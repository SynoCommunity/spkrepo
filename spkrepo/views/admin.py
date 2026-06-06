# -*- coding: utf-8 -*-
import io
import os
import shutil

from flask import abort, current_app, flash, redirect, request, url_for
from flask_admin import AdminIndexView, expose
from flask_admin.actions import action
from flask_admin.contrib.sqla import ModelView
from flask_admin.contrib.sqla.form import get_form
from flask_admin.contrib.sqla.tools import get_query_for_ids
from flask_admin.form import ImageUploadField
from flask_security import current_user
from markupsafe import Markup
from sqlalchemy.exc import SQLAlchemyError
from wtforms import PasswordField
from wtforms.validators import Regexp

from ..ext import cache, db
from ..models import (
    Architecture,
    Build,
    BuildManifest,
    Description,
    DisplayName,
    Firmware,
    Icon,
    Language,
    Package,
    Screenshot,
    Service,
    User,
    Version,
)
from ..utils import SPK, firmware_re, version_re

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


# ---------------------------------------------------------------------------
# SPK helpers
# ---------------------------------------------------------------------------


def _resolve_firmware(session, value, allow_none=False):
    if not value:
        if allow_none:
            return None
        raise ValueError("Missing firmware information in INFO")

    match = firmware_re.match(value)
    if not match:
        raise ValueError(f"Invalid firmware value: {value}")

    firmware = Firmware.find(int(match.group("build")))
    if firmware is None:
        raise ValueError(f"Unknown firmware: {value}")

    return session.merge(firmware, load=False)


def _apply_info_from_spk(session, build, spk, md5_hash):
    info = spk.info
    package = build.version.package

    if info.get("package") != package.name:
        raise ValueError("INFO package does not match build package")

    version_match = version_re.match(info.get("version", ""))
    if not version_match:
        raise ValueError("Invalid INFO version value")

    version_number = int(version_match.group("version"))
    if version_number != build.version.version:
        raise ValueError("INFO version does not match build version")

    version = build.version
    version.upstream_version = version_match.group("upstream_version")
    version.changelog = info.get("changelog")
    version.report_url = info.get("report_url")
    version.distributor = info.get("distributor")
    version.distributor_url = info.get("distributor_url")
    version.maintainer = info.get("maintainer")
    version.maintainer_url = info.get("maintainer_url")
    version.install_wizard = "install" in spk.wizards
    version.upgrade_wizard = "upgrade" in spk.wizards

    startable = True  # default per Synology docs
    if info.get("startable") is False or info.get("ctl_stop") is False:
        startable = False
    version.startable = startable

    version.license = spk.license

    install_services = info.get("install_dep_services")
    services = []
    if install_services:
        for service_code in install_services.split():
            service = Service.find(service_code)
            if service is None:
                raise ValueError(f"Unknown dependent service: {service_code}")
            services.append(service)
    version.service_dependencies = services

    version.displaynames.clear()
    default_display = info.get("displayname")
    if default_display:
        language = Language.find("enu")
        if language is None:
            raise ValueError("Language 'enu' is not defined")
        version.displaynames[language.code] = DisplayName(
            language=language, displayname=default_display
        )

    for key, value in info.items():
        if key.startswith("displayname_"):
            language_code = key.split("_", 1)[1]
            language = Language.find(language_code)
            if language is None:
                raise ValueError(f"Unknown INFO displayname language: {language_code}")
            version.displaynames[language.code] = DisplayName(
                language=language, displayname=value
            )

    version.descriptions.clear()
    default_description = info.get("description")
    if default_description:
        language = Language.find("enu")
        if language is None:
            raise ValueError("Language 'enu' is not defined")
        version.descriptions[language.code] = Description(
            language=language, description=default_description
        )

    for key, value in info.items():
        if key.startswith("description_"):
            language_code = key.split("_", 1)[1]
            language = Language.find(language_code)
            if language is None:
                raise ValueError(f"Unknown INFO description language: {language_code}")
            version.descriptions[language.code] = Description(
                language=language, description=value
            )

    existing_icons = dict(version.icons)
    new_sizes = set(spk.icons.keys()) if spk.icons else set()
    for stale_size in set(existing_icons) - new_sizes:
        del version.icons[stale_size]

    if spk.icons:
        version_path = os.path.join(
            current_app.config["DATA_PATH"], package.name, str(version.version)
        )
        os.makedirs(version_path, exist_ok=True)
        for size, icon_stream in spk.icons.items():
            icon_stream.seek(0)
            icon_path = os.path.join(
                package.name, str(version.version), f"icon_{size}.png"
            )
            icon = version.icons.get(size)
            if icon is None:
                icon = Icon(path=icon_path, size=size)
                version.icons[size] = icon
            else:
                icon.path = icon_path
            icon.save(icon_stream)

    arch_value = info.get("arch")
    if not arch_value:
        raise ValueError("Missing 'arch' field in INFO")
    architectures = []
    for info_arch in arch_value.split():
        architecture = Architecture.find(info_arch, syno=True)
        if architecture is None:
            raise ValueError(f"Unknown architecture: {info_arch}")
        architectures.append(session.merge(architecture, load=False))
    build.architectures = architectures

    firmware = _resolve_firmware(
        session, info.get("firmware") or info.get("os_min_ver")
    )
    build.firmware_min = firmware

    firmware_max_value = info.get("os_max_ver")
    firmware_max = _resolve_firmware(session, firmware_max_value, allow_none=True)
    if firmware_max and firmware_max.build < firmware.build:
        raise ValueError(
            "Maximum firmware must be greater than or equal to minimum firmware"
        )
    build.firmware_max = firmware_max

    build.checksum = info.get("checksum")
    build.md5 = md5_hash

    manifest = build.buildmanifest
    if manifest is None:
        manifest = BuildManifest()
        build.buildmanifest = manifest

    manifest.dependencies = info.get("install_dep_packages")
    manifest.conf_dependencies = spk.conf_dependencies
    manifest.conflicts = info.get("install_conflict_packages")
    manifest.conf_conflicts = spk.conf_conflicts
    manifest.conf_privilege = spk.conf_privilege
    manifest.conf_resource = spk.conf_resource

    session.flush()


