# -*- coding: utf-8 -*-
import logging
import secrets

import requests
from flask import (
    Blueprint,
    abort,
    current_app,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_security import RegisterFormV2, current_user, login_required
from flask_security.forms import ChangePasswordForm
from flask_wtf import FlaskForm
from wtforms import HiddenField, StringField, SubmitField, ValidationError
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
from ..net import get_client_ip

frontend = Blueprint("frontend", __name__)

logger = logging.getLogger(__name__)


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
    """WTForms validator: reject usernames that are already taken.

    Records the existing user on ``form.existing_username_user`` so that
    :py:data:`SECURITY_RETURN_GENERIC_RESPONSES` can squash the error and avoid
    leaking which usernames are registered.
    """
    form.existing_username_user = user_datastore.find_user(username=field.data)
    if form.existing_username_user is not None:
        raise ValidationError("Username already taken")


def _honeypot_must_be_empty(form, field):
    """WTForms validator: reject submissions that filled the hidden honeypot.

    The field is hidden from human visitors via CSS, so any content means an
    automated bot auto-filled every text input.
    """
    if field.data:
        logger.warning(
            "Registration honeypot triggered (client IP %s, username %r, email %r)",
            get_client_ip(),
            form.username.data,
            form.email.data,
        )
        raise ValidationError("Please leave this field empty")


TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def _verify_turnstile_token(token, remote_ip):
    """Verify a Turnstile token with Cloudflare. Returns True on success.

    When TURNSTILE_HOSTNAME is configured, the hostname Cloudflare reports
    the challenge was solved on must also match (defense against tokens
    minted for a different site).
    """
    secret = current_app.config.get("TURNSTILE_SECRET_KEY")
    if not secret:
        logger.error("TURNSTILE_SECRET_KEY is not configured; rejecting registration")
        return False
    try:
        response = requests.post(
            TURNSTILE_VERIFY_URL,
            data={"secret": secret, "response": token, "remoteip": remote_ip},
            timeout=10,
        )
        result = response.json()
        if not result.get("success", False):
            return False
        expected_hostname = current_app.config.get("TURNSTILE_HOSTNAME")
        if expected_hostname and result.get("hostname") != expected_hostname:
            logger.warning(
                "Turnstile hostname mismatch: expected %r, got %r",
                expected_hostname,
                result.get("hostname"),
            )
            return False
        return True
    except Exception:
        logger.exception("Turnstile verification request failed")
        return False


def _turnstile_must_verify(form, field):
    """WTForms validator: verify the Cloudflare Turnstile challenge token.

    The widget posts its token as ``cf-turnstile-response``. Skipped when
    TESTING (same pattern flask-security itself uses). Fail-closed: a missing
    token, missing secret, provider error, or explicit failure all reject the
    registration — no user is created and no email is sent.
    """
    if current_app.config.get("TESTING"):
        return
    token = request.form.get("cf-turnstile-response")
    if not token or not _verify_turnstile_token(token, get_client_ip()):
        raise ValidationError("Bot verification failed. Please try again.")


class SpkrepoRegisterForm(RegisterFormV2):
    """Flask-Security registration form extended with a required, unique
    username field, a CSS-hidden honeypot, and Cloudflare Turnstile
    verification to reject scripted bots."""

    username = StringField(
        "Username", [InputRequired(), Length(min=4), unique_user_username]
    )
    website = StringField(
        "Website",
        [_honeypot_must_be_empty],
        render_kw={
            "tabindex": "-1",
            "autocomplete": "off",
            "aria-hidden": "true",
        },
    )
    # NOTE: the field name must NOT be "turnstile" — browsers expose every
    # id as a window global, so <input id="turnstile"> shadows window.turnstile
    # and the Cloudflare library refuses to initialize ("already loaded"),
    # silently killing the widget. Carries Turnstile failures so the error
    # renders via form_errors; the widget posts its token as
    # cf-turnstile-response (see validator).
    turnstile_check = HiddenField("Turnstile", [_turnstile_must_verify])
