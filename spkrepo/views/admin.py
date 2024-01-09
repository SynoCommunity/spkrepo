# -*- coding: utf-8 -*-
import io
import os
import shutil

from flask import abort, current_app, flash, redirect, url_for
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
from ..models import Architecture, Build, Firmware, Package, Screenshot, User, Version
from ..utils import SPK


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
                else "%d users were successfully activated." % len(users)
            )
        except Exception as e:  # pragma: no cover
            self.session.rollback()
            flash("Failed to activate users. %s" % str(e), "error")

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
                else "%d users were successfully deactivated." % len(users)
            )
        except Exception as e:  # pragma: no cover
            self.session.rollback()
            flash("Failed to deactivate users. %s" % str(e), "error")


class ArchitectureView(ModelView):
    """View for :class:`~spkrepo.models.Architecture`"""

    def __init__(self, **kwargs):
        super(ArchitectureView, self).__init__(Architecture, db.session, **kwargs)

    # Permissions
    def is_accessible(self):
        return current_user.is_authenticated and current_user.has_role("package_admin")

    can_edit = False

    can_delete = False


class FirmwareView(ModelView):
    """View for :class:`~spkrepo.models.Firmware`"""

    def __init__(self, **kwargs):
        super(FirmwareView, self).__init__(Firmware, db.session, **kwargs)

    # Permissions
    def is_accessible(self):
        return current_user.is_authenticated and current_user.has_role("package_admin")

    can_edit = False

    can_delete = False


def screenshot_namegen(obj, file_data):
    pattern = "screenshot_%0d%s"
    ext = os.path.splitext(file_data.filename)[1]
    i = 1
    while os.path.exists(
        os.path.join(
            current_app.config["DATA_PATH"], obj.package.name, pattern % (i, ext)
        )
    ):
        i += 1
    return os.path.join(obj.package.name, pattern % (i, ext))


# TODO: Not necessary with Flask-Admin>1.0.8
# see https://github.com/mrjoes/flask-admin/pull/705
class SpkrepoImageUploadField(ImageUploadField):
    def _get_path(self, filename):
        if not self.base_path:  # pragma: no cover
            raise ValueError("FileUploadField field requires base_path to be set.")

        if callable(self.base_path):
            return os.path.join(self.base_path(), filename)
        return os.path.join(self.base_path, filename)  # pragma: no cover


