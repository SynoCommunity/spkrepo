# -*- coding: utf-8 -*-
import hashlib
import os

from flask import Blueprint, abort, redirect, render_template, url_for
from flask_security import ConfirmRegisterForm, current_user, login_required
from flask_security.forms import ChangePasswordForm
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, ValidationError
from wtforms.validators import InputRequired, Length

from ..ext import db
from ..models import Build, Description, DisplayName, Package, Version, user_datastore

frontend = Blueprint("frontend", __name__)


@frontend.route("/")
def index():
    return render_template("frontend/index.html")


class GenerateApiKeyForm(FlaskForm):
    """Form for generating an API key"""

    api_key = StringField("API Key")
    submit = SubmitField("Generate API Key")

    def validate(self):
        if not super(GenerateApiKeyForm, self).validate():  # pragma: no cover
            return False

        if not current_user.has_role("developer"):
            return False

        return True


def generate_api_key():
    """
    Generate a random API key based on `os.urandom`

    :return: the generated API key
    :rtype: str
    """
    return hashlib.sha256(os.urandom(32)).hexdigest()


@frontend.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    form = GenerateApiKeyForm()
    if form.validate_on_submit():
        current_user.api_key = generate_api_key()
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
    latest_version = (
        db.session.query(
            Version.package_id, db.func.max(Version.version).label("latest_version")
        )
        .join(Build)
        .filter(Build.active)
        .group_by(Version.package_id)
        .subquery()
    )
    versions = (
        Version.query.join(Version.package)
        .options(
            db.joinedload(Version.package),
            db.joinedload(Version.icons),
            db.joinedload(Version.displaynames).joinedload(DisplayName.language),
            db.joinedload(Version.descriptions).joinedload(Description.language),
        )
        .join(
            latest_version,
            db.and_(
                Version.package_id == latest_version.c.package_id,
                Version.version == latest_version.c.latest_version,
            ),
        )
        .order_by(Package.name)
        .all()
    )
    return render_template("frontend/packages.html", versions=versions)


@frontend.route("/package/<name>")
def package(name):
    # TODO: show only packages with at least a version and an active build
    package = Package.query.filter_by(name=name).first()
    if package is None:
        abort(404)
    return render_template("frontend/package.html", package=package)


def unique_user_username(form, field):
    if user_datastore.find_user(username=field.data) is not None:
        raise ValidationError("Username already taken")


class SpkrepoConfirmRegisterForm(ConfirmRegisterForm):
    username = StringField(
        "Username", [InputRequired(), Length(min=4), unique_user_username]
    )
