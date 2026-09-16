# -*- coding: utf-8 -*-
"""Web frontend views: package browsing, auth pages, user profile."""

import logging
import secrets

import requests
from flask import (
    Blueprint,
    abort,
    current_app,
    g,
    make_response,
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
    Architecture,
    Build,
    BuildDescription,
    DisplayName,
    Language,
    Package,
    Version,
    group_builds_per_dsm,
    user_datastore,
)
from ..net import get_client_ip

frontend = Blueprint("frontend", __name__)

logger = logging.getLogger(__name__)

#: Cookie persisting the selected frontend architecture filter.
ARCH_COOKIE = "spk_arch"
#: How long the architecture list is cached (nas catalog uses 600s too).
ARCH_LIST_TIMEOUT = 600


@cache.memoize(timeout=ARCH_LIST_TIMEOUT)
def get_architectures():
    """Sorted list of selectable architecture codes, excluding noarch.

    noarch builds are universal so they are always included in filtered
    results, but noarch itself is not a device architecture to select.
    """
    return (
        db.session.execute(
            db.select(Architecture.code)
            .where(Architecture.code != "noarch")
            .order_by(Architecture.code)
        )
        .scalars()
        .all()
    )


def _resolve_arch_filter():
    """Resolve the requested architecture filter.

    Returns (arch_code or None, clear_cookie bool). An explicit ?arch=
    query param wins over the cookie; unknown codes abort with 404.
    """
    from ..domain.shared_kernel import translate_arch_from_syno as _from_syno

    param = request.args.get("arch")
    if param is not None:
        if param in ("", "all"):
            return None, True
        # Accept Synology DSM/SRM spellings (e.g. 88f6281); canonical map is
        # owned by spkrepo.domain.shared_kernel.
        param = _from_syno(param)
        if Architecture.find(param) is None:
            abort(404)
        return param, False
    cookie = request.cookies.get(ARCH_COOKIE)
    if cookie and cookie not in ("", "all"):
        cookie = _from_syno(cookie)
        if Architecture.find(cookie) is not None:
            return cookie, False
    return None, False


def _arch_response(template, param_present, clear_cookie, selected_arch, **context):
    """Render a template, persisting the arch selection in a cookie."""
    response = make_response(render_template(template, **context))
    if param_present:
        if clear_cookie or not selected_arch:
            response.delete_cookie(ARCH_COOKIE, path="/")
        else:
            response.set_cookie(
                ARCH_COOKIE, selected_arch, max_age=31536000, path="/", samesite="Lax"
            )
    return response


@frontend.context_processor
def inject_arch_selector():
    """Expose the architecture list + current selection to frontend
    templates (packages.html renders the selector; other pages ignore
    the extra variables)."""
    try:
        architectures = get_architectures()
    except Exception:
        architectures = []
    return {
        "architectures": architectures,
        "selected_arch": getattr(g, "selected_arch", None),
    }