def _resync_build_file(build):
    """Recalculate md5 and size from the build file on disk."""
    if not build.path:
        raise ValueError("Build has no file path")
    build.md5 = build.calculate_md5()
    build.size = build.calculate_size()


def _resync_build_metadata(session, build):
    if not build.path:
        raise ValueError("Build has no file path")

    file_path = os.path.join(current_app.config["DATA_PATH"], build.path)
    with io.open(file_path, "rb") as stream:
        spk = SPK(stream)
        md5 = spk.calculate_md5()
        _apply_info_from_spk(session, build, spk, md5)


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
        successes, failures = [], []
        for label, build in self._iter_builds(ids):
            try:
                _resync_build_metadata(db.session, build)
                db.session.commit()
                successes.append(label)
            except Exception as exc:  # pragma: no cover
                db.session.rollback()
                failures.append((label, str(exc)))
        _flash_action_results(successes, failures, item_label="build")

    @action(
        "resync_file",
        "Resync File",
        "Recalculate md5 and size from selected build files?",
    )
    def action_resync_file(self, ids):
        successes, failures = [], []
        for label, build in self._iter_builds(ids):
            try:
                _resync_build_file(build)
                db.session.commit()
                successes.append(label)
            except Exception as exc:
                db.session.rollback()
                failures.append((label, str(exc)))
        _flash_action_results(successes, failures, item_label="build")


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

    def after_model_delete(self, model):
        cache.delete("packages_versions")

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

    def after_model_delete(self, model):
        cache.delete("packages_versions")

    column_list = (
        "name",
        "author",
        "maintainers",
        "download_count",
        "recent_download_count",
        "insert_date",
    )
    column_sortable_list = (
        ("name", "name"),
        ("author", "author.username"),
        ("insert_date", "insert_date"),
        ("download_count", "download_count"),
        ("recent_download_count", "recent_download_count"),
    )
    column_formatters = {
        "insert_date": lambda v, c, m, p: m.insert_date.strftime("%Y-%m-%d %H:%M:%S"),
        "download_count": lambda v, c, m, p: (
            f"{m.download_count:,}" if m.download_count else "0"
        ),
        "recent_download_count": lambda v, c, m, p: (
            f"{m.recent_download_count:,}" if m.recent_download_count else "0"
        ),
    }
    column_labels = {
        "download_count": "Downloads",
        "recent_download_count": "Recent Downloads",
        "author.username": "Author",
    }
    column_filters = ("name", "author.username")

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
        "insert_date": lambda v, c, m, p: m.insert_date.strftime("%Y-%m-%d %H:%M:%S"),
        "all_builds_active": _bool_formatter,
        "startable": _bool_formatter,
        "beta": _bool_formatter,
        "total_size": lambda v, c, m, p: (
            f"{m.total_size / 1024 / 1024:.1f} MB" if m.total_size else None
        ),
    }
    column_formatters_detail = {
        "install_wizard": _bool_formatter,
        "upgrade_wizard": _bool_formatter,
        "startable": _bool_formatter,
        "license": _truncate_formatter,
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
        "insert_date": lambda v, c, m, p: m.insert_date.strftime("%Y-%m-%d %H:%M:%S"),
        "size": lambda v, c, m, p: (
            f"{m.size / 1024 / 1024:.1f} MB" if m.size else None
        ),
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
        build_path = os.path.join(current_app.config["DATA_PATH"], model.path)
        if os.path.exists(build_path):
            os.remove(build_path)

    def after_model_change(self, form, model, is_created):
        cache.delete("packages_versions")

    def after_model_delete(self, model):
        cache.delete("packages_versions")

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
