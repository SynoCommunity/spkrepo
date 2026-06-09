# -*- coding: utf-8 -*-
import io
import os
import shutil
import uuid
from datetime import date, timedelta

from celery.result import AsyncResult
from flask import (
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    request,
    session,
    url_for,
)
from flask_admin import AdminIndexView, BaseView, expose
from flask_admin.actions import action
from flask_admin.contrib.sqla import ModelView
from flask_admin.contrib.sqla.form import get_form
from flask_admin.contrib.sqla.tools import get_query_for_ids
from flask_admin.form import ImageUploadField
from flask_security import current_user
from flask_wtf.csrf import generate_csrf
from markupsafe import Markup
from sqlalchemy.exc import SQLAlchemyError
from wtforms import PasswordField
from wtforms.validators import Regexp

from ..ext import cache, celery, db
from ..models import (
    Architecture,
    Build,
    DownloadStat,
    Firmware,
    Package,
    Screenshot,
    Service,
    User,
    Version,
)
from ..utils import SPK, apply_info_from_spk, extract_version_metadata
from .nas import clear_catalog_cache
from .tasks import resync_build_file, resync_build_metadata

# ---------------------------------------------------------------------------
# Shared formatters
# ---------------------------------------------------------------------------


def _bool_formatter(v, c, m, p):
    value = getattr(m, p)
    if value is None:
        return Markup('<i class="fa fa-question-circle text-muted"></i>')
    if value:
        return Markup('<i class="fa fa-check-circle text-success"></i>')
    return Markup('<i class="fa fa-times-circle text-danger"></i>')


def _flash_action_results(successes, failures, skipped=None, item_label="item"):
    if successes:
        count = len(successes)
        flash(
            f"{item_label.capitalize()} {successes[0]} refreshed."
            if count == 1
            else f"Refreshed {count} {item_label}s: {', '.join(successes)}"
        )
    if skipped:
        count = len(skipped)
        flash(
            f"{item_label.capitalize()} {skipped[0]} skipped."
            if count == 1
            else f"Skipped {count} {item_label}s: {', '.join(skipped)}"
        )
    for name, message in failures:
        flash(f"Failed to process {name}: {message}", "error")


def _task_redis_key():
    """Return a per-user Redis key for storing task IDs.

    The key is stored in the session cookie as a short UUID — only 36 bytes,
    well within the 4KB cookie limit regardless of how many tasks are queued.
    The task ID list itself lives in Redis.
    """

    key = session.get("resync_task_key")
    if not key:
        key = f"resync_tasks:{uuid.uuid4()}"
        session["resync_task_key"] = key
    return key


def _store_task_ids(new_ids):
    """Append new task IDs to the user's Redis-backed task list."""
    key = _task_redis_key()
    existing = cache.get(key) or []
    cache.set(key, existing + new_ids, timeout=86400)  # match result_expires


def _get_task_ids():
    """Return the current user's task ID list from Redis."""
    key = _task_redis_key()
    return cache.get(key) or []


def _clear_task_ids():
    """Remove the current user's task ID list from Redis."""

    key = session.pop("resync_task_key", None)
    if key:
        cache.delete(key)


# ---------------------------------------------------------------------------
# SPK helpers
# ---------------------------------------------------------------------------


def _resync_build_file(build):
    """Recalculate md5 and size from the build file on disk."""
    if not build.path:
        raise ValueError("Build has no file path")
    build.md5 = build.calculate_md5()
    build.size = build.calculate_size()


def _resync_build_metadata(session, build):
    """Re-read the SPK file for a build, check it is consistent with all sibling
    builds under the same version, then apply the metadata to the database.

    Raises ValueError if the build's SPK metadata conflicts with any sibling SPK,
    preventing last-write-wins corruption of shared version-level fields.
    """
    if not build.path:
        raise ValueError("Build has no file path")

    file_path = os.path.join(current_app.config["DATA_PATH"], build.path)
    with io.open(file_path, "rb") as stream:
        spk = SPK(stream)
        incoming_meta = extract_version_metadata(spk)

        for sibling in build.version.builds:
            if sibling.id == build.id or not sibling.path:
                continue
            sibling_path = os.path.join(current_app.config["DATA_PATH"], sibling.path)
            with io.open(sibling_path, "rb") as s2:
                sibling_meta = extract_version_metadata(SPK(s2))
            if sibling_meta != incoming_meta:
                raise ValueError(
                    f"Version-level metadata mismatch between "
                    f"{os.path.basename(build.path)} and "
                    f"{os.path.basename(sibling.path)} — resync aborted. "
                    f"Inspect the SPK files to resolve the inconsistency."
                )

        md5 = spk.calculate_md5()
        apply_info_from_spk(session, build, spk, md5)


