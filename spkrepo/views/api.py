# -*- coding: utf-8 -*-
"""SPK upload API adapter (Flask-RESTful).

Implements ``POST /api/packages``. Parses uploads via
:mod:`spkrepo.adapters.spk_io`, validates against :mod:`spkrepo.domain`,
and maps outcomes to HTTP status codes.
"""

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
from sqlalchemy.exc import IntegrityError

from ..adapters.repositories import resolve_architectures, resolve_firmware
from ..adapters.spk_io import SPK
from ..domain.versions import assert_version_metadata_matches_db
from ..exceptions import SPKParseError, SPKSignError
from ..ext import db
from ..models import (
    Build,
    BuildDescription,
    BuildManifest,
    DisplayName,
    Icon,
    Package,
    Version,
    user_datastore,
)

logger = logging.getLogger(__name__)

api = Blueprint("api", __name__)


def api_auth_required(f):
    """Require HTTP Basic auth with a ``developer``-role API key (else 401)."""

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

        try:
            spk = SPK(io.BytesIO(request.data))
        except SPKParseError as e:
            abort(422, message=str(e))

        if spk.signature is not None:
            abort(422, message="Package contains a signature")

        try:
            architectures = resolve_architectures(db.session, spk.info.get("arch"))
        except ValueError as e:
            abort(422, message=str(e))

        input_firmware = spk.info.get("firmware") or spk.info.get("os_min_ver")
        try:
            firmware = resolve_firmware(db.session, input_firmware)
        except ValueError as e:
            abort(422, message=str(e))

        firmware_max = None
        input_firmware_max = spk.info.get("os_max_ver")
        if input_firmware_max:
            try:
                firmware_max = resolve_firmware(db.session, input_firmware_max)
            except ValueError as e:
                abort(422, message=str(e))
            from ..domain.upload import validate_firmware_range as _validate_fw

            try:
                _validate_fw(firmware.build, firmware_max.build)
            except ValueError as e:
                abort(422, message=str(e))

        # Package (pure auth decision in domain.upload; adapter maps to HTTP)
        from ..domain.upload import authorize_upload as _authorize

        create_package = False
        package = Package.find(spk.info["package"])
        try:
            _authorize(
                {r.name for r in current_user.roles} if current_user else set(),
                is_new_package=package is None,
                is_maintainer=package is not None
                and current_user in package.maintainers,
            )
        except PermissionError as e:
            abort(403, message=str(e))
        if package is None:
            create_package = True
            package = Package(name=spk.info["package"], author=current_user)

        # Version (shared writer; pure parsing in domain.shared_kernel)
        from ..adapters.persistence import assign_version_common_fields
        from ..adapters.repositories import (
            resolve_displayname_languages as _resolve_names,
        )
        from ..domain.shared_kernel import parse_version as _parse_version

        create_version = False
        try:
            _, version_number = _parse_version(spk.info["version"])
        except (ValueError, KeyError):
            abort(422, message="Invalid version")

        version = {v.version: v for v in package.versions}.get(version_number)

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
            version = Version(
                package=package, upstream_version="", version=version_number
            )
            try:
                assign_version_common_fields(version, spk)
            except ValueError as e:
                abort(422, message=str(e))

            with db.session.no_autoflush:
                try:
                    displaynames = _resolve_names(spk.info)
                except ValueError:
                    abort(422, message="Unknown INFO displayname language")
                from ..domain.shared_kernel import map_displaynames as _map_names

                raw_names = _map_names(spk.info)
                for code, language in displaynames.items():
                    version.displaynames[language.code] = DisplayName(
                        language=language, displayname=raw_names[code]
                    )

            for size, icon in spk.icons.items():
                version.icons[size] = Icon(
                    path=os.path.join(
                        package.name, str(version.version), f"icon_{size}.png"
                    ),
                    size=size,
                )

        # Build — conflict check is a no-op for new versions but kept unconditional
        # Pure domain check (hex): snapshots keep DB objects out of the policy.
        from ..domain.upload import detect_conflicts

        existing_snapshot = [
            {
                "archs": {a.code for a in b.architectures},
                "min": b.firmware_min.build,
                "max": (
                    b.firmware_max.build if b.firmware_max else b.firmware_min.build
                ),
            }
            for b in version.builds
        ]
        conflicts = detect_conflicts(
            existing_snapshot,
            {a.code for a in architectures},
            firmware.build,
            firmware_max.build if firmware_max is not None else None,
        )
        if conflicts:
            conflict_codes = ", ".join(sorted(conflicts))
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

        from ..adapters.repositories import (
            resolve_description_languages as _resolve_desc,
        )
        from ..domain.shared_kernel import map_descriptions as _descriptions

        with db.session.no_autoflush:
            try:
                desc_langs = _resolve_desc(spk.info)
            except ValueError:
                abort(422, message="Unknown INFO description language")
            raw_desc = _descriptions(spk.info)
            for code, language in desc_langs.items():
                build.descriptions[language.code] = BuildDescription(
                    language=language, description=raw_desc[code]
                )

        build.buildmanifest = BuildManifest(
            dependencies=spk.info.get("install_dep_packages"),
            conf_dependencies=spk.conf_dependencies,
            conflicts=spk.info.get("install_conflict_packages"),
            conf_conflicts=spk.conf_conflicts,
            conf_privilege=spk.conf_privilege,
            conf_resource=spk.conf_resource,
        )

        if current_app.config["GNUPG_PATH"] is not None:
            try:
                spk.sign(
                    current_app.config["GNUPG_TIMESTAMP_URL"],
                    current_app.config["GNUPG_PATH"],
                )
            except SPKSignError as e:
                abort(500, message="Failed to sign package", details=str(e))
        if spk.signature is not None:
            build.signed = True

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
        try:
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            if "version_package_id_version_key" in str(e):
                msg = (
                    f"Version {version.version_string} already exists"
                    f" for {package.name}"
                )
            elif "package_name_key" in str(e):
                msg = f"Package {package.name} was created by another request"
            else:
                msg = "Database constraint violation"
            abort(409, message=msg)

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
