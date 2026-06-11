# -*- coding: utf-8 -*-
import io
import logging
import os
import shutil
from functools import wraps

from flask import Blueprint, current_app, request
from flask_login import login_user
from flask_principal import Identity, identity_changed
from flask_restful import Api, Resource, abort
from flask_security import current_user

from ..exceptions import SPKParseError, SPKSignError
from ..ext import db
from ..models import (
    Build,
    BuildDescription,
    BuildManifest,
    DisplayName,
    Icon,
    Language,
    Package,
    Version,
    user_datastore,
)
from ..utils import (
    SPK,
    assert_version_metadata_matches_db,
    resolve_architectures,
    resolve_firmware,
    resolve_services,
    version_re,
)

logger = logging.getLogger(__name__)

api = Blueprint("api", __name__)


def api_auth_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if request.authorization and request.authorization.type == "basic":
            user = user_datastore.find_user(api_key=request.authorization.username)
            if user and user.has_role("developer"):
                login_user(user)
                identity_changed.send(
                    current_app._get_current_object(),
                    identity=Identity(user.fs_uniquifier),
                )
                return f(*args, **kwargs)
        abort(401)

    return wrapper


def _cleanup_on_failure(
    data_path, package_name, version_number, build_path, create_package, create_version
):
    """Remove partially saved files after a failed SPK save."""
    if create_package:
        shutil.rmtree(os.path.join(data_path, package_name), ignore_errors=True)
    elif create_version:
        shutil.rmtree(
            os.path.join(data_path, package_name, str(version_number)),
            ignore_errors=True,
        )
    else:
        try:
            os.remove(os.path.join(data_path, build_path))
        except OSError:
            pass