# ---------------------------------------------------------------------------
# Mixin for sign / unsign / resync actions shared by VersionView & BuildView
# ---------------------------------------------------------------------------


class SignResyncMixin:
    """
    Mixin that provides sign, unsign, resync_info, and resync_file actions,
    plus the corresponding permission guards.

    Subclasses must implement `_iter_builds(ids)` which yields (label, build)
    pairs for the given list of selected ids.
    """

    # -- Permission properties (override in subclass if needed) -------------

    @property
    def can_sign(self):
        return current_user.has_role("admin")

    @property
    def can_unsign(self):
        return current_user.has_role("admin")

    @property
    def can_resync_info(self):
        return current_user.has_role("admin") or current_user.has_role("package_admin")

    @property
    def can_resync_file(self):
        return current_user.has_role("admin") or current_user.has_role("package_admin")

    # -- Permission guards --------------------------------------------------

    def is_action_allowed(self, name):
        checks = {
            "sign": self.can_sign,
            "unsign": self.can_unsign,
            "resync_info": self.can_resync_info,
            "resync_file": self.can_resync_file,
        }
        if name in checks and not checks[name]:
            return False
        return super().is_action_allowed(name)

    def handle_action(self, return_view=None):
        action_name = request.form.get("action")
        checks = {
            "sign": self.can_sign,
            "unsign": self.can_unsign,
            "resync_info": self.can_resync_info,
            "resync_file": self.can_resync_file,
        }
        if action_name in checks and not checks[action_name]:
            abort(403)
        return super().handle_action(return_view)

    # -- Subclass contract --------------------------------------------------

    def _iter_builds(self, ids):
        """
        Yield (label, build) for each build implied by the selected ids.
        Override in VersionView to expand version -> builds.
        """
        raise NotImplementedError

    # -- Shared actions -----------------------------------------------------

    @action("sign", "Sign", "Are you sure you want to sign selected builds?")
    def action_sign(self, ids):
        try:
            already_signed, success, failed = [], [], []
            for label, build in self._iter_builds(ids):
                with io.open(
                    os.path.join(current_app.config["DATA_PATH"], build.path), "rb+"
                ) as f:
                    spk = SPK(f)
                    if spk.signature is not None:
                        already_signed.append(label)
                        continue
                    try:
                        spk.sign(
                            current_app.config["GNUPG_TIMESTAMP_URL"],
                            current_app.config["GNUPG_PATH"],
                        )
                        _resync_build_file(build)
                        db.session.commit()
                        success.append(label)
                    except Exception:
                        current_app.logger.exception("Failed to sign build %s", label)
                        db.session.rollback()
                        failed.append(label)
            _flash_action_results(
                success,
                [(f, "") for f in failed],
                skipped=already_signed,
                item_label="build",
            )
        except Exception:  # pragma: no cover
            current_app.logger.exception("Failed to sign builds")
            flash("Failed to sign builds. Please check the logs.", "error")

    @action("unsign", "Unsign", "Are you sure you want to unsign selected builds?")
    def action_unsign(self, ids):
        try:
            not_signed, active_skipped, success, failed = [], [], [], []
            for label, build in self._iter_builds(ids):
                if build.active:
                    active_skipped.append(label)
                    continue
                with io.open(
                    os.path.join(current_app.config["DATA_PATH"], build.path), "rb+"
                ) as f:
                    spk = SPK(f)
                    if spk.signature is None:
                        not_signed.append(label)
                        continue
                    try:
                        spk.unsign()
                        _resync_build_file(build)
                        db.session.commit()
                        success.append(label)
                    except Exception:
                        current_app.logger.exception("Failed to unsign build %s", label)
                        db.session.rollback()
                        failed.append(label)
            if active_skipped:
                count = len(active_skipped)
                flash(
                    (
                        f"Build {active_skipped[0]} must be deactivated before "
                        f"unsigning."
                        if count == 1
                        else f"Skipped {count} active builds — deactivate before "
                        f"unsigning: {', '.join(active_skipped)}"
                    ),
                    "warning",
                )
            _flash_action_results(
                success,
                [(f, "") for f in failed],
                skipped=not_signed,
                item_label="build",
            )
        except Exception:  # pragma: no cover
            current_app.logger.exception("Failed to unsign builds")
            flash("Failed to unsign builds. Please check the logs.", "error")

    @action(
        "resync_info",
        "Resync Info",
        "Reapply INFO metadata from selected builds?",
    )
    def action_resync_info(self, ids):
        task_ids = []
        for label, build in self._iter_builds(ids):
            result = resync_build_metadata.delay(build.id, str(build))
            task_ids.append(result.id)
        if task_ids:
            _store_task_ids(task_ids)
            count = len(task_ids)
            flash(
                Markup(
                    f"{count} resync task(s) queued. "
                    f'<a href="/admin/tasks/">View status</a>',
                ),
                "info",
            )
        else:
            flash("No builds found to resync.", "warning")

    @action(
        "resync_file",
        "Resync File",
        "Recalculate md5 and size from selected build files?",
    )
    def action_resync_file(self, ids):
        task_ids = []
        for label, build in self._iter_builds(ids):
            result = resync_build_file.delay(build.id, str(build))
            task_ids.append(result.id)
        if task_ids:
            _store_task_ids(task_ids)
            count = len(task_ids)
            flash(
                Markup(
                    f"{count} file resync task(s) queued. "
                    f'<a href="/admin/tasks/">View status</a>',
                ),
                "info",
            )
        else:
            flash("No builds found to resync.", "warning")


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


