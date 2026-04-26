# -*- coding: utf-8 -*-
import io
import os
import re
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
from wtforms import PasswordField
from wtforms.validators import Regexp

from ..ext import db
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
from ..utils import SPK


def _bool_formatter(v, c, m, p):
    value = getattr(m, p)
    if value is None:
        return Markup('<i class="fa fa-question-circle" style="color: #aaaaaa;"></i>')
    if value:
        return Markup('<i class="fa fa-check-circle" style="color: #27ae60;"></i>')
    return Markup('<i class="fa fa-times-circle" style="color: #e74c3c;"></i>')


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


class UserView(ModelView):
    """View for :class:`~spkrepo.models.User`"""

    def __init__(self, **kwargs):
        super(UserView, self).__init__(User, db.session, **kwargs)

    # Permissions
    def is_accessible(self):
        return current_user.is_authenticated and current_user.has_role("admin")

    can_create = False

    # View
    column_list = ("username", "email", "roles", "active", "confirmed_at")

    column_formatters = {
        "confirmed_at": lambda v, c, m, p: (
            m.confirmed_at.strftime("%Y-%m-%d %H:%M:%S") if m.confirmed_at else None
        )
    }

    # Form
    form_columns = ("username", "roles", "active")
    form_overrides = {"password": PasswordField}

    # Actions
    @action("activate", "Activate", "Are you sure you want to activate selected users?")
    def action_activate(self, ids):
        try:
            users = get_query_for_ids(self.get_query(), self.model, ids).all()
            for user in users:
                user.active = True
            self.session.commit()
            flash(
                "User was successfully activated."
                if len(users) == 1
                else f"{len(users)} users were successfully activated."
            )
        except Exception:  # pragma: no cover
            self.session.rollback()
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
            self.session.commit()
            flash(
                "User was successfully deactivated."
                if len(users) == 1
                else f"{len(users)} users were successfully deactivated."
            )
        except Exception:  # pragma: no cover
            self.session.rollback()
            current_app.logger.exception("Failed to deactivate users")
            flash("Failed to deactivate users. Please check the logs.", "error")


class ArchitectureView(ModelView):
    """View for :class:`~spkrepo.models.Architecture`"""

    def __init__(self, **kwargs):
        super(ArchitectureView, self).__init__(Architecture, db.session, **kwargs)

    # Permissions
    def is_accessible(self):
        return current_user.is_authenticated and current_user.has_role("package_admin")

    can_edit = False

    can_delete = False

    # Form
    form_excluded_columns = "builds"


class FirmwareView(ModelView):
    """View for :class:`~spkrepo.models.Firmware`"""

    def __init__(self, **kwargs):
        super(FirmwareView, self).__init__(Firmware, db.session, **kwargs)

    # Permissions
    def is_accessible(self):
        return current_user.is_authenticated and current_user.has_role("package_admin")

    can_edit = False

    can_delete = False

    # Form
    form_columns = ("version", "build", "type")
    form_args = {
        "version": {"validators": [Regexp(SPK.firmware_version_re)]},
        "type": {"validators": [Regexp(SPK.firmware_type_re)]},
    }


class ServiceView(ModelView):
    """View for :class:`~spkrepo.models.Service`"""

    def __init__(self, **kwargs):
        super(ServiceView, self).__init__(Service, db.session, **kwargs)

    # Permissions
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
        super(ScreenshotView, self).__init__(Screenshot, db.session, **kwargs)

    # Permissions
    def is_accessible(self):
        return current_user.is_authenticated and current_user.has_role("package_admin")

    can_edit = False

    # View
    column_labels = {
        "package.name": "Package Name",
        "path": "Screenshot",
    }

    def _display(view, context, model, name):
        safe_url = Markup.escape(url_for("nas.data", path=model.path))
        return Markup(
            f'<img src="{safe_url}" alt="screenshot" height="100" width="100">'
        )

    column_formatters = {"path": _display}
    column_sortable_list = (("package", "package.name"),)
    column_default_sort = "package.name"
    column_filters = ("package.name",)

    # Hooks
    def on_model_delete(self, model):
        build_path = os.path.join(current_app.config["DATA_PATH"], model.path)
        if os.path.exists(build_path):
            os.remove(build_path)

    # Form
    form_overrides = {"path": ImageUploadField}
    form_args = {
        "path": {
            "label": "Screenshot",
            "namegen": screenshot_namegen,
            "base_path": lambda: current_app.config["DATA_PATH"],
        }
    }


firmware_re = re.compile(r"^(?P<version>\d\.\d)-(?P<build>\d{3,6})$")
version_re = re.compile(r"^(?P<upstream_version>.*)-(?P<version>\d+)$")


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