class ScreenshotView(ModelView):
    """View for :class:`~spkrepo.models.Screenshot`"""

    def __init__(self, **kwargs):
        super(ScreenshotView, self).__init__(Screenshot, db.session, **kwargs)

    # Permissions
    def is_accessible(self):
        return current_user.is_authenticated and current_user.has_role("package_admin")

    # View
    def _display(view, context, model, name):
        return Markup(
            '<img src="%s" alt="screenshot" height="100" width="100">'
            % url_for("nas.data", path=model.path)
        )

    column_formatters = {"path": _display}
    column_sortable_list = (("package", "package.name"),)
    column_default_sort = (Package.name, True)
    column_filters = ("package.name",)

    # Form
    form_overrides = {"path": SpkrepoImageUploadField}
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
    column_list = ("name", "author", "maintainers", "insert_date")
    column_sortable_list = (
        ("name", "name"),
        ("author", "author.username"),
        ("insert_date", "insert_date"),
    )

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

    @property
    def can_delete(self):
        return current_user.has_role("admin")

    @property
    def can_sign(self):
        return current_user.has_role("admin")

    @property
    def can_unsign(self):
        return current_user.has_role("admin")

    # Hooks
    def on_model_delete(self, model):
        version_path = os.path.join(
            current_app.config["DATA_PATH"], model.package.name, str(model.version)
        )
        if os.path.exists(version_path):
            shutil.rmtree(version_path)

    # View
    column_list = (
        "package",
        "upstream_version",
        "version",
        "beta",
        "service_dependencies",
        "insert_date",
        "all_builds_active",
        "install_wizard",
        "upgrade_wizard",
        "startable",
    )
    column_labels = {
        "version_string": "Version",
        "dependencies": "Dependencies",
        "service_dependencies": "Services",
    }
    column_filters = ("package.name", "version", "upstream_version")
    column_sortable_list = (
        ("package", "package.name"),
        ("upstream_version", "upstream_version"),
        ("version", "version"),
        ("insert_date", "insert_date"),
        ("install_wizard", "install_wizard"),
        ("upgrade_wizard", "upgrade_wizard"),
        ("startable", "startable"),
    )
    # TODO: Add beta and all_builds_active with Flask-Admin>1.0.8
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
                else "Builds have been successfully activated for %d versions."
                % len(versions)
            )
        except Exception as e:  # pragma: no cover
            self.session.rollback()
            flash("Failed to activate versions' builds. %s" % str(e), "error")

    @action(
        "deactivate",
        "Deactivate",
        "Are you sure you want to deactivate selected  versions' builds?",
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
                else "Builds have been successfully deactivated for %d versions."
                % len(versions)
            )
        except Exception as e:  # pragma: no cover
            self.session.rollback()
            flash("Failed to deactivate versions' builds. %s" % str(e), "error")

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
                            success.append(filename)
                        except Exception:
                            failed.append(filename)
                if failed:
                    if len(failed) == 1:
                        flash("Failed to sign build %s" % failed[0], "error")
                    else:
                        flash(
                            "Failed to sign %d builds: %s"
                            % (len(failed), ", ".join(failed)),
                            "error",
                        )
                if already_signed:
                    if len(already_signed) == 1:
                        flash("Build %s already signed" % already_signed[0], "info")
                    else:
                        flash(
                            "%d builds already signed: %s"
                            % (len(already_signed), ", ".join(already_signed)),
                            "info",
                        )
                if success:
                    if len(success) == 1:
                        flash("Build %s successfully signed" % success[0])
                    else:
                        flash(
                            "Successfully signed %d builds: %s"
                            % (len(success), ", ".join(success))
                        )
        except Exception as e:  # pragma: no cover
            flash("Failed to sign builds. %s" % str(e), "error")

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
                            success.append(filename)
                        except Exception:
                            failed.append(filename)
                if failed:
                    if len(failed) == 1:
                        flash("Failed to unsign build %s" % failed[0], "error")
                    else:
                        flash(
                            "Failed to unsign %d builds: %s"
                            % (len(failed), ", ".join(failed)),
                            "error",
                        )
                if not_signed:
                    if len(not_signed) == 1:
                        flash("Build %s not signed" % not_signed[0], "info")
                    else:
                        flash(
                            "%d builds not signed: %s"
                            % (len(not_signed), ", ".join(not_signed)),
                            "info",
                        )
                if success:
                    if len(success) == 1:
                        flash("Build %s successfully unsigned" % success[0])
                    else:
                        flash(
                            "Successfully unsigned %d builds: %s"
                            % (len(success), ", ".join(success))
                        )
        except Exception as e:  # pragma: no cover
            flash("Failed to unsign builds. %s" % str(e), "error")

    def is_action_allowed(self, name):
        if name == "sign" and not self.can_sign:
            return False
        if name == "unsign" and not self.can_unsign:
            return False

        return super(VersionView, self).is_action_allowed(name)


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

    @property
    def can_delete(self):
        return current_user.has_role("admin")

    @property
    def can_sign(self):
        return current_user.has_role("admin")

    @property
    def can_unsign(self):
        return current_user.has_role("admin")

    # View
    column_list = (
        "version.package",
        "version.upstream_version",
        "version.version",
        "architectures",
        "firmware",
        "publisher",
        "insert_date",
        "active",
    )
    column_labels = {
        "version.package": "Package",
        "version.upstream_version": "Upstream Version",
        "version.version": "Version",
    }
    column_filters = (
        "version.package.name",
        "version.upstream_version",
        "version.version",
        "publisher.username",
    )
    column_sortable_list = (
        ("version.upstream_version", "version.upstream_version"),
        ("version.version", "version.version"),
        ("firmware", "firmware.build"),
        ("publisher", "publisher.username"),
        ("insert_date", "insert_date"),
        ("active", "active"),
    )
    # TODO: Add version.package with Flask-Admin>1.0.8
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
                else "%d builds were successfully activated." % len(builds)
            )
        except Exception as e:  # pragma: no cover
            self.session.rollback()
            flash("Failed to activate builds. %s" % str(e), "error")

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
                else "%d builds were successfully deactivated." % len(builds)
            )
        except Exception as e:  # pragma: no cover
            self.session.rollback()
            flash("Failed to deactivate builds. %s" % str(e), "error")

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
                        success.append(filename)
                    except Exception:
                        failed.append(filename)
            if failed:
                if len(failed) == 1:
                    flash("Failed to sign build %s" % failed[0], "error")
                else:
                    flash(
                        "Failed to sign %d builds: %s"
                        % (len(failed), ", ".join(failed)),
                        "error",
                    )
            if already_signed:
                if len(already_signed) == 1:
                    flash("Build %s already signed" % already_signed[0], "info")
                else:
                    flash(
                        "%d builds already signed: %s"
                        % (len(already_signed), ", ".join(already_signed)),
                        "info",
                    )
            if success:
                if len(success) == 1:
                    flash("Build %s successfully signed" % success[0])
                else:
                    flash(
                        "Successfully signed %d builds: %s"
                        % (len(success), ", ".join(success))
                    )
        except Exception as e:  # pragma: no cover
            flash("Failed to sign builds. %s" % str(e), "error")

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
                        success.append(filename)
                    except Exception:
                        failed.append(filename)
            if failed:
                if len(failed) == 1:
                    flash("Failed to unsign build %s" % failed[0], "error")
                else:
                    flash(
                        "Failed to unsign %d builds: %s"
                        % (len(failed), ", ".join(failed)),
                        "error",
                    )
            if not_signed:
                if len(not_signed) == 1:
                    flash("Build %s not signed" % not_signed[0], "info")
                else:
                    flash(
                        "%d builds not signed: %s"
                        % (len(not_signed), ", ".join(not_signed)),
                        "info",
                    )
            if success:
                if len(success) == 1:
                    flash("Build %s successfully unsigned" % success[0])
                else:
                    flash(
                        "Successfully unsigned %d builds: %s"
                        % (len(success), ", ".join(success))
                    )
        except Exception as e:  # pragma: no cover
            flash("Failed to unsign builds. %s" % str(e), "error")

    def is_action_allowed(self, name):
        if name == "sign" and not self.can_sign:
            return False
        if name == "unsign" and not self.can_unsign:
            return False

        return super(BuildView, self).is_action_allowed(name)


class IndexView(AdminIndexView):
    @expose("/")
    def index(self):
        if not current_user.is_authenticated:
            return redirect(url_for("security.login"))
        if not any(map(current_user.has_role, ("developer", "package_admin", "admin"))):
            abort(403)
        return super(IndexView, self).index()