class UserView(ModelView):
    """View for :class:`~spkrepo.models.User`"""

    def __init__(self, **kwargs):
        super().__init__(User, db, **kwargs)

    def is_accessible(self):
        return current_user.is_authenticated and current_user.has_role("admin")

    can_create = False

    column_list = ("username", "email", "roles", "active", "confirmed_at")
    column_formatters = {
        "confirmed_at": lambda v, c, m, p: (
            m.confirmed_at.strftime("%Y-%m-%d %H:%M:%S") if m.confirmed_at else None
        )
    }

    form_columns = ("username", "roles", "active")
    form_overrides = {"password": PasswordField}

    def after_model_change(self, form, model, is_created):
        cache.delete("packages_versions")
        clear_catalog_cache()

    def after_model_delete(self, model):
        cache.delete("packages_versions")
        clear_catalog_cache()

    @action("activate", "Activate", "Are you sure you want to activate selected users?")
    def action_activate(self, ids):
        try:
            users = get_query_for_ids(self.get_query(), self.model, ids).all()
            for user in users:
                user.active = True
            db.session.commit()
            flash(
                "User was successfully activated."
                if len(users) == 1
                else f"{len(users)} users were successfully activated."
            )
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception("Failed to activate users")
            flash("Failed to activate users. Please check the logs.", "error")

    @action(
        "deactivate",
        "Deactivate",
        "Are you sure you want to deactivate selected users?",
    )
    def action_deactivate(self, ids):
        try:
            users = get_query_for_ids(self.get_query(), self.model, ids).all()
            for user in users:
                user.active = False
            db.session.commit()
            flash(
                "User was successfully deactivated."
                if len(users) == 1
                else f"{len(users)} users were successfully deactivated."
            )
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception("Failed to deactivate users")
            flash("Failed to deactivate users. Please check the logs.", "error")