class PackageView(ModelView):
    """View for :class:`~spkrepo.models.Package`"""

    def __init__(self, **kwargs):
        super(PackageView, self).__init__(Package, db.session, **kwargs)

    # Permissions
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

    # Hooks
    def on_model_change(self, form, model, is_created):
        if is_created:
            package_path = os.path.join(current_app.config["DATA_PATH"], model.name)
            if not os.path.exists(package_path):
                os.mkdir(package_path)

    def on_model_delete(self, model):
        package_path = os.path.join(current_app.config["DATA_PATH"], model.name)
        if os.path.exists(package_path):
            shutil.rmtree(package_path)

    # View
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

    # Form
    form_columns = ("name", "author", "maintainers")
    form_args = {"name": {"validators": [Regexp(SPK.package_re)]}}


class VersionView(ModelView):
    """View for :class:`~spkrepo.models.Version`"""

    def __init__(self, **kwargs):
        super(VersionView, self).__init__(Version, db.session, **kwargs)

    # Permissions
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

    @property
    def can_sign(self):
        return current_user.has_role("admin")

    @property
    def can_unsign(self):
        return current_user.has_role("admin")

    @property
    def can_resync_info(self):
        return current_user.has_role("admin")

    @property
    def can_resync_file(self):
        return current_user.has_role("admin")

    # Hooks
    def on_model_delete(self, model):
        version_path = os.path.join(
            current_app.config["DATA_PATH"], model.package.name, str(model.version)
        )
        if os.path.exists(version_path):
            shutil.rmtree(version_path)

    # Define a formatter to truncate long text
    def _truncate_formatter(view, context, model, name):
        text = getattr(model, name)
        if not text:
            return text
        if len(text) > 250:
            return Markup(f"{Markup.escape(text[:250])}...")
        return Markup.escape(text)

    # View
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

    # Custom queries
    def get_query(self):
        if not current_user.has_role("package_admin"):
            return (
                super(VersionView, self)
                .get_query()
                .join(self.model.package)
                .join(Package.maintainers)
                .filter(User.id == current_user.id)
            )
        return super(VersionView, self).get_query()

    def get_count_query(self):
        if not current_user.has_role("package_admin"):
            return (
                super(VersionView, self)
                .get_count_query()
                .join(self.model.package)
                .join(Package.maintainers)
                .filter(User.id == current_user.id)
            )
        return super(VersionView, self).get_count_query()

    # Actions
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
            self.session.commit()
            flash(
                "Builds on version were successfully activated."
                if len(versions) == 1
                else (
                    "Builds have been successfully activated for "
                    f"{len(versions)} versions."
                )
            )
        except Exception:  # pragma: no cover
            self.session.rollback()
            current_app.logger.exception("Failed to activate versions' builds")
            flash("Failed to activate versions' builds. Please check the logs.", "error")

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
            self.session.commit()
            flash(
                "Builds on version were successfully deactivated."
                if len(versions) == 1
                else (
                    "Builds have been successfully deactivated for "
                    f"{len(versions)} versions."
                )
            )
        except Exception:  # pragma: no cover
            self.session.rollback()
            current_app.logger.exception("Failed to deactivate versions' builds")
            flash("Failed to deactivate versions' builds. Please check the logs.", "error")

    @action("sign", "Sign", "Are you sure you want to sign selected builds?")
    def action_sign(self, ids):
        try:
            versions = get_query_for_ids(self.get_query(), self.model, ids).all()
            already_signed = []
            success = []
            failed = []
            for version in versions:
                for build in version.builds:
                    filename = os.path.basename(build.path)
                    with io.open(
                        os.path.join(current_app.config["DATA_PATH"], build.path), "rb+"
                    ) as f:
                        spk = SPK(f)
                        if spk.signature is not None:
                            already_signed.append(filename)
                            continue
                        try:
                            spk.sign(
                                current_app.config["GNUPG_TIMESTAMP_URL"],
                                current_app.config["GNUPG_PATH"],
                            )
                            _resync_build_file(build)
                            self.session.commit()
                            success.append(filename)
                        except Exception:
                            current_app.logger.exception("Failed to sign build %s", filename)
                            self.session.rollback()
                            failed.append(filename)
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
            versions = get_query_for_ids(self.get_query(), self.model, ids).all()
            not_signed = []
            success = []
            failed = []
            for version in versions:
                for build in version.builds:
                    filename = os.path.basename(build.path)
                    with io.open(
                        os.path.join(current_app.config["DATA_PATH"], build.path), "rb+"
                    ) as f:
                        spk = SPK(f)
                        if spk.signature is None:
                            not_signed.append(filename)
                            continue
                        try:
                            spk.unsign()
                            _resync_build_file(build)
                            self.session.commit()
                            success.append(filename)
                        except Exception:
                            current_app.logger.exception("Failed to unsign build %s", filename)
                            self.session.rollback()
                            failed.append(filename)
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
        "Reapply INFO metadata from builds on selected versions?",
    )
    def action_resync_info(self, ids):
        successes = []
        failures = []

        versions = get_query_for_ids(self.get_query(), self.model, ids).all()
        for version in versions:
            for build in version.builds:
                filename = os.path.basename(build.path) if build.path else str(build.id)
                try:
                    _resync_build_metadata(self.session, build)
                    self.session.commit()
                    successes.append(filename)
                except Exception as exc:  # pragma: no cover
                    self.session.rollback()
                    failures.append((filename, str(exc)))

        _flash_action_results(successes, failures, item_label="build")

    @action(
        "resync_file",
        "Resync File",
        "Recalculate md5 and size from build files on selected versions?",
    )
    def action_resync_file(self, ids):
        successes = []
        failures = []

        versions = get_query_for_ids(self.get_query(), self.model, ids).all()
        for version in versions:
            for build in version.builds:
                filename = os.path.basename(build.path) if build.path else str(build.id)
                try:
                    _resync_build_file(build)
                    self.session.commit()
                    successes.append(filename)
                except Exception as exc:
                    self.session.rollback()
                    failures.append((filename, str(exc)))

        _flash_action_results(successes, failures, item_label="build")

    def is_action_allowed(self, name):
        if name == "resync_info" and not self.can_resync_info:
            return False
        if name == "resync_file" and not self.can_resync_file:
            return False
        if name == "sign" and not self.can_sign:
            return False
        if name == "unsign" and not self.can_unsign:
            return False

        return super(VersionView, self).is_action_allowed(name)

    def handle_action(self, return_view=None):
        action = request.form.get("action")
        if action == "resync_info" and not self.can_resync_info:
            abort(403)
        if action == "resync_file" and not self.can_resync_file:
            abort(403)
        if action == "sign" and not self.can_sign:
            abort(403)
        if action == "unsign" and not self.can_unsign:
            abort(403)
        return super(VersionView, self).handle_action(return_view)


