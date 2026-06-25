# -*- coding: utf-8 -*-
import io
import json
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

from .. import storage as storage_service
from ..ext import cache, celery, db
from ..models import (
    Architecture,
    Build,
    DownloadStat,
    Firmware,
    Package,
    PackageDownloadCounts,
    Screenshot,
    Service,
    User,
    Version,
)
from ..utils import SPK
from .nas import clear_catalog_cache
from .tasks import (
    rehome_from_storage,
    resync_build_file,
    resync_build_metadata,
    upload_to_storage,
)

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


def _storage_formatter(v, c, m, p):
    if m.storage == "remote":
        return Markup('<i class="fa fa-cloud text-info"></i>')
    if m.storage == "local":
        return Markup('<i class="fa fa-hdd-o text-muted"></i>')
    return Markup('<i class="fa fa-question-circle text-warning"></i>')


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

    key = session.get("background_task_key")
    if not key:
        key = f"background_tasks:{uuid.uuid4()}"
        session["background_task_key"] = key
    return key


def _store_task_tasks(new_tasks):
    """Append task info dicts to the user's Redis-backed task list.
    Each dict: {"id": str, "type": str, "label": str}
    """
    key = _task_redis_key()
    existing = cache.get(key) or []
    cache.set(key, existing + new_tasks, timeout=86400)


def _get_task_ids():
    """Return the current user's task list from Redis."""
    key = _task_redis_key()
    return cache.get(key) or []


def _clear_task_ids():
    """Remove the current user's task ID list from Redis."""

    key = session.pop("background_task_key", None)
    if key:
        cache.delete(key)


def _detect_and_fix_signed(build):
    """If the local SPK has a signature but build.signed is False, fix it.
    Returns True if the column was updated."""
    if build.signed:
        return False
    if not build.path:
        return False
    spk_path = os.path.join(current_app.config["DATA_PATH"], build.path)
    if not os.path.exists(spk_path):
        return False
    try:
        with io.open(spk_path, "rb") as f:
            spk = SPK(f)
        if spk.signature is not None:
            build.signed = True
            return True
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# SPK helpers
# ---------------------------------------------------------------------------