class ArchitectureView(ModelView):
    """View for :class:`~spkrepo.models.Architecture`"""

    def __init__(self, **kwargs):
        super().__init__(Architecture, db, **kwargs)

    def is_accessible(self):
        return current_user.is_authenticated and current_user.has_role("package_admin")

    can_edit = False
    can_delete = False

    form_excluded_columns = "builds"


class FirmwareView(ModelView):
    """View for :class:`~spkrepo.models.Firmware`"""

    def __init__(self, **kwargs):
        super().__init__(Firmware, db, **kwargs)

    def is_accessible(self):
        return current_user.is_authenticated and current_user.has_role("package_admin")

    can_edit = False
    can_delete = False

    form_columns = ("version", "build", "type")
    form_args = {
        "version": {"validators": [Regexp(SPK.firmware_version_re)]},
        "type": {"validators": [Regexp(SPK.firmware_type_re)]},
    }


class ServiceView(ModelView):
    """View for :class:`~spkrepo.models.Service`"""

    def __init__(self, **kwargs):
        super().__init__(Service, db, **kwargs)

    def is_accessible(self):
        return current_user.is_authenticated and current_user.has_role("package_admin")

    can_edit = False
    can_delete = False


ALLOWED_SCREENSHOT_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def screenshot_namegen(obj, file_data):
    ext = os.path.splitext(file_data.filename)[1].lower()
    if ext not in ALLOWED_SCREENSHOT_EXTENSIONS:
        raise ValueError(f"Invalid screenshot file extension: {ext!r}")
    i = 1
    while os.path.exists(
        os.path.join(
            current_app.config["DATA_PATH"],
            obj.package.name,
            f"screenshot_{i}{ext}",
        )
    ):
        i += 1
    return os.path.join(obj.package.name, f"screenshot_{i}{ext}")


class ScreenshotView(ModelView):
    """View for :class:`~spkrepo.models.Screenshot`"""

    def __init__(self, **kwargs):
        super().__init__(Screenshot, db, **kwargs)

    def is_accessible(self):
        return current_user.is_authenticated and current_user.has_role("package_admin")

    can_edit = False

    column_labels = {
        "package.name": "Package Name",
        "path": "Screenshot",
    }

    def _display(view, context, model, name):
        safe_url = Markup.escape(url_for("nas.data", path=model.path))
        return Markup(f'<img src="{safe_url}" alt="screenshot" height="100">')

    column_formatters = {"path": _display}
    column_sortable_list = (("package", "package.name"),)
    column_default_sort = "package.name"
    column_filters = ("package.name",)

    def on_model_delete(self, model):
        screenshot_path = os.path.join(current_app.config["DATA_PATH"], model.path)
        if os.path.exists(screenshot_path):
            os.remove(screenshot_path)

    form_overrides = {"path": ImageUploadField}
    form_args = {
        "path": {
            "label": "Screenshot",
            "namegen": screenshot_namegen,
            "base_path": lambda: current_app.config["DATA_PATH"],
        }
    }


