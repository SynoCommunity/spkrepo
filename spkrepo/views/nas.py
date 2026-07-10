# -*- coding: utf-8 -*-
import gnupg
from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    json,
    redirect,
    request,
    send_from_directory,
    url_for,
)
from sqlalchemy.orm import aliased

from ..ext import cache, db
from ..models import (
    Architecture,
    Build,
    BuildDescription,
    DisplayName,
    Firmware,
    Language,
    Package,
    PackageDownloadCounts,
    Version,
)

nas = Blueprint("nas", __name__)


@cache.memoize(timeout=600)
def is_valid_arch(arch):
    """Return True if arch is a known Architecture code."""
    return Architecture.find(arch) is not None


@cache.memoize(timeout=600)
def is_valid_language(language):
    """Return True if language is a known Language code."""
    return Language.find(language) is not None


@cache.memoize(timeout=600)
def get_catalog(arch, build, major, language, beta):
    """Build the package catalog for one (arch, build, major, language,
    beta) combination.

    Returns a list of package dicts for DSM < 5.1, or a dict with
    "packages" (and "keyrings" for DSM 6 only) otherwise. Memoized for
    10 minutes; clear_catalog_cache() invalidates all entries when build
    or version data changes.
    """
    # Raise work_mem for this transaction only to avoid the catalog sort
    # spilling to disk (observed: 6.9 MB spill with default work_mem).
    if db.engine.dialect.name == "postgresql":
        db.session.execute(db.text("SET LOCAL work_mem = '16MB'"))

    firmware_min_alias = aliased(Firmware)
    firmware_max_alias = aliased(Firmware)

    # Step 1: Get the latest version for each package
    latest_version = db.select(
        Version.package_id, db.func.max(Version.version).label("latest_version")
    ).select_from(Version)

    if not beta:
        latest_version = latest_version.filter(
            db.or_(Version.report_url.is_(None), Version.report_url == "")
        )

    latest_version = (
        latest_version.join(Build)
        .filter(Build.active)
        .join(Build.architectures)
        .filter(db.or_(Architecture.code == arch, Architecture.code == "noarch"))
        .join(firmware_min_alias, Build.firmware_min)
        .outerjoin(firmware_max_alias, Build.firmware_max)
        .filter(firmware_min_alias.build <= build)
        .filter(
            db.or_(Build.firmware_max_id.is_(None), firmware_max_alias.build >= build)
        )
        .filter(
            db.or_(
                firmware_min_alias.version.startswith(f"{major}."),
                db.and_(
                    Architecture.code == "noarch",
                    major < 6,
                    firmware_min_alias.version.startswith("3."),
                ),
            )
        )
        .group_by(Version.package_id)
        .subquery()
    )

    # Step 2: Get the latest firmware for each version
    latest_firmware = (
        db.select(
            Version.package_id,
            latest_version.c.latest_version,
            db.func.max(firmware_min_alias.build).label("latest_firmware"),
        )
        .select_from(Version)
        .join(Build)
        .filter(Build.active)
        .join(Build.architectures)
        .filter(db.or_(Architecture.code == arch, Architecture.code == "noarch"))
        .join(firmware_min_alias, Build.firmware_min)
        .outerjoin(firmware_max_alias, Build.firmware_max)
        .filter(firmware_min_alias.build <= build)
        .filter(
            db.or_(Build.firmware_max_id.is_(None), firmware_max_alias.build >= build)
        )
        .join(
            latest_version,
            db.and_(
                Version.package_id == latest_version.c.package_id,
                Version.version == latest_version.c.latest_version,
            ),
        )
        .group_by(Version.package_id, latest_version.c.latest_version)
        .subquery()
    )

    # Step 3: Get the latest builds for versions.
    # Download counts are no longer undeferred here — they are fetched in
    # bulk from the package_download_counts materialized view below, which
    # replaces the correlated per-row subqueries that were firing ~7000
    # times per catalog request.
    firmware_min_for_build = aliased(Firmware)
    latest_build = (
        db.session.execute(
            db.select(Build)
            .options(
                # Build.architectures/version/firmware_min/firmware_max are
                # lazy=False (models.py), so joined by default. Collections
                # below use selectinload, not joinedload, to avoid Cartesian-
                # product row multiplication when eager-loading several at once.
                db.selectinload(Build.architectures),
                db.joinedload(Build.firmware_min),
                db.joinedload(Build.firmware_max),
                db.joinedload(Build.version).joinedload(Version.package),
                db.joinedload(Build.version).selectinload(Version.icons),
                db.joinedload(Build.version)
                .selectinload(Version.displaynames)
                .joinedload(DisplayName.language),
                db.selectinload(Build.descriptions).joinedload(
                    BuildDescription.language
                ),
                db.joinedload(Build.version, Version.package).selectinload(
                    Package.screenshots
                ),
                db.joinedload(Build.buildmanifest),
            )
            .join(Build.architectures)
            .filter(db.or_(Architecture.code == arch, Architecture.code == "noarch"))
            .join(firmware_min_for_build, Build.firmware_min)
            .join(Version)
            .join(
                latest_firmware,
                db.and_(
                    Version.package_id == latest_firmware.c.package_id,
                    Version.version == latest_firmware.c.latest_version,
                    firmware_min_for_build.build == latest_firmware.c.latest_firmware,
                ),
            )
        )
        # unique() is required (and good practice generally) whenever a
        # query's joins could yield more than one row per Build — here,
        # joining the many-to-many Build.architectures for filtering can
        # do that — so entities are de-duplicated by identity before
        # converting to a plain list.
        .unique()
        .scalars()
        .all()
    )

    # Step 4: Bulk fetch download counts from the materialized view in one
    # query rather than firing a correlated subquery per package per row.
    package_ids = [b.version.package_id for b in latest_build]
    counts_by_package = {
        row.package_id: row
        for row in db.session.execute(
            db.select(PackageDownloadCounts).filter(
                PackageDownloadCounts.package_id.in_(package_ids)
            )
        ).scalars()
    }

    # Step 5: Construct response with "packages"
    packages = [
        build_package_entry(b, language, arch, build, counts_by_package)
        for b in latest_build
    ]

    # DSM 5.1+
    if build >= 5004:
        result = {"packages": packages}
        # DSM 6 only
        if build < 40000:
            keyrings = []
            if current_app.config["GNUPG_PATH"] is not None:  # pragma: no cover
                gpg = gnupg.GPG(gnupghome=current_app.config["GNUPG_PATH"])
                keyrings.append(
                    gpg.export_keys(current_app.config["GNUPG_FINGERPRINT"]).strip()
                )
            result["keyrings"] = keyrings
    else:
        result = packages

    return result