def _resync_build_file(build):
    """Recalculate md5 and size from the build file or sidecar."""
    if not build.path:
        raise ValueError("Build has no file path")
    sidecar_path = os.path.join(current_app.config["DATA_PATH"], build.path + ".json")
    if os.path.exists(sidecar_path):
        with io.open(sidecar_path, "r", encoding="utf-8") as f:
            sidecar = json.load(f)
        build.md5 = sidecar["calculated"]["md5"]
        build.size = sidecar["calculated"]["size"]
    else:
        build.md5 = build.calculate_md5()
        build.size = build.calculate_size()


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

    @property
    def can_upload(self):
        return current_user.has_role("admin") or current_user.has_role("package_admin")

    @property
    def can_rehome(self):
        return current_user.has_role("admin") or current_user.has_role("package_admin")

    # -- Permission guards --------------------------------------------------

    def is_action_allowed(self, name):
        checks = {
            "07_sign": self.can_sign,
            "08_unsign": self.can_unsign,
            "05_resync_info": self.can_resync_info,
            "06_resync_file": self.can_resync_file,
            "03_upload": self.can_upload,
            "04_rehome": self.can_rehome,
        }
        if name in checks and not checks[name]:
            return False
        return super().is_action_allowed(name)

    def handle_action(self, return_view=None):
        action_name = request.form.get("action")
        checks = {
            "07_sign": self.can_sign,
            "08_unsign": self.can_unsign,
            "05_resync_info": self.can_resync_info,
            "06_resync_file": self.can_resync_file,
            "03_upload": self.can_upload,
            "04_rehome": self.can_rehome,
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

    @action("07_sign", "Sign", "Are you sure you want to sign selected builds?")
    def action_07_sign(self, ids):
        try:
            not_local, already_signed, recovered, success, failed = ([], [], [], [], [])
            for label, build in self._iter_builds(ids):
                if build.storage != "local":
                    not_local.append(label)
                    continue
                with io.open(
                    os.path.join(current_app.config["DATA_PATH"], build.path), "rb+"
                ) as f:
                    spk = SPK(f)
                    if spk.signature is not None:
                        if not build.signed:
                            build.signed = True
                            db.session.commit()
                            recovered.append(label)
                        else:
                            already_signed.append(label)
                        continue
                    if current_app.config["GNUPG_PATH"] is None:
                        failed.append((label, "GNUPG_PATH is not configured"))
                        continue
                    try:
                        spk.sign(
                            current_app.config["GNUPG_TIMESTAMP_URL"],
                            current_app.config["GNUPG_PATH"],
                        )
                        _resync_build_file(build)
                        build.signed = True
                        db.session.commit()
                        success.append(label)
                    except Exception as e:
                        current_app.logger.exception("Failed to sign build %s", label)
                        db.session.rollback()
                        failed.append((label, str(e) or "unknown error"))
            if not_local:
                flash(
                    "Build(s) in Object Storage must be re-homed before signing: "
                    + ", ".join(not_local),
                    "warning",
                )
            if recovered:
                flash(
                    "Signature status corrected for: " + ", ".join(recovered),
                    "info",
                )
            _flash_action_results(
                success,
                failed,
                skipped=already_signed,
                item_label="build",
            )
        except Exception:  # pragma: no cover
            current_app.logger.exception("Failed to sign builds")
            flash("Failed to sign builds. Please check the logs.", "error")

    @action("08_unsign", "Unsign", "Are you sure you want to unsign selected builds?")
    def action_08_unsign(self, ids):
        try:
            not_local, not_signed, active_skipped, success, failed = (
                [],
                [],
                [],
                [],
                [],
            )
            for label, build in self._iter_builds(ids):
                if build.storage != "local":
                    not_local.append(label)
                    continue
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
                        build.signed = False
                        db.session.commit()
                        success.append(label)
                    except Exception as e:
                        current_app.logger.exception("Failed to unsign build %s", label)
                        db.session.rollback()
                        failed.append((label, str(e) or "unknown error"))
            if not_local:
                flash(
                    "Build(s) in Object Storage must be re-homed before unsigning: "
                    + ", ".join(not_local),
                    "warning",
                )
            if active_skipped:
                count = len(active_skipped)
                flash(
                    (
                        f"Build {active_skipped[0]} must be deactivated before "
                        "unsigning."
                        if count == 1
                        else f"Skipped {count} active builds — deactivate before "
                        f"unsigning: {', '.join(active_skipped)}"
                    ),
                    "warning",
                )
            _flash_action_results(
                success,
                failed,
                skipped=not_signed,
                item_label="build",
            )
        except Exception:  # pragma: no cover
            current_app.logger.exception("Failed to unsign builds")
            flash("Failed to unsign builds. Please check the logs.", "error")

    @action(
        "03_upload",
        "Upload",
        "Upload selected builds to Object Storage?",
    )
    def action_03_upload(self, ids):
        tasks = []
        for label, build in self._iter_builds(ids):
            if build.storage != "local":
                continue
            if not build.active:
                continue
            if not build.signed and not _detect_and_fix_signed(build):
                continue
            result = upload_to_storage.delay(build.id, str(build))
            tasks.append({"id": result.id, "type": "upload", "label": label})
        if tasks:
            _store_task_tasks(tasks)
            count = len(tasks)
            flash(
                Markup(
                    f"{count} upload task(s) queued. "
                    f'<a href="/admin/tasks/">View status</a>',
                ),
                "info",
            )
        else:
            flash(
                "No builds found to upload (must be local, active, and signed).",
                "warning",
            )

    @action(
        "04_rehome",
        "Re-home",
        "Download selected builds from Object Storage for local editing?",
    )
    def action_04_rehome(self, ids):
        tasks = []
        for label, build in self._iter_builds(ids):
            if build.active:
                continue
            if build.storage != "remote":
                continue
            result = rehome_from_storage.delay(build.id, str(build))
            tasks.append({"id": result.id, "type": "rehome", "label": label})
        if tasks:
            _store_task_tasks(tasks)
            count = len(tasks)
            flash(
                Markup(
                    f"{count} re-home task(s) queued. "
                    f'<a href="/admin/tasks/">View status</a>',
                ),
                "info",
            )
        else:
            flash(
                "No builds found to re-home (must be inactive and in Object Storage).",
                "warning",
            )

    @action(
        "05_resync_info",
        "Resync Info",
        "Reapply INFO metadata from selected builds?",
    )
    def action_05_resync_info(self, ids):
        tasks = []
        for label, build in self._iter_builds(ids):
            result = resync_build_metadata.delay(build.id, str(build))
            tasks.append({"id": result.id, "type": "resync_info", "label": label})
        if tasks:
            _store_task_tasks(tasks)
            count = len(tasks)
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
        "06_resync_file",
        "Resync File",
        "Recalculate md5 and size from selected build files?",
    )
    def action_06_resync_file(self, ids):
        tasks = []
        for label, build in self._iter_builds(ids):
            result = resync_build_file.delay(build.id, str(build))
            tasks.append({"id": result.id, "type": "resync_file", "label": label})
        if tasks:
            _store_task_tasks(tasks)
            count = len(tasks)
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

    @action(
        "01_activate", "Activate", "Are you sure you want to activate selected users?"
    )
    def action_01_activate(self, ids):
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
        "02_deactivate",
        "Deactivate",
        "Are you sure you want to deactivate selected users?",
    )
    def action_02_deactivate(self, ids):
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

    list_template = "admin/model/download_stats_list.html"

    column_list = (
        "code",
        "download_count",
        "recent_download_count",
        "target_download_count",
        "recent_target_download_count",
    )
    column_labels = {
        "download_count": "By NAS",
        "recent_download_count": "By NAS (90d)",
        "target_download_count": "By Build",
        "recent_target_download_count": "By Build (90d)",
    }
    column_sortable_list = (
        ("code", "code"),
        ("download_count", "download_count"),
        ("recent_download_count", "recent_download_count"),
        ("target_download_count", "target_download_count"),
        ("recent_target_download_count", "recent_target_download_count"),
    )
    column_formatters = {
        "download_count": lambda v, c, m, p: (
            f"{m.download_count:,}" if m.download_count else "0"
        ),
        "recent_download_count": lambda v, c, m, p: (
            f"{m.recent_download_count:,}" if m.recent_download_count else "0"
        ),
        "target_download_count": lambda v, c, m, p: (
            f"{m.target_download_count:,}" if m.target_download_count else "0"
        ),
        "recent_target_download_count": lambda v, c, m, p: (
            f"{m.recent_target_download_count:,}"
            if m.recent_target_download_count
            else "0"
        ),
    }