class PackageView(ModelView):
    """View for :class:`~spkrepo.models.Package`"""

    def __init__(self, **kwargs):
        super().__init__(Package, db, **kwargs)

    def is_accessible(self):
        return current_user.is_authenticated and current_user.has_role("package_admin")

    @property
    def can_create(self):
        return current_user.has_role("package_admin")

    @property
    def can_edit(self):
        return current_user.has_role("package_admin")

    @property
    def can_delete(self):
        return current_user.has_role("admin")

    def get_edit_form(self):
        edit_form_columns = tuple(c for c in self.form_columns if c != "name")
        converter = self.model_form_converter(self.session, self)
        form_class = get_form(
            self.model,
            converter,
            base_class=self.form_base_class,
            only=edit_form_columns,
            exclude=self.form_excluded_columns,
            field_args=self.form_args,
            extra_fields=self.form_extra_fields,
        )
        return form_class

    def on_model_change(self, form, model, is_created):
        if is_created:
            package_path = os.path.join(current_app.config["DATA_PATH"], model.name)
            if not os.path.exists(package_path):
                os.mkdir(package_path)

    def on_model_delete(self, model):
        package_path = os.path.join(current_app.config["DATA_PATH"], model.name)
        if os.path.exists(package_path):
            shutil.rmtree(package_path)

    def after_model_change(self, form, model, is_created):
        cache.delete("packages_versions")
        clear_catalog_cache()

    def after_model_delete(self, model):
        cache.delete("packages_versions")
        clear_catalog_cache()

    can_view_details = True
    details_template = "admin/package_detail.html"

    @expose("/details/")
    def details_view(self):
        self._template_args["arch_breakdown"] = self._get_arch_breakdown()
        return super().details_view()

    def _get_arch_breakdown(self):
        pkg_id = request.args.get("id", type=int)
        if not pkg_id:
            return None
        cutoff = date.today() - timedelta(days=90)
        rows = db.session.execute(
            db.select(
                Architecture.code,
                db.func.sum(DownloadStat.count).label("total"),
            )
            .join(Architecture, Architecture.id == DownloadStat.architecture_id)
            .where(
                db.and_(
                    DownloadStat.package_id == pkg_id,
                    DownloadStat.date >= cutoff,
                )
            )
            .group_by(Architecture.code)
            .order_by(db.desc("total"))
            .limit(3)
        ).all()
        if not rows:
            return None
        grand_total = sum(total for _, total in rows)
        return [(code, total, total / grand_total * 100) for code, total in rows]

    column_list = (
        "name",
        "author",
        "maintainers",
        "download_count",
        "recent_download_count",
        "last_download_date",
        "insert_date",
    )
    column_sortable_list = (
        ("name", "name"),
        ("author", "author.username"),
        ("insert_date", "insert_date"),
        ("download_count", "download_count"),
        ("recent_download_count", "recent_download_count"),
        ("last_download_date", "last_download_date"),
    )
    column_formatters = {
        "insert_date": lambda v, c, m, p: (
            m.insert_date.strftime("%Y-%m-%d") if m.insert_date else None
        ),
        "download_count": lambda v, c, m, p: (
            f"{m.download_count:,}" if m.download_count else "0"
        ),
        "recent_download_count": lambda v, c, m, p: (
            f"{m.recent_download_count:,}" if m.recent_download_count else "0"
        ),
        "last_download_date": lambda v, c, m, p: (
            m.last_download_date.strftime("%Y-%m-%d") if m.last_download_date else None
        ),
    }

    column_formatters_detail = {
        "insert_date": lambda v, c, m, p: m.insert_date.strftime("%Y-%m-%d %H:%M:%S"),
    }
    column_labels = {
        "download_count": "Downloads",
        "recent_download_count": "Recent Downloads",
        "last_download_date": "Last Download",
        "author.username": "Author",
        "arch_breakdown": "Top Architectures (90d)",
    }
    column_filters = ("name", "author.username")
    column_details_list = (
        "name",
        "author",
        "maintainers",
        "insert_date",
        "download_count",
        "recent_download_count",
        "last_download_date",
        "arch_breakdown",
    )

    form_columns = ("name", "author", "maintainers")
    form_args = {"name": {"validators": [Regexp(SPK.package_re)]}}


