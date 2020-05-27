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

from ..ext import cache, db
from ..models import (
    Architecture,
    Build,
    Description,
    DisplayName,
    Download,
    Firmware,
    Language,
    Package,
    Version,
)

nas = Blueprint("nas", __name__)


@cache.memoize(timeout=600)
def is_valid_arch(arch):
    if Architecture.find(arch):
        return True
    return False


@cache.memoize(timeout=600)
def is_valid_language(language):
    if Language.find(language):
        return True
    return False


@cache.memoize(timeout=600)
def get_catalog(arch, build, language, beta):
    # latest version per package
    latest_version = db.session.query(
        Version.package_id, db.func.max(Version.version).label("latest_version")
    ).select_from(Version)
    if not beta:
        latest_version = latest_version.filter(Version.report_url.is_(None))
    latest_version = (
        latest_version.join(Build)
        .filter(Build.active)
        .join(Build.architectures)
        .filter(Architecture.code.in_(["noarch", arch]))
        .join(Build.firmware)
        .filter(Firmware.build <= build)
        .group_by(Version.package_id)
    ).subquery()

    # latest firmware on given version
    latest_firmware = (
        db.session.query(
            Version.package_id,
            latest_version.c.latest_version,
            db.func.max(Firmware.build).label("latest_firmware"),
        )
        .select_from(Version)
        .join(Build)
        .filter(Build.active)
        .join(Build.architectures)
        .filter(Architecture.code.in_(["noarch", arch]))
        .join(Build.firmware)
        .filter(Firmware.build <= build)
        .join(
            latest_version,
            db.and_(
                Version.package_id == latest_version.c.package_id,
                Version.version == latest_version.c.latest_version,
            ),
        )
        .group_by(Version.package_id, latest_version.c.latest_version)
    ).subquery()

    # build on given version and firmware
    latest_build = (
        Build.query.options(
            db.joinedload(Build.architectures),
            db.joinedload(Build.firmware),
            db.joinedload(Build.version).joinedload(Version.package),
            db.joinedload(Build.version).joinedload(Version.service_dependencies),
            db.joinedload(Build.version).joinedload(Version.icons),
            db.joinedload(Build.version)
            .joinedload(Version.displaynames)
            .joinedload(DisplayName.language),
            db.joinedload(Build.version, Version.descriptions, Description.language),
            db.joinedload(Build.version, Version.package, Package.screenshots),
        )
        .join(Build.architectures)
        .filter(Architecture.code.in_(["noarch", arch]))
        .join(Firmware)
        .join(Version)
        .join(
            latest_firmware,
            db.and_(
                Version.package_id == latest_firmware.c.package_id,
                Version.version == latest_firmware.c.latest_version,
                Firmware.build == latest_firmware.c.latest_firmware,
            ),
        )
    )

    # fill the catalog
    entries = []
    for b in latest_build.all():
        entry = {
            "package": b.version.package.name,
            "version": b.version.version_string,
            "dname": b.version.displaynames.get(
                language, b.version.displaynames["enu"]
            ).displayname,
            "desc": b.version.descriptions.get(
                language, b.version.descriptions["enu"]
            ).description,
            "link": url_for(
                ".data", path=b.path, arch=arch, build=build, _external=True
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
            "deppkgs": b.version.dependencies,
            "conflictpkgs": b.version.conflicts,
            "download_count": b.version.package.download_count,
            "recent_download_count": b.version.package.recent_download_count,
        }

        if b.version.package.screenshots:
            entry["snapshot"] = [
                url_for(".data", path=screenshot.path, _external=True)
                for screenshot in b.version.package.screenshots
            ]
        if b.version.report_url:
            entry["report_url"] = b.version.report_url
            entry["beta"] = True
        if b.version.changelog:
            entry["changelog"] = b.version.changelog
        if b.version.distributor:
            entry["distributor"] = b.version.distributor
        if b.version.distributor_url:
            entry["distributor_url"] = b.version.distributor_url
        if b.version.maintainer:
            entry["maintainer"] = b.version.maintainer
        if b.version.maintainer_url:
            entry["maintainer_url"] = b.version.maintainer_url
        if b.version.service_dependencies:
            entry["depsers"] = " ".join(
                [service.code for service in b.version.service_dependencies]
            )
        if b.md5:
            entry["md5"] = b.md5
        if b.version.conf_dependencies:
            entry["conf_deppkgs"] = b.version.conf_dependencies
        if b.version.conf_conflicts:
            entry["conf_conxpkgs"] = b.version.conf_conflicts
        if b.version.conf_privilege:
            entry["conf_privilege"] = b.version.conf_privilege
        if b.version.conf_resource:
            entry["conf_resource"] = b.version.conf_resource
        entries.append(entry)

    # DSM 5.1
    if build >= 5004:
        if current_app.config["GNUPG_PATH"] is not None:  # pragma: no cover
            gpg = gnupg.GPG(gnupghome=current_app.config["GNUPG_PATH"])
            return {
                "packages": entries,
                "keyrings": [
                    gpg.export_keys(current_app.config["GNUPG_FINGERPRINT"]).strip()
                ],
            }
        return {"packages": entries, "keyrings": []}

    return entries


@nas.route("/", methods=["POST", "GET"])
def catalog():
    # check consistency
    if (
        "build" not in request.values
        or "arch" not in request.values
        or "language" not in request.values
    ):
        abort(400)

    # read parameters
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
    beta = request.values.get("package_update_channel") == "beta"

    # get the catalog
    catalog = get_catalog(arch, build, language, beta)

    return Response(json.dumps(catalog), mimetype="application/json")


@nas.route("/download/<int:architecture_id>/<int:firmware_build>/<int:build_id>")
def download(architecture_id, firmware_build, build_id):
    # check build
    build = Build.query.get_or_404(build_id)
    if not build.active:
        abort(403)

    # architecture
    architecture = Architecture.query.get_or_404(architecture_id)

    # check consistency
    if architecture not in build.architectures or firmware_build < build.firmware.build:
        abort(400)

    # insert in database
    download = Download(
        build=build,
        architecture=architecture,
        firmware_build=firmware_build,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string,
    )
    db.session.add(download)
    db.session.commit()

    # redirect
    return redirect(url_for(".data", path=build.path))


@nas.route("/<path:path>")
def data(path):
    return send_from_directory(current_app.config["DATA_PATH"], path)