class FirmwareView(ModelView):
    """View for :class:`~spkrepo.models.Firmware`"""

    def __init__(self, **kwargs):
        super().__init__(Firmware, db, **kwargs)

    def is_accessible(self):
        return current_user.is_authenticated and current_user.has_role("package_admin")

    can_edit = False
    can_delete = False

    list_template = "admin/model/download_stats_list.html"

    column_list = (
        "version",
        "build",
        "type",
        "download_count",
        "recent_download_count",
        "target_download_count",
        "recent_target_download_count",
    )
    column_labels = {
        "download_count": "By NAS",
        "recent_download_count": "By NAS (90d)",
        "target_download_count": "By Build",
        "recent_target_download_count": "By Build (90d)",
    }
    column_sortable_list = (
        ("version", "version"),
        ("build", "build"),
        ("type", "type"),
        ("download_count", "download_count"),
        ("recent_download_count", "recent_download_count"),
        ("target_download_count", "target_download_count"),
        ("recent_target_download_count", "recent_target_download_count"),
    )
    column_formatters = {
        "download_count": lambda v, c, m, p: (
            f"{m.download_count:,}" if m.download_count else "0"
        ),
        "recent_download_count": lambda v, c, m, p: (
            f"{m.recent_download_count:,}" if m.recent_download_count else "0"
        ),
        "target_download_count": lambda v, c, m, p: (
            f"{m.target_download_count:,}" if m.target_download_count else "0"
        ),
        "recent_target_download_count": lambda v, c, m, p: (
            f"{m.recent_target_download_count:,}"
            if m.recent_target_download_count
            else "0"
        ),
    }

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
    list_template = "admin/model/package_list.html"

    @expose("/details/")
    def details_view(self):
        self._template_args["arch_breakdown"] = self._get_arch_breakdown()
        self._template_args["firmware_breakdown"] = self._get_firmware_breakdown()
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

    def _get_firmware_breakdown(self):
        pkg_id = request.args.get("id", type=int)
        if not pkg_id:
            return None
        cutoff = date.today() - timedelta(days=90)
        rows = db.session.execute(
            db.select(
                Firmware.version,
                Firmware.build,
                db.func.sum(DownloadStat.count).label("total"),
            )
            .join(Firmware, Firmware.build == DownloadStat.firmware_build)
            .where(
                db.and_(
                    DownloadStat.package_id == pkg_id,
                    DownloadStat.date >= cutoff,
                )
            )
            .group_by(Firmware.version, Firmware.build)
            .order_by(db.desc("total"))
            .limit(3)
        ).all()
        if not rows:
            return None
        grand_total = sum(total for _, _, total in rows)
        return [
            (f"{ver}-{build}", total, total / grand_total * 100)
            for ver, build, total in rows
        ]

    def get_query(self):
        # Explicitly outer-join PackageDownloadCounts so that Flask-Admin's
        # sort can reference its columns directly. Without this, sorting by
        # download_counts.download_count produces a join but NULLs (packages
        # with no download_stat rows) sort above real values in descending
        # order. The COALESCE in column_sortable_list below fixes that.
        q = (
            super()
            .get_query()
            .outerjoin(
                PackageDownloadCounts,
                Package.id == PackageDownloadCounts.package_id,
            )
        )
        archived = request.args.get("archived")
        if archived == "yes":
            q = q.filter(~Package.has_active_builds)
        elif archived == "no":
            q = q.filter(Package.has_active_builds)
        return q

    def get_count_query(self):
        return super().get_count_query()

    column_list = (
        "name",
        "author",
        "maintainers",
        "has_active_builds",
        "download_count",
        "recent_download_count",
        "last_download_date",
        "insert_date",
    )
    column_sortable_list = (
        ("name", "name"),
        ("author", "author.username"),
        ("insert_date", "insert_date"),
        ("download_count", db.func.coalesce(PackageDownloadCounts.download_count, 0)),
        (
            "recent_download_count",
            db.func.coalesce(PackageDownloadCounts.recent_download_count, 0),
        ),
        ("last_download_date", "last_download_date"),
    )
    column_formatters = {
        "insert_date": lambda v, c, m, p: (
            m.insert_date.strftime("%Y-%m-%d") if m.insert_date else None
        ),
        "has_active_builds": lambda v, c, m, p: (
            Markup('<i class="fa fa-check-circle text-success"></i>')
            if not m.has_active_builds
            else Markup('<i class="fa fa-times-circle text-danger"></i>')
        ),
        "download_count": lambda v, c, m, p: (
            f"{m.download_counts.download_count:,}"
            if m.download_counts and m.download_counts.download_count
            else "0"
        ),
        "recent_download_count": lambda v, c, m, p: (
            f"{m.download_counts.recent_download_count:,}"
            if m.download_counts and m.download_counts.recent_download_count
            else "0"
        ),
        "last_download_date": lambda v, c, m, p: (
            m.last_download_date.strftime("%Y-%m-%d") if m.last_download_date else None
        ),
    }

    column_formatters_detail = {
        "insert_date": lambda v, c, m, p: m.insert_date.strftime("%Y-%m-%d %H:%M:%S"),
        "has_active_builds": lambda v, c, m, p: (
            Markup('<i class="fa fa-check-circle text-success"></i>')
            if not m.has_active_builds
            else Markup('<i class="fa fa-times-circle text-danger"></i>')
        ),
    }
    column_labels = {
        "download_count": "Downloads",
        "recent_download_count": "Downloads (90d)",
        "last_download_date": "Last Download",
        "author.username": "Author",
        "has_active_builds": "Archived",
        "arch_breakdown": "Top Architectures (90d)",
        "firmware_breakdown": "Top Firmwares (90d)",
    }
    column_filters = (
        "name",
        "author.username",
    )
    column_details_list = (
        "name",
        "author",
        "maintainers",
        "has_active_builds",
        "insert_date",
        "download_count",
        "recent_download_count",
        "last_download_date",
        "arch_breakdown",
        "firmware_breakdown",
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
        for build in model.builds:
            if build.storage == "remote":
                storage_service.delete(build.path)
                storage_service.purge_cdn("/" + build.path)
            sidecar = os.path.join(
                current_app.config["DATA_PATH"], build.path + ".json"
            )
            if os.path.exists(sidecar):
                os.remove(sidecar)
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
        "all_builds_uploaded",
        "total_size",
        "insert_date",
    )
    column_labels = {
        "package.name": "Package Name",
        "version_string": "Version",
        "dependencies": "Dependencies",
        "all_builds_active": "All Active",
        "all_builds_uploaded": "All Uploaded",
        "install_wizard": "Install Wizard",
        "upgrade_wizard": "Upgrade Wizard",
        "total_size": "Total Size",
        "download_count": "Downloads",
        "recent_download_count": "Downloads (90d)",
    }
    column_filters = (
        "package.name",
        "upstream_version",
        "version",
        "beta",
        "startable",
        "all_builds_active",
        "all_builds_uploaded",
    )
    column_sortable_list = (
        ("package", "package.name"),
        ("upstream_version", "upstream_version"),
        ("version", "version"),
        ("beta", "beta"),
        ("insert_date", "insert_date"),
        ("all_builds_active", "all_builds_active"),
        ("all_builds_uploaded", "all_builds_uploaded"),
        ("startable", "startable"),
        ("total_size", "total_size"),
    )
    column_formatters = {
        "insert_date": lambda v, c, m, p: (
            m.insert_date.strftime("%Y-%m-%d") if m.insert_date else None
        ),
        "all_builds_active": _bool_formatter,
        "all_builds_uploaded": _bool_formatter,
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
        "all_builds_uploaded": _bool_formatter,
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
        "01_activate",
        "Activate",
        "Are you sure you want to activate selected versions' builds?",
    )
    def action_01_activate(self, ids):
        try:
            versions = get_query_for_ids(self.get_query(), self.model, ids).all()
            activated = []
            not_signed = []
            storage_ok = storage_service.storage_configured()
            for version in versions:
                for build in version.builds:
                    if not build.signed and not _detect_and_fix_signed(build):
                        not_signed.append(str(build))
                        continue
                    build.active = True
                    activated.append(build)
            db.session.commit()
            cache.delete("packages_versions")
            clear_catalog_cache()

            upload_tasks = []
            if storage_ok:
                for build in activated:
                    if build.storage == "local":
                        result = upload_to_storage.delay(build.id, str(build))
                        upload_tasks.append(
                            {"id": result.id, "type": "upload", "label": str(build)}
                        )
            if upload_tasks:
                _store_task_tasks(upload_tasks)
            if not_signed:
                flash(
                    "Build(s) have no signature and cannot be activated: "
                    + ", ".join(not_signed),
                    "warning",
                )
            if activated:
                if upload_tasks:
                    msg = (
                        "Build was successfully activated and queued for upload."
                        if len(activated) == 1
                        else (
                            f"{len(activated)} builds were successfully activated "
                            "and queued for upload."
                        )
                    )
                    flash(
                        Markup(msg + ' <a href="/admin/tasks/">View status</a>'), "info"
                    )
                else:
                    msg = (
                        "Build was successfully activated."
                        if len(activated) == 1
                        else f"{len(activated)} builds were successfully activated."
                    )
                    flash(msg, "success")
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception("Failed to activate versions' builds")
            flash(
                "Failed to activate versions' builds. Please check the logs.", "error"
            )

    @action(
        "02_deactivate",
        "Deactivate",
        "Are you sure you want to deactivate selected versions' builds?",
    )
    def action_02_deactivate(self, ids):
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
                    "Builds have been successfully deactivated for "
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
        "storage",
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
        "storage",
        "active",
    )
    column_sortable_list = (
        ("version.package", "version.package.name"),
        ("version.version", "version.version"),
        ("firmware_min", "firmware_min.build"),
        ("publisher", "publisher.username"),
        ("insert_date", "insert_date"),
        ("storage", "storage"),
        ("active", "active"),
    )
    column_formatters = {
        "insert_date": lambda v, c, m, p: (
            m.insert_date.strftime("%Y-%m-%d") if m.insert_date else None
        ),
        "size": lambda v, c, m, p: (
            f"{m.size / 1024 / 1024:.1f} MB" if m.size else None
        ),
        "storage": _storage_formatter,
        "active": _bool_formatter,
    }
    column_formatters_detail = {
        "insert_date": lambda v, c, m, p: m.insert_date.strftime("%Y-%m-%d %H:%M:%S"),
        "size": lambda v, c, m, p: (
            f"{m.size / 1024 / 1024:.1f} MB" if m.size else None
        ),
        "storage": _storage_formatter,
        "signed": _bool_formatter,
        "active": _bool_formatter,
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
        if model.storage == "remote":
            storage_service.delete(model.path)
            storage_service.purge_cdn("/" + model.path)
        sidecar = os.path.join(current_app.config["DATA_PATH"], model.path + ".json")
        if os.path.exists(sidecar):
            os.remove(sidecar)
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
        "01_activate", "Activate", "Are you sure you want to activate selected builds?"
    )
    def action_01_activate(self, ids):
        try:
            builds = get_query_for_ids(self.get_query(), self.model, ids).all()
            not_signed = []
            activated = []
            storage_ok = storage_service.storage_configured()
            for build in builds:
                if not build.signed and not _detect_and_fix_signed(build):
                    not_signed.append(str(build))
                    continue
                build.active = True
                activated.append(build)
            db.session.commit()
            cache.delete("packages_versions")
            clear_catalog_cache()

            upload_tasks = []
            if storage_ok:
                for build in activated:
                    if build.storage == "local":
                        result = upload_to_storage.delay(build.id, str(build))
                        upload_tasks.append(
                            {"id": result.id, "type": "upload", "label": str(build)}
                        )
            if upload_tasks:
                _store_task_tasks(upload_tasks)
            if not_signed:
                flash(
                    "Build(s) have no signature and cannot be activated: "
                    + ", ".join(not_signed),
                    "warning",
                )
            if activated:
                if upload_tasks:
                    a = len(activated)
                    msg = (
                        "Build was successfully activated and queued for upload."
                        if a == 1
                        else (
                            f"{a} builds were successfully activated "
                            "and queued for upload."
                        )
                    )
                    flash(
                        Markup(msg + ' <a href="/admin/tasks/">View status</a>'), "info"
                    )
                else:
                    msg = (
                        "Build was successfully activated."
                        if len(activated) == 1
                        else f"{len(activated)} builds were successfully activated."
                    )
                    flash(msg, "success")
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception("Failed to activate builds")
            flash("Failed to activate builds. Please check the logs.", "error")

    @action(
        "02_deactivate",
        "Deactivate",
        "Are you sure you want to deactivate selected builds?",
    )
    def action_02_deactivate(self, ids):
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

        cutoff = date.today() - timedelta(days=90)
        if is_privileged:
            recent_downloads = db.session.execute(
                db.select(db.func.coalesce(db.func.sum(DownloadStat.count), 0)).where(
                    DownloadStat.date >= cutoff
                )
            ).scalar()
        else:
            recent_downloads = db.session.execute(
                db.select(db.func.coalesce(db.func.sum(DownloadStat.count), 0))
                .join(Package, Package.id == DownloadStat.package_id)
                .join(Package.maintainers)
                .where(
                    db.and_(
                        User.id == current_user.id,
                        DownloadStat.date >= cutoff,
                    )
                )
            ).scalar()

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
            recent_downloads=recent_downloads,
        )