class VersionView(SignResyncMixin, ModelView):
    """View for :class:`~spkrepo.models.Version`"""

    def __init__(self, **kwargs):
        super().__init__(Version, db, **kwargs)

    def is_accessible(self):
        return current_user.is_authenticated and any(
            map(current_user.has_role, ("developer", "package_admin"))
        )

    can_create = False
    can_edit = False
    can_view_details = True

    @property
    def can_delete(self):
        return current_user.has_role("admin")

    def _iter_builds(self, ids):
        versions = get_query_for_ids(self.get_query(), self.model, ids).all()
        for version in versions:
            for build in version.builds:
                label = os.path.basename(build.path) if build.path else str(build.id)
                yield label, build

    def on_model_delete(self, model):
        version_path = os.path.join(
            current_app.config["DATA_PATH"], model.package.name, str(model.version)
        )
        if os.path.exists(version_path):
            shutil.rmtree(version_path)

    def _truncate_formatter(view, context, model, name):
        text = getattr(model, name)
        if not text:
            return text
        if len(text) > 250:
            return Markup(f"{Markup.escape(text[:250])}...")
        return Markup.escape(text)

    column_list = (
        "package",
        "upstream_version",
        "version",
        "beta",
        "startable",
        "all_builds_active",
        "total_size",
        "insert_date",
    )
    column_labels = {
        "package.name": "Package Name",
        "version_string": "Version",
        "dependencies": "Dependencies",
        "all_builds_active": "All Active",
        "install_wizard": "Install Wizard",
        "upgrade_wizard": "Upgrade Wizard",
        "total_size": "Total Size",
        "download_count": "Downloads",
        "recent_download_count": "Recent Downloads (90d)",
    }
    column_filters = (
        "package.name",
        "upstream_version",
        "version",
        "beta",
        "startable",
        "all_builds_active",
    )
    column_sortable_list = (
        ("package", "package.name"),
        ("upstream_version", "upstream_version"),
        ("version", "version"),
        ("beta", "beta"),
        ("insert_date", "insert_date"),
        ("all_builds_active", "all_builds_active"),
        ("startable", "startable"),
        ("total_size", "total_size"),
    )
    column_formatters = {
        "insert_date": lambda v, c, m, p: (
            m.insert_date.strftime("%Y-%m-%d") if m.insert_date else None
        ),
        "all_builds_active": _bool_formatter,
        "startable": _bool_formatter,
        "beta": _bool_formatter,
        "total_size": lambda v, c, m, p: (
            f"{m.total_size / 1024 / 1024:.1f} MB" if m.total_size else None
        ),
    }
    column_formatters_detail = {
        "insert_date": lambda v, c, m, p: m.insert_date.strftime("%Y-%m-%d %H:%M:%S"),
        "install_wizard": _bool_formatter,
        "upgrade_wizard": _bool_formatter,
        "startable": _bool_formatter,
        "license": _truncate_formatter,
        "download_count": lambda v, c, m, p: (
            f"{m.download_count:,}" if m.download_count else "0"
        ),
        "recent_download_count": lambda v, c, m, p: (
            f"{m.recent_download_count:,}" if m.recent_download_count else "0"
        ),
    }
    column_default_sort = (Version.insert_date, True)

    def get_query(self):
        q = super().get_query()
        if not current_user.has_role("package_admin"):
            q = (
                q.join(self.model.package)
                .join(Package.maintainers)
                .filter(User.id == current_user.id)
            )
        return q

    def get_count_query(self):
        q = super().get_count_query()
        if not current_user.has_role("package_admin"):
            q = (
                q.join(self.model.package)
                .join(Package.maintainers)
                .filter(User.id == current_user.id)
            )
        return q

    @action(
        "activate",
        "Activate",
        "Are you sure you want to activate selected versions' builds?",
    )
    def action_activate(self, ids):
        try:
            versions = get_query_for_ids(self.get_query(), self.model, ids).all()
            for version in versions:
                for build in version.builds:
                    build.active = True
            db.session.commit()
            cache.delete("packages_versions")
            clear_catalog_cache()
            flash(
                "Builds on version were successfully activated."
                if len(versions) == 1
                else (
                    f"Builds have been successfully activated for "
                    f"{len(versions)} versions."
                )
            )
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception("Failed to activate versions' builds")
            flash(
                "Failed to activate versions' builds. Please check the logs.", "error"
            )

    @action(
        "deactivate",
        "Deactivate",
        "Are you sure you want to deactivate selected versions' builds?",
    )
    def action_deactivate(self, ids):
        try:
            versions = get_query_for_ids(self.get_query(), self.model, ids).all()
            for version in versions:
                for build in version.builds:
                    build.active = False
            db.session.commit()
            cache.delete("packages_versions")
            clear_catalog_cache()
            flash(
                "Builds on version were successfully deactivated."
                if len(versions) == 1
                else (
                    f"Builds have been successfully deactivated for "
                    f"{len(versions)} versions."
                )
            )
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception("Failed to deactivate versions' builds")
            flash(
                "Failed to deactivate versions' builds. Please check the logs.", "error"
            )


