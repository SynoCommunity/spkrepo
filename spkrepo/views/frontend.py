# -*- coding: utf-8 -*-
import secrets

from flask import Blueprint, abort, redirect, render_template, url_for
from flask_security import RegisterFormV2, current_user, login_required
from flask_security.forms import ChangePasswordForm
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, ValidationError
from wtforms.validators import InputRequired, Length

from ..ext import cache, db
from ..models import (
    Build,
    BuildDescription,
    DisplayName,
    Package,
    Version,
    user_datastore,
)

frontend = Blueprint("frontend", __name__)


@frontend.route("/")
def index():
    """Render the site's home page."""
    return render_template("frontend/index.html")


class GenerateApiKeyForm(FlaskForm):
    """Form for generating an API key."""

    api_key = StringField("API Key")
    submit = SubmitField("Generate API Key")


def _generate_api_key():
    """Generate a random 64-character hex API key."""
    return secrets.token_hex(32)


@frontend.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """Render the current user's profile page.

    Developers additionally see an API key generation form; submitting
    it regenerates their API key.
    """
    if not current_user.has_role("developer"):
        return render_template(
            "frontend/profile.html",
            change_password_form=ChangePasswordForm(),
        )
    form = GenerateApiKeyForm()
    if form.validate_on_submit():
        current_user.api_key = _generate_api_key()
        db.session.commit()
        return redirect(url_for("frontend.profile"), code=303)
    form.api_key.data = current_user.api_key
    return render_template(
        "frontend/profile.html",
        change_password_form=ChangePasswordForm(),
        generate_api_key_form=form,
    )


@frontend.route("/packages")
def packages():
    """Render the package list page, showing each package's latest
    version. Results are cached for 5 minutes under "packages_versions".
    """
    versions = cache.get("packages_versions")
    if versions is None:
        latest_version = (
            db.select(
                Version.package_id, db.func.max(Version.version).label("latest_version")
            )
            .join(Build)
            .group_by(Version.package_id)
            .subquery()
        )
        versions = (
            db.session.execute(
                db.select(Version)
                .join(Version.package)
                .options(
                    # Version.icons/displaynames/builds are one-to-many
                    # collections; selectinload avoids the Cartesian-product
                    # row multiplication joinedload would cause here.
                    db.joinedload(Version.package).joinedload(Package.download_counts),
                    db.joinedload(Version.package).undefer(Package.has_active_builds),
                    db.selectinload(Version.icons),
                    db.selectinload(Version.displaynames).joinedload(
                        DisplayName.language
                    ),
                    db.selectinload(Version.builds)
                    .selectinload(Build.descriptions)
                    .joinedload(BuildDescription.language),
                )
                .join(
                    latest_version,
                    db.and_(
                        Version.package_id == latest_version.c.package_id,
                        Version.version == latest_version.c.latest_version,
                    ),
                )
                .order_by(Package.name)
            )
            .unique()
            .scalars()
            .all()
        )
        cache.set("packages_versions", versions, timeout=300)
    return render_template("frontend/packages.html", versions=versions)


@frontend.route("/package/<name>")
def package(name):
    """Render a single package's detail page, showing its full version
    history. Returns 404 if the package doesn't exist or has no versions.
    """
    pkg = (
        db.session.execute(
            db.select(Package)
            .filter_by(name=name)
            .options(
                # Same Cartesian-product concern as /packages — selectinload
                # for one-to-many collections instead of stacking joinedloads.
                db.joinedload(Package.download_counts),
                db.selectinload(Package.versions).selectinload(Version.icons),
                db.selectinload(Package.versions).selectinload(Version.displaynames),
                db.selectinload(Package.versions)
                .selectinload(Version.builds)
                .selectinload(Build.descriptions),
            )
        )
        .unique()
        .scalars()
        .first()
    )
    if pkg is None or not pkg.versions:
        abort(404)
    return render_template("frontend/package.html", package=pkg)


def unique_user_username(form, field):
    """WTForms validator: reject usernames that are already taken."""
    if user_datastore.find_user(username=field.data) is not None:
        raise ValidationError("Username already taken")


class SpkrepoRegisterForm(RegisterFormV2):
    """Flask-Security registration form extended with a required, unique
    username field."""

    username = StringField(
        "Username", [InputRequired(), Length(min=4), unique_user_username]
    )