def _set_if_truthy(entry, key, value):
    """Set entry[key] = value only if value is truthy."""
    if value:
        entry[key] = value


def build_package_entry(b, language, arch, build, counts_by_package):
    """Build one package's catalog dict entry from a Build, in the shape
    expected by DSM/SRM package_update clients."""
    counts = counts_by_package.get(b.version.package_id)
    entry = {
        "package": b.version.package.name,
        "version": b.version.version_string,
        "dname": b.version.displaynames.get(
            language, b.version.displaynames["enu"]
        ).displayname,
        "desc": b.descriptions.get(language, b.descriptions["enu"]).description,
        "link": url_for(
            ".data",
            path=b.path,
            arch=arch,
            build=build,
            _external=True,
        ),
        "thumbnail": [
            url_for(".data", path=icon.path, _external=True)
            for icon in b.version.icons.values()
        ],
        "qinst": b.version.license is None and b.version.install_wizard is False,
        "qupgrade": b.version.license is None and b.version.upgrade_wizard is False,
        "qstart": (
            b.version.license is None
            and b.version.install_wizard is False
            and b.version.startable is not False
        ),
        "deppkgs": b.buildmanifest.dependencies if b.buildmanifest else None,
        "conflictpkgs": b.buildmanifest.conflicts if b.buildmanifest else None,
        "download_count": counts.download_count if counts else 0,
        "recent_download_count": counts.recent_download_count if counts else 0,
        "snapshot": (
            [
                url_for(".data", path=screenshot.path, _external=True)
                for screenshot in b.version.package.screenshots
            ]
            if b.version.package.screenshots
            else []
        ),
    }

    if b.version.report_url:
        entry["report_url"] = b.version.report_url
        entry["beta"] = True

    _set_if_truthy(entry, "changelog", b.changelog)
    _set_if_truthy(entry, "distributor", b.version.distributor)
    _set_if_truthy(entry, "distributor_url", b.version.distributor_url)
    _set_if_truthy(entry, "maintainer", b.version.maintainer)
    _set_if_truthy(entry, "maintainer_url", b.version.maintainer_url)
    _set_if_truthy(entry, "md5", b.md5)
    _set_if_truthy(entry, "size", b.size)

    _retina_icon = b.version.icons.get("256")
    if _retina_icon:
        _retina_url = url_for(".data", path=_retina_icon.path, _external=True)
        entry["thumbnail_retina"] = [_retina_url, _retina_url]

    if b.version.startable is not None:
        entry["startable"] = "yes" if b.version.startable else "no"

    return entry