class BuildView(SignResyncMixin, ModelView):
    """View for :class:`~spkrepo.models.Build`"""

    def __init__(self, **kwargs):
        super().__init__(Build, db, **kwargs)

    def is_accessible(self):
        return current_user.is_authenticated and any(
            map(current_user.has_role, ("developer", "package_admin"))
        )

    can_create = False
    can_edit = False
    can_view_details = True

    @property
    def can_delete(self):
        return current_user.has_role("admin")

    def _iter_builds(self, ids):
        for build_id in ids:
            try:
                build = db.session.get(self.model, int(build_id))
            except (TypeError, ValueError):
                continue
            if build is None:
                continue
            label = os.path.basename(build.path) if build.path else str(build_id)
            yield label, build

    column_list = (
        "version.package",
        "version.version",
        "architectures",
        "firmware_min",
        "publisher",
        "insert_date",
        "active",
    )
    column_labels = {
        "version.package": "Package",
        "version.package.name": "Package Name",
        "version.upstream_version": "Upstream Version",
        "version.version": "Version",
        "architectures.code": "Architecture",
        "firmware_min.version": "Minimum Firmware",
        "firmware_max.version": "Maximum Firmware",
        "publisher.username": "Publisher Username",
        "size": "Package Size",
        "checksum": "Application Checksum",
        "md5": "Package Checksum",
    }
    column_filters = (
        "version.package.name",
        "version.version",
        "architectures.code",
        "firmware_min.version",
        "publisher.username",
        "active",
    )
    column_sortable_list = (
        ("version.package", "version.package.name"),
        ("version.version", "version.version"),
        ("firmware_min", "firmware_min.build"),
        ("publisher", "publisher.username"),
        ("insert_date", "insert_date"),
        ("active", "active"),
    )
    column_formatters = {
        "insert_date": lambda v, c, m, p: (
            m.insert_date.strftime("%Y-%m-%d") if m.insert_date else None
        ),
        "size": lambda v, c, m, p: (
            f"{m.size / 1024 / 1024:.1f} MB" if m.size else None
        ),
        "active": _bool_formatter,
    }
    column_formatters_detail = {
        "insert_date": lambda v, c, m, p: m.insert_date.strftime("%Y-%m-%d %H:%M:%S"),
        "size": lambda v, c, m, p: (
            f"{m.size / 1024 / 1024:.1f} MB" if m.size else None
        ),
    }
    column_default_sort = (Build.insert_date, True)

    def get_query(self):
        q = super().get_query()
        if not current_user.has_role("package_admin"):
            q = (
                q.join(self.model.version)
                .join(Version.package)
                .join(Package.maintainers)
                .filter(User.id == current_user.id)
            )
        return q

    def get_count_query(self):
        q = super().get_count_query()
        if not current_user.has_role("package_admin"):
            q = (
                q.join(self.model.version)
                .join(Version.package)
                .join(Package.maintainers)
                .filter(User.id == current_user.id)
            )
        return q

    def on_model_delete(self, model):
        build_path = os.path.join(current_app.config["DATA_PATH"], model.path)
        if os.path.exists(build_path):
            os.remove(build_path)

    def after_model_change(self, form, model, is_created):
        cache.delete("packages_versions")
        clear_catalog_cache()

    def after_model_delete(self, model):
        cache.delete("packages_versions")
        clear_catalog_cache()

    @action(
        "activate", "Activate", "Are you sure you want to activate selected builds?"
    )
    def action_activate(self, ids):
        try:
            builds = get_query_for_ids(self.get_query(), self.model, ids).all()
            for build in builds:
                build.active = True
            db.session.commit()
            cache.delete("packages_versions")
            clear_catalog_cache()
            flash(
                "Build was successfully activated."
                if len(builds) == 1
                else f"{len(builds)} builds were successfully activated."
            )
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception("Failed to activate builds")
            flash("Failed to activate builds. Please check the logs.", "error")

    @action(
        "deactivate",
        "Deactivate",
        "Are you sure you want to deactivate selected builds?",
    )
    def action_deactivate(self, ids):
        try:
            builds = get_query_for_ids(self.get_query(), self.model, ids).all()
            for build in builds:
                build.active = False
            db.session.commit()
            cache.delete("packages_versions")
            clear_catalog_cache()
            flash(
                "Build was successfully deactivated."
                if len(builds) == 1
                else f"{len(builds)} builds were successfully deactivated."
            )
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception("Failed to deactivate builds")
            flash("Failed to deactivate builds. Please check the logs.", "error")