class BuildView(ModelView):
    """View for :class:`~spkrepo.models.Build`"""

    def __init__(self, **kwargs):
        super(BuildView, self).__init__(Build, db.session, **kwargs)

    # Permissions
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

    @property
    def can_sign(self):
        return current_user.has_role("admin")

    @property
    def can_unsign(self):
        return current_user.has_role("admin")

    @property
    def can_resync_info(self):
        return current_user.has_role("admin")

    @property
    def can_resync_file(self):
        return current_user.has_role("admin")

    # View
    column_list = (
        "version.package",
        "version.version",
        "architectures",
        "firmware_min",
        "firmware_max",
        "size",
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
        "firmware_max.version",
        "size",
        "active",
    )
    column_sortable_list = (
        ("version.package", "version.package.name"),
        ("version.version", "version.version"),
        ("firmware_min", "firmware_min.build"),
        ("firmware_max", "firmware_max.build"),
        ("active", "active"),
        ("size", "size"),
    )

    column_formatters = {
        "insert_date": lambda v, c, m, p: m.insert_date.strftime("%Y-%m-%d %H:%M:%S"),
        "size": lambda v, c, m, p: (
            f"{m.size / 1024 / 1024:.1f} MB" if m.size else None
        ),
        "active": _bool_formatter,
    }
    column_default_sort = (Build.insert_date, True)

    # Custom queries
    def get_query(self):
        if not current_user.has_role("package_admin"):
            return (
                super(BuildView, self)
                .get_query()
                .join(self.model.version)
                .join(Version.package)
                .join(Package.maintainers)
                .filter(User.id == current_user.id)
            )
        return super(BuildView, self).get_query()

    def get_count_query(self):
        if not current_user.has_role("package_admin"):
            return (
                super(BuildView, self)
                .get_count_query()
                .join(self.model.version)
                .join(Version.package)
                .join(Package.maintainers)
                .filter(User.id == current_user.id)
            )
        return super(BuildView, self).get_count_query()

    # Hooks
    def on_model_delete(self, model):
        build_path = os.path.join(current_app.config["DATA_PATH"], model.path)
        if os.path.exists(build_path):
            os.remove(build_path)

    # Actions
    @action(
        "activate", "Activate", "Are you sure you want to activate selected builds?"
    )
    def action_activate(self, ids):
        try:
            builds = get_query_for_ids(self.get_query(), self.model, ids).all()
            for build in builds:
                build.active = True
            self.session.commit()
            flash(
                "Build was successfully activated."
                if len(builds) == 1
                else f"{len(builds)} builds were successfully activated."
            )
        except Exception:  # pragma: no cover
            self.session.rollback()
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
            self.session.commit()
            flash(
                "Build was successfully deactivated."
                if len(builds) == 1
                else f"{len(builds)} builds were successfully deactivated."
            )
        except Exception:  # pragma: no cover
            self.session.rollback()
            current_app.logger.exception("Failed to deactivate builds")
            flash("Failed to deactivate builds. Please check the logs.", "error")

    @action("sign", "Sign", "Are you sure you want to sign selected builds?")
    def action_sign(self, ids):
        try:
            builds = get_query_for_ids(self.get_query(), self.model, ids).all()
            already_signed = []
            success = []
            failed = []
            for build in builds:
                filename = os.path.basename(build.path)
                with io.open(
                    os.path.join(current_app.config["DATA_PATH"], build.path), "rb+"
                ) as f:
                    spk = SPK(f)
                    if spk.signature is not None:
                        already_signed.append(filename)
                        continue
                    try:
                        spk.sign(
                            current_app.config["GNUPG_TIMESTAMP_URL"],
                            current_app.config["GNUPG_PATH"],
                        )
                        _resync_build_file(build)
                        self.session.commit()
                        success.append(filename)
                    except Exception:
                        current_app.logger.exception(
                            "Failed to sign build %s", filename
                        )
                        self.session.rollback()
                        failed.append(filename)
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
            builds = get_query_for_ids(self.get_query(), self.model, ids).all()
            not_signed = []
            success = []
            failed = []
            for build in builds:
                filename = os.path.basename(build.path)
                with io.open(
                    os.path.join(current_app.config["DATA_PATH"], build.path), "rb+"
                ) as f:
                    spk = SPK(f)
                    if spk.signature is None:
                        not_signed.append(filename)
                        continue
                    try:
                        spk.unsign()
                        _resync_build_file(build)
                        self.session.commit()
                        success.append(filename)
                    except Exception:
                        current_app.logger.exception("Failed to unsign build %s", filename)
                        self.session.rollback()
                        failed.append(filename)
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
        successes = []
        failures = []

        for build_id in ids:
            try:
                build = self.session.get(self.model, int(build_id))
            except (TypeError, ValueError):
                continue

            if build is None:
                continue

            filename = os.path.basename(build.path) if build.path else str(build_id)
            try:
                _resync_build_metadata(self.session, build)
                self.session.commit()
                successes.append(filename)
            except Exception as exc:  # pragma: no cover
                self.session.rollback()
                failures.append((filename, str(exc)))

        _flash_action_results(successes, failures, item_label="build")

    @action(
        "resync_file",
        "Resync File",
        "Recalculate md5 and size from selected build files?",
    )
    def action_resync_file(self, ids):
        successes = []
        failures = []

        for build_id in ids:
            try:
                build = self.session.get(self.model, int(build_id))
            except (TypeError, ValueError):
                continue

            if build is None:
                continue

            filename = os.path.basename(build.path) if build.path else str(build_id)
            try:
                _resync_build_file(build)
                self.session.commit()
                successes.append(filename)
            except Exception as exc:
                self.session.rollback()
                failures.append((filename, str(exc)))

        _flash_action_results(successes, failures, item_label="build")

    def is_action_allowed(self, name):
        if name == "resync_info" and not self.can_resync_info:
            return False
        if name == "resync_file" and not self.can_resync_file:
            return False
        if name == "sign" and not self.can_sign:
            return False
        if name == "unsign" and not self.can_unsign:
            return False

        return super(BuildView, self).is_action_allowed(name)

    def handle_action(self, return_view=None):
        action = request.form.get("action")
        if action == "resync_info" and not self.can_resync_info:
            abort(403)
        if action == "resync_file" and not self.can_resync_file:
            abort(403)
        if action == "sign" and not self.can_sign:
            abort(403)
        if action == "unsign" and not self.can_unsign:
            abort(403)
        return super(BuildView, self).handle_action(return_view)


class IndexView(AdminIndexView):
    @expose("/")
    def index(self):
        if not current_user.is_authenticated:
            return redirect(url_for("security.login"))
        if not any(map(current_user.has_role, ("developer", "package_admin", "admin"))):
            abort(403)
        return super(IndexView, self).index()