def clear_catalog_cache():
    """Invalidate all memoized NAS catalog cache entries.

    Called by admin actions and background tasks whenever build metadata
    or activation state changes, so Synology devices see fresh data
    without waiting for the memoize timeout to expire.
    """
    cache.delete_memoized(get_catalog)


@nas.route("/", methods=["POST", "GET"])
def catalog():
    """Return the package catalog for a DSM/SRM device.

    This is the endpoint DSM/SRM devices poll to discover packages
    available for their architecture, firmware, and language. The
    response shape depends on the ``build`` firmware number: builds
    below ``5004`` get a bare list, builds from ``5004`` up to (but not
    including) ``40000`` (DSM 6) additionally get a ``keyrings`` entry,
    and DSM 7+ builds (``40000`` and above) get ``packages`` only.

    :query build: the device's firmware build number (required)
    :query arch: the device's CPU architecture code, as reported by
        DSM/SRM (required)
    :query language: the device's language code, e.g. ``enu`` (required)
    :query major: the DSM/SRM major version; inferred from ``build``
        against known firmware if omitted
    :query package_update_channel: set to ``beta`` to include beta
        packages (DSM < 7 only; ignored otherwise)

    **Example response** (DSM 7+):

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Content-Type: application/json

        {
            "packages": [
                {
                    "package": "git",
                    "version": "2.1.2-4",
                    "dname": "Git",
                    "desc": "Distributed version control system.",
                    "link": "https://example.com/nas/git/4/git.v4.f64570%5Bx86_64%5D.spk?arch=x86_64&build=64570",
                    "thumbnail": ["https://example.com/nas/git/4/icon_72.png"],
                    "qinst": true,
                    "qupgrade": true,
                    "qstart": false,
                    "download_count": 1024,
                    "recent_download_count": 87
                }
            ]
        }

    :statuscode 200: catalog returned
    :statuscode 400: a required parameter is missing and the client did
        not request an HTML response (browsers are redirected instead)
    :statuscode 422: ``language``, ``arch``, or ``build`` is invalid
    """
    if (
        "build" not in request.values
        or "arch" not in request.values
        or "language" not in request.values
    ):
        if request.accept_mimetypes.accept_html:
            return redirect(url_for("frontend.packages"))
        abort(400)

    language = request.values["language"]
    if not is_valid_language(language):
        abort(422)
    arch = Architecture.from_syno.get(request.values["arch"], request.values["arch"])
    if not is_valid_arch(arch):
        abort(422)
    try:
        build = int(request.values["build"])
    except ValueError:
        abort(422)

    # DSM 7.0+ does not support beta packages
    if build < 40000:
        beta = request.values.get("package_update_channel") == "beta"
    else:
        beta = False

    if "major" in request.values:
        try:
            major = int(request.values["major"])
        except ValueError:
            abort(422)
    else:
        closest_firmware = (
            db.session.execute(
                db.select(Firmware)
                .filter(Firmware.build <= build, Firmware.type == "dsm")
                .order_by(Firmware.build.desc())
            )
            .scalars()
            .first()
        )
        if not closest_firmware or not closest_firmware.version:
            abort(422)
        major = int(closest_firmware.version.split(".")[0])

    result = get_catalog(arch, build, major, language, beta)
    return Response(json.dumps(result), mimetype="application/json")


@nas.route("/<path:path>")
def data(path):
    """Serve a file (SPK, icon, or screenshot) from local storage.

    :param path: relative file path under DATA_PATH, as returned by the
        catalog's ``link``/``thumbnail``/``snapshot`` URLs
    :statuscode 200: file returned
    :statuscode 404: no file exists at the given path
    """
    return send_from_directory(current_app.config["DATA_PATH"], path)