# ---------------------------------------------------------------------------
# Admin index
# ---------------------------------------------------------------------------


class IndexView(AdminIndexView):
    @expose("/")
    def index(self):
        if not current_user.is_authenticated:
            return redirect(url_for("security.login"))
        if not any(map(current_user.has_role, ("developer", "package_admin", "admin"))):
            abort(403)

        is_privileged = current_user.has_role("package_admin") or current_user.has_role(
            "admin"
        )

        def _maintainer_filter(q):
            """Apply maintainer filter for non-privileged users."""
            return q.join(Package.maintainers).filter(User.id == current_user.id)

        if is_privileged:
            package_count = Package.query.count()
            build_count = Build.query.count()
            inactive_build_count = Build.query.filter_by(active=False).count()
            recent_versions = (
                Version.query.order_by(Version.insert_date.desc()).limit(5).all()
            )
        else:
            package_count = _maintainer_filter(Package.query).count()
            build_count = _maintainer_filter(
                Build.query.join(Build.version).join(Version.package)
            ).count()
            inactive_build_count = _maintainer_filter(
                Build.query.filter_by(active=False)
                .join(Build.version)
                .join(Version.package)
            ).count()
            recent_versions = (
                _maintainer_filter(Version.query.join(Version.package))
                .order_by(Version.insert_date.desc())
                .limit(5)
                .all()
            )

        return self.render(
            "admin/index.html",
            package_count=package_count,
            build_count=build_count,
            inactive_build_count=inactive_build_count,
            unconfirmed_user_count=(
                User.query.filter_by(confirmed_at=None).count()
                if current_user.has_role("admin")
                else None
            ),
            recent_versions=recent_versions,
        )


# ---------------------------------------------------------------------------
# Task status
# ---------------------------------------------------------------------------


class TaskStatusView(BaseView):
    """Admin panel page showing the status of queued resync tasks."""

    def is_accessible(self):
        return current_user.is_authenticated and any(
            current_user.has_role(r) for r in ("developer", "package_admin", "admin")
        )

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("security.login"))

    @expose("/")
    def index(self):
        task_ids = _get_task_ids()
        tasks = []
        pending_count = 0
        for task_id in task_ids:
            result = AsyncResult(task_id, app=celery)
            state = result.state
            info = result.info if result.ready() else None
            if state in ("PENDING", "STARTED", "RETRY"):
                pending_count += 1
            tasks.append(
                {
                    "id": task_id,
                    "state": state,
                    "result": info,
                }
            )
        return self.render(
            "admin/task_status.html",
            tasks=tasks,
            pending_count=pending_count,
            csrf_token=generate_csrf,
        )

    @expose("/status/")
    def status_json(self):
        """JSON endpoint polled by the page's auto-refresh."""
        if not self.is_accessible():
            return jsonify({"error": "forbidden"}), 403

        task_ids = _get_task_ids()
        tasks = []
        pending_count = 0
        for task_id in task_ids:
            result = AsyncResult(task_id, app=celery)
            state = result.state
            info = result.info if result.ready() else None
            label = (
                (info or {}).get("label", task_id)
                if isinstance(info, dict)
                else task_id
            )
            error = (
                (info or {}).get("error")
                if isinstance(info, dict)
                else (str(info) if info else None)
            )
            if state in ("PENDING", "STARTED", "RETRY"):
                pending_count += 1
            tasks.append(
                {
                    "id": task_id,
                    "state": state,
                    "label": label,
                    "error": error,
                }
            )
        return jsonify({"tasks": tasks, "pending_count": pending_count})

    @expose("/clear/", methods=["POST"])
    def clear(self):
        """Clear the current user's task list from Redis."""
        if not self.is_accessible():
            abort(403)
        _clear_task_ids()
        return redirect(url_for("tasks.index"))
