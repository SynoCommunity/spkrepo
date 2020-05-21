# -*- coding: utf-8 -*-
import io
import os
import re
import shutil
from functools import wraps

from flask import Blueprint, _request_ctx_stack, current_app, request
from flask_principal import Identity, identity_changed
from flask_restful import Api, Resource, abort
from flask_security import current_user

from ..exceptions import SPKParseError, SPKSignError
from ..ext import db
from ..models import (
    Architecture,
    Build,
    Description,
    DisplayName,
    Firmware,
    Icon,
    Language,
    Package,
    Service,
    Version,
    user_datastore,
)
from ..utils import SPK

api = Blueprint("api", __name__)

# regexes
firmware_re = re.compile(r"^(?P<version>\d\.\d)-(?P<build>\d{3,6})$")
version_re = re.compile(r"^(?P<upstream_version>.*)-(?P<version>\d+)$")


def api_auth_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if request.authorization and request.authorization.type == "basic":
            user = user_datastore.find_user(api_key=request.authorization.username)
            if user and user.has_role("developer"):
                _request_ctx_stack.top.user = user
                identity_changed.send(
                    current_app._get_current_object(), identity=Identity(user.id)
                )
                return f(*args, **kwargs)
        abort(401)

    return wrapper


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
        architectures = []
        for info_arch in spk.info["arch"].split():
            architecture = Architecture.find(info_arch, syno=True)
            if architecture is None:
                abort(422, message="Unknown architecture: %s" % info_arch)
            architectures.append(architecture)

        # Firmware
        input_firmware = spk.info.get("firmware")
        if input_firmware is None:
            input_firmware = spk.info.get("os_min_ver")
        match = firmware_re.match(input_firmware)
        if not match:
            abort(422, message="Invalid firmware")
        firmware = Firmware.find(int(match.group("build")))
        if firmware is None:
            abort(422, message="Unknown firmware")

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
        # TODO: check discrepencies with what's in the database
        version = {v.version: v for v in package.versions}.get(
            int(match.group("version"))
        )
        if version is None:
            create_version = True
            version_startable = None
            if spk.info.get("startable") is False or spk.info.get("ctl_stop") is False:
                version_startable = False
            elif spk.info.get("startable") is True or spk.info.get("ctl_stop") is True:
                version_startable = True
            version = Version(
                package=package,
                upstream_version=match.group("upstream_version"),
                version=int(match.group("version")),
                changelog=spk.info.get("changelog"),
                report_url=spk.info.get("report_url"),
                distributor=spk.info.get("distributor"),
                distributor_url=spk.info.get("distributor_url"),
                maintainer=spk.info.get("maintainer"),
                maintainer_url=spk.info.get("maintainer_url"),
                dependencies=spk.info.get("install_dep_packages"),
                conf_dependencies=spk.conf_dependencies,
                conflicts=spk.info.get("install_conflict_packages"),
                conf_conflicts=spk.conf_conflicts,
                conf_privilege=spk.conf_privilege,
                conf_resource=spk.conf_resource,
                install_wizard="install" in spk.wizards,
                upgrade_wizard="upgrade" in spk.wizards,
                startable=version_startable,
                license=spk.license,
            )

            for key, value in spk.info.items():
                if key == "install_dep_services":
                    for service_name in value.split():
                        version.service_dependencies.append(Service.find(service_name))
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
                elif key == "description":
                    version.descriptions["enu"] = Description(
                        description=value, language=Language.find("enu")
                    )
                elif key.startswith("description_"):
                    language = Language.find(key.split("_", 1)[1])
                    if not language:
                        abort(422, message="Unknown INFO description language")
                    version.descriptions[language.code] = Description(
                        language=language, description=value
                    )

            # Icon
            for size, icon in spk.icons.items():
                version.icons[size] = Icon(
                    path=os.path.join(
                        package.name, str(version.version), "icon_%s.png" % size
                    ),
                    size=size,
                )

        # Build
        if version.id:
            # check for conflicts
            conflicts = set(architectures) & set(
                Architecture.query.join(Architecture.builds)
                .filter_by(version=version, firmware=firmware)
                .all()
            )
            if conflicts:
                abort(
                    409,
                    message="Conflicting architectures: %s"
                    % (", ".join(sorted(a.code for a in conflicts))),
                )

        build_filename = Build.generate_filename(
            package, version, firmware, architectures
        )
        build = Build(
            version=version,
            architectures=architectures,
            firmware=firmware,
            publisher=current_user,
            path=os.path.join(package.name, str(version.version), build_filename),
            checksum=spk.info.get("checksum"),
        )

        # sign
        if current_app.config["GNUPG_PATH"] is not None:  # pragma: no cover
            try:
                spk.sign(
                    current_app.config["GNUPG_TIMESTAMP_URL"],
                    current_app.config["GNUPG_PATH"],
                )
            except SPKSignError as e:
                abort(500, message="Failed to sign package", details=e.message)

        # save files
        try:
            data_path = current_app.config["DATA_PATH"]
            if create_package:
                os.mkdir(os.path.join(data_path, package.name))
            if create_version:
                os.mkdir(os.path.join(data_path, package.name, str(version.version)))
                for size, icon in build.version.icons.items():
                    icon.save(spk.icons[size])
            build.save(spk.stream)
        except Exception as e:  # pragma: no cover
            if create_package:
                shutil.rmtree(os.path.join(data_path, package.name), ignore_errors=True)
            elif create_version:
                shutil.rmtree(
                    os.path.join(data_path, package.name, str(version.version)),
                    ignore_errors=True,
                )
            else:
                try:
                    os.remove(os.path.join(data_path, build.path))
                except OSError:
                    pass
            abort(500, message="Failed to save files", details=e.message)

        # insert the package into database
        db.session.add(build)
        db.session.commit()

        # success
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