class Packages(Resource):
    """Packages resource"""

    def post(self):
        """Post a :abbr:`SPK (Synology Package)` to the repository.

        First a :class:`~spkrepo.models.Package` is created if not existing already,
        based on the :attr:`~spkrepo.models.Package.name`. Only users with
        ``package_admin`` role can create new packages, other users must be defined
        as :attr:`~spkrepo.models.Package.maintainers` to be able to continue.

        Then a :class:`~spkrepo.models.Version` is created with its appropriate
        relationships if not existing already, based on the
        :attr:`~spkrepo.models.Version.package` and the
        :attr:`~spkrepo.models.Version.version`.

        Lastly, a :class:`~spkrepo.models.Build` is created with its appropriate
        relationships and files saved on the filesystem.

        .. note::

           The created :class:`~spkrepo.models.Build` is not
           :attr:`~spkrepo.models.Build.active` by default

        **Example response:**

        .. sourcecode:: http

            HTTP/1.1 201 CREATED
            Content-Length: 97

            {
                "architectures": ["88f628x"],
                "firmware": "3.1-1594",
                "package": "btsync",
                "version": "1.4.103-10"
            }

        :statuscode 201: SPK registered
        :statuscode 400: Request contained no body
        :statuscode 403: Insufficient permission
        :statuscode 409: A :class:`~spkrepo.models.Build` already exists
        :statuscode 422: Invalid or malformed SPK
        :statuscode 500: Signing or filesystem issue
        """
        if not request.data:
            abort(400, message="No data to process")

        # open the spk
        try:
            spk = SPK(io.BytesIO(request.data))
        except SPKParseError as e:
            abort(422, message=str(e))

        # reject signed packages
        if spk.signature is not None:
            abort(422, message="Package contains a signature")

        # Architectures
        try:
            architectures = resolve_architectures(db.session, spk.info.get("arch"))
        except ValueError as e:
            abort(422, message=str(e))

        # Firmware min
        input_firmware = spk.info.get("firmware") or spk.info.get("os_min_ver")
        try:
            firmware = resolve_firmware(db.session, input_firmware)
        except ValueError as e:
            abort(422, message=str(e))

        # Firmware max
        firmware_max = None
        input_firmware_max = spk.info.get("os_max_ver")
        if input_firmware_max:
            try:
                firmware_max = resolve_firmware(db.session, input_firmware_max)
            except ValueError as e:
                abort(422, message=str(e))
            if firmware_max.build < firmware.build:
                abort(
                    422,
                    message=(
                        "Maximum firmware must be greater than or equal to "
                        "minimum firmware"
                    ),
                )

        # Services — resolve once here; reused in version creation below
        try:
            services = resolve_services(spk.info.get("install_dep_services"))
        except ValueError as e:
            abort(422, message=str(e))

        # Package
        create_package = False
        package = Package.find(spk.info["package"])
        if package is None:
            if not current_user.has_role("package_admin"):
                abort(403, message="Insufficient permissions to create new packages")
            create_package = True
            package = Package(name=spk.info["package"], author=current_user)
        elif (
            not current_user.has_role("package_admin")
            and current_user not in package.maintainers
        ):
            abort(403, message="Insufficient permissions on this package")

        # Version
        create_version = False
        match = version_re.match(spk.info["version"])
        if not match:
            abort(422, message="Invalid version")

        version = {v.version: v for v in package.versions}.get(
            int(match.group("version"))
        )

        if version is not None:
            # Existing version — enforce full metadata consistency before proceeding.
            # This catches cases where a build pipeline bug produces SPKs with
            # differing version-level metadata (e.g. different SPK_VER) for builds
            # that are part of the same logical release.
            try:
                assert_version_metadata_matches_db(version, spk)
            except ValueError as e:
                abort(422, message=str(e))
        else:
            create_version = True
            version_startable = True
            if spk.info.get("startable") is False or spk.info.get("ctl_stop") is False:
                version_startable = False
            version = Version(
                package=package,
                upstream_version=match.group("upstream_version"),
                version=int(match.group("version")),
                report_url=spk.info.get("report_url"),
                distributor=spk.info.get("distributor"),
                distributor_url=spk.info.get("distributor_url"),
                maintainer=spk.info.get("maintainer"),
                maintainer_url=spk.info.get("maintainer_url"),
                install_wizard="install" in spk.wizards,
                upgrade_wizard="upgrade" in spk.wizards,
                startable=version_startable,
                license=spk.license,
            )

            with db.session.no_autoflush:
                for key, value in spk.info.items():
                    if key == "install_dep_services":
                        version.service_dependencies = services
                    elif key == "displayname":
                        version.displaynames["enu"] = DisplayName(
                            language=Language.find("enu"), displayname=value
                        )
                    elif key.startswith("displayname_"):
                        language = Language.find(key.split("_", 1)[1])
                        if not language:
                            abort(422, message="Unknown INFO displayname language")
                        version.displaynames[language.code] = DisplayName(
                            language=language, displayname=value
                        )

            # Icon
            for size, icon in spk.icons.items():
                version.icons[size] = Icon(
                    path=os.path.join(
                        package.name, str(version.version), f"icon_{size}.png"
                    ),
                    size=size,
                )

        # Build — conflict check is a no-op for new versions but kept unconditional
        conflicts = set()
        for existing_build in version.builds:
            overlapping_architectures = set(existing_build.architectures) & set(
                architectures
            )
            if not overlapping_architectures:
                continue
            existing_min_build = existing_build.firmware_min.build
            existing_max_build = (
                existing_build.firmware_max.build
                if existing_build.firmware_max
                else existing_min_build
            )
            candidate_min_build = firmware.build
            candidate_max_build = (
                firmware_max.build if firmware_max is not None else candidate_min_build
            )
            if (
                candidate_min_build > existing_max_build
                or candidate_max_build < existing_min_build
            ):
                continue
            conflicts |= overlapping_architectures
        if conflicts:
            conflict_codes = ", ".join(sorted(a.code for a in conflicts))
            abort(409, message=f"Conflicting architectures: {conflict_codes}")

        build_filename = Build.generate_filename(
            package, version, firmware, architectures
        )
        build = Build(
            version=version,
            architectures=architectures,
            firmware_min=firmware,
            firmware_max=firmware_max,
            publisher=current_user,
            path=os.path.join(package.name, str(version.version), build_filename),
            checksum=spk.info.get("checksum"),
            changelog=spk.info.get("changelog"),
        )

        with db.session.no_autoflush:
            for key, value in spk.info.items():
                if key == "description":
                    build.descriptions["enu"] = BuildDescription(
                        description=value, language=Language.find("enu")
                    )
                elif key.startswith("description_"):
                    language = Language.find(key.split("_", 1)[1])
                    if not language:
                        abort(422, message="Unknown INFO description language")
                    build.descriptions[language.code] = BuildDescription(
                        language=language, description=value
                    )

        build.buildmanifest = BuildManifest(
            dependencies=spk.info.get("install_dep_packages"),
            conf_dependencies=spk.conf_dependencies,
            conflicts=spk.info.get("install_conflict_packages"),
            conf_conflicts=spk.conf_conflicts,
            conf_privilege=spk.conf_privilege,
            conf_resource=spk.conf_resource,
        )

        # sign
        if current_app.config["GNUPG_PATH"] is not None:  # pragma: no cover
            try:
                spk.sign(
                    current_app.config["GNUPG_TIMESTAMP_URL"],
                    current_app.config["GNUPG_PATH"],
                )
            except SPKSignError as e:
                abort(500, message="Failed to sign package", details=str(e))
        if spk.signature is not None:
            build.signed = True

        # save files
        try:
            data_path = current_app.config["DATA_PATH"]
            if create_package:
                os.makedirs(os.path.join(data_path, package.name), exist_ok=True)
            if create_version:
                os.makedirs(
                    os.path.join(data_path, package.name, str(version.version)),
                    exist_ok=True,
                )
                for size, icon in build.version.icons.items():
                    icon.save(spk.icons[size])
            build.save(spk.stream)
            build.md5 = build.calculate_md5()
            build.size = build.calculate_size()
        except Exception as e:  # pragma: no cover
            logger.exception("Failed to save SPK files for package %s", package.name)
            _cleanup_on_failure(
                data_path,
                package.name,
                version.version,
                build.path,
                create_package,
                create_version,
            )
            abort(500, message="Failed to save files", details=str(e))

        # insert the package into database
        db.session.add(build)
        db.session.commit()

        return (
            {
                "package": package.name,
                "version": version.version_string,
                "firmware": firmware.firmware_string,
                "architectures": [a.code for a in architectures],
            },
            201,
        )


restful_api = Api(api, decorators=[api_auth_required])
restful_api.add_resource(Packages, "/packages")