# ---------------------------------------------------------------------------
# Task status
# ---------------------------------------------------------------------------


class TaskStatusView(BaseView):
    """Admin panel page showing the status of queued background tasks."""

    def is_accessible(self):
        return current_user.is_authenticated and any(
            current_user.has_role(r) for r in ("developer", "package_admin", "admin")
        )

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("security.login"))

    @expose("/")
    def index(self):
        task_list = _get_task_ids()
        tasks = []
        pending_count = 0
        for entry in task_list:
            task_id = entry["id"] if isinstance(entry, dict) else entry
            task_type = entry.get("type", "") if isinstance(entry, dict) else ""
            task_label = (
                entry.get("label", task_id) if isinstance(entry, dict) else task_id
            )
            result = AsyncResult(task_id, app=celery)
            state = result.state
            info = result.info if result.ready() else None
            if state in ("PENDING", "STARTED", "RETRY"):
                pending_count += 1
            tasks.append(
                {
                    "id": task_id,
                    "type": task_type,
                    "label": task_label,
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

        task_list = _get_task_ids()
        tasks = []
        pending_count = 0
        for entry in task_list:
            task_id = entry["id"] if isinstance(entry, dict) else entry
            task_type = entry.get("type", "") if isinstance(entry, dict) else ""
            task_label = (
                entry.get("label", task_id) if isinstance(entry, dict) else task_id
            )
            result = AsyncResult(task_id, app=celery)
            state = result.state
            info = result.info if result.ready() else None
            label = (
                (info or {}).get("label", task_label)
                if isinstance(info, dict)
                else task_label
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
                    "type": task_type,
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