def _arch_request_context():
    """Resolve the arch filter for this request and stash it on g for
    the context processor. Returns (selected_arch, clear_cookie,
    param_present)."""
    selected_arch, clear_cookie = _resolve_arch_filter()
    g.selected_arch = selected_arch
    return selected_arch, clear_cookie, "arch" in request.args


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

    With ?arch=<code> (or the spk_arch cookie), only packages with a
    build for that architecture — or a universal noarch build — are
    shown, and "latest" means latest version carrying such a build.
    Filtered views bypass the cache; the unfiltered list stays cached
    so existing invalidation logic is untouched.
    """
    selected_arch, clear_cookie, param_present = _arch_request_context()

    if selected_arch is None:
        versions = cache.get("packages_versions")
        if versions is None:
            versions = _latest_versions_query(None)
            cache.set("packages_versions", versions, timeout=300)
    else:
        versions = _latest_versions_query(selected_arch)
    active_versions = [v for v in versions if not v["archived"]]
    archived_versions = [v for v in versions if v["archived"]]
    return _arch_response(
        "frontend/packages.html",
        param_present,
        clear_cookie,
        selected_arch,
        active_versions=active_versions,
        archived_versions=archived_versions,
    )


def _default_descriptions(version_ids):
    """Map version id -> the enu description of its first build.

    One small query instead of eager-loading every build and every
    description for the whole page (which dominated the packages list).
    """
    if not version_ids:
        return {}
    first_build = (
        db.select(
            Build.version_id,
            db.func.min(Build.id).label("build_id"),
        )
        .where(Build.version_id.in_(version_ids))
        .group_by(Build.version_id)
        .subquery()
    )
    rows = db.session.execute(
        db.select(first_build.c.version_id, BuildDescription.description)
        .join(Build, Build.id == first_build.c.build_id)
        .join(BuildDescription, BuildDescription.build_id == Build.id)
        .join(Language, Language.id == BuildDescription.language_id)
        .where(Language.code == "enu")
    ).all()
    return dict(rows)


def _latest_versions_query(arch_code):
    """Latest Version per package, optionally restricted to builds for
    arch_code (universal noarch builds always count).

    Returns plain dicts of just the fields the template renders, so the
    result is cheap to cache (no ORM object graph to pickle) and avoids
    loading the full build/description collections.
    """
    latest_version = db.select(
        Version.package_id, db.func.max(Version.version).label("latest_version")
    ).join(Build)
    if arch_code is not None:
        latest_version = latest_version.join(Build.architectures).filter(
            db.or_(
                Architecture.code == arch_code,
                Architecture.code == "noarch",
            )
        )
    latest_version = latest_version.group_by(Version.package_id).subquery()
    versions = (
        db.session.execute(
            db.select(Version)
            .join(Version.package)
            .options(
                db.contains_eager(Version.package).joinedload(Package.download_counts),
                db.contains_eager(Version.package).undefer(Package.has_active_builds),
                db.selectinload(Version.icons),
                db.selectinload(Version.displaynames).joinedload(DisplayName.language),
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

    descriptions = _default_descriptions([v.id for v in versions])
    rows = []
    for version in versions:
        counts = version.package.download_counts
        rows.append(
            {
                "name": version.package.name,
                "displayname": version.displaynames["enu"].displayname,
                "version_string": version.version_string,
                "icon_path": version.icons["72"].path,
                "description": descriptions.get(version.id, ""),
                "recent_download_count": (
                    counts.recent_download_count if counts else 0
                ),
                "archived": not version.package.has_active_builds,
            }
        )
    return rows


@frontend.route("/package/<name>")
def package(name):
    """Render a single package's detail page, showing its full version
    history. Returns 404 if the package doesn't exist or has no versions.

    When an architecture filter is active, only versions with a build
    for that architecture (or a universal noarch build) are shown, and
    only the matching builds within them. Returns 404 when nothing
    targets the selected arch.
    """
    selected_arch, clear_cookie, param_present = _arch_request_context()
    pkg = (
        db.session.execute(
            db.select(Package)
            .filter_by(name=name)
            .options(
                # Same selectinload rule as above.
                db.joinedload(Package.download_counts),
                db.selectinload(Package.versions).selectinload(Version.icons),
                db.selectinload(Package.versions).selectinload(Version.displaynames),
                db.selectinload(Package.versions)
                .selectinload(Version.builds)
                .selectinload(Build.descriptions),
                db.selectinload(Package.versions)
                .selectinload(Version.builds)
                .selectinload(Build.architectures),
            )
        )
        .unique()
        .scalars()
        .first()
    )
    if pkg is None or not pkg.versions:
        abort(404)
    display_versions = None
    version_build_groups = None
    header_version = pkg.versions[-1]
    if selected_arch is not None:
        wanted = {selected_arch, "noarch"}
        display_versions = [
            version
            for version in pkg.versions
            if any(
                {a.code for a in build.architectures} & wanted
                for build in version.builds
            )
        ]
        if not display_versions:
            abort(404)
        version_build_groups = {
            version.id: group_builds_per_dsm(
                [
                    build
                    for build in version.builds
                    if {a.code for a in build.architectures} & wanted
                ]
            )
            for version in display_versions
        }
        header_version = display_versions[-1]
    return _arch_response(
        "frontend/package.html",
        param_present,
        clear_cookie,
        selected_arch,
        package=pkg,
        display_versions=display_versions,
        version_build_groups=version_build_groups,
        header_version=header_version,
    )


def unique_user_username(form, field):
    """WTForms validator: reject usernames that are already taken.

    Records the existing user on ``form.existing_username_user`` so that the
    Flask-Security ``SECURITY_RETURN_GENERIC_RESPONSES`` setting can squash
    the error and avoid leaking which usernames are registered.
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
