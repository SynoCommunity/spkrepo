# -*- coding: utf-8 -*-
import gnupg
from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    json,
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
    return Architecture.find(arch) is not None


@cache.memoize(timeout=600)
def is_valid_language(language):
    return Language.find(language) is not None


@cache.memoize(timeout=600)
def get_catalog(arch, build, major, language, beta):
    # Raise work_mem for this transaction only to avoid the catalog sort
    # spilling to disk (observed: 6.9 MB spill with default work_mem).
    if db.engine.dialect.name == "postgresql":
        db.session.execute(db.text("SET LOCAL work_mem = '16MB'"))

    firmware_min_alias = aliased(Firmware)
    firmware_max_alias = aliased(Firmware)

    # Step 1: Get the latest version for each package
    latest_version = db.session.query(
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
        db.session.query(
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
        Build.query.options(
            db.joinedload(Build.architectures),
            db.joinedload(Build.firmware_min),
            db.joinedload(Build.firmware_max),
            db.joinedload(Build.version).joinedload(Version.package),
            db.joinedload(Build.version).joinedload(Version.icons),
            db.joinedload(Build.version)
            .joinedload(Version.displaynames)
            .joinedload(DisplayName.language),
            db.joinedload(Build.descriptions).joinedload(BuildDescription.language),
            db.joinedload(Build.version, Version.package, Package.screenshots),
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
        .all()
    )

    # Step 4: Bulk fetch download counts from the materialized view in one
    # query rather than firing a correlated subquery per package per row.
    package_ids = [b.version.package_id for b in latest_build]
    counts_by_package = {
        row.package_id: row
        for row in PackageDownloadCounts.query.filter(
            PackageDownloadCounts.package_id.in_(package_ids)
        )
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
    if (
        "build" not in request.values
        or "arch" not in request.values
        or "language" not in request.values
    ):
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
            Firmware.query.filter(Firmware.build <= build, Firmware.type == "dsm")
            .order_by(Firmware.build.desc())
            .first()
        )
        if not closest_firmware or not closest_firmware.version:
            abort(422)
        major = int(closest_firmware.version.split(".")[0])

    result = get_catalog(arch, build, major, language, beta)
    return Response(json.dumps(result), mimetype="application/json")


@nas.route("/<path:path>")
def data(path):
    return send_from_directory(current_app.config["DATA_PATH"], path)
