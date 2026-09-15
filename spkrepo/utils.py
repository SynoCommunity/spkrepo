# -*- coding: utf-8 -*-
"""SPK tar adapter and shared upload/resync writers over :mod:`spkrepo.domain`.

Archive I/O, DB lookups, and file writes stay here; parsing, validation,
and metadata mapping live in the domain layer.
"""
import hashlib
import io
import json
import os
import re
import tarfile
import time

import gnupg
import requests
from flask import current_app

from .domain.shared_kernel import parse_firmware
from .domain.spk import BOOLEAN_INFO as _DOMAIN_BOOLEAN_INFO
from .domain.spk import REQUIRED_INFO as _DOMAIN_REQUIRED_INFO
from .domain.spk import icon_info_re as _domain_icon_info_re
from .domain.spk import info_line_re as _domain_info_line_re
from .domain.spk import package_re as _domain_package_re
from .domain.spk import wizard_filename_re as _domain_wizard_filename_re
from .exceptions import SPKParseError, SPKSignError
from .ext import db
from .models import (
    Architecture,
    BuildDescription,
    BuildManifest,
    DisplayName,
    Firmware,
    Icon,
    Language,
    Role,
    Service,
)


class SPK(object):
    """SPK utilities

    :param fileobj stream: SPK file stream
    """

    #: Required keys in the INFO file (single owner: domain.spk)
    REQUIRED_INFO = _DOMAIN_REQUIRED_INFO

    #: Boolean INFO keys (single owner: domain.spk)
    BOOLEAN_INFO = _DOMAIN_BOOLEAN_INFO

    #: Signature filename
    SIGNATURE_FILENAME = "syno_signature.asc"

    #: Regex for a line of the INFO file (single owner: domain.spk)
    info_line_re = _domain_info_line_re

    #: Regex for package in INFO file (single owner: domain.spk)
    package_re = _domain_package_re

    #: Regex for a wizard filename (single owner: domain.spk)
    wizard_filename_re = _domain_wizard_filename_re

    #: Regex for icons in INFO (single owner: domain.spk)
    icon_info_re = _domain_icon_info_re

    #: Regex for icons in files
    icon_filename_re = re.compile(r"^PACKAGE_ICON(?:_(?P<size>120|256))?\.PNG$")

    #: Regex for files in scripts
    script_filename_re = re.compile(r"^scripts/.+$")

    #: Regex for files in conf
    conf_filename_re = re.compile(r"^conf/.+$")

    #: Regex for firmware input
    firmware_version_re = re.compile(r"^\d+\.\d$")
    firmware_type_re = re.compile(r"^([a-z]){3,}$")

    def __init__(self, stream):
        self.info = {}
        self.icons = {}
        self.wizards = set()
        self.license = None
        self.signature = None
        self.stream = stream
        self.conf_dependencies = None
        self.conf_conflicts = None
        self.conf_privilege = None
        self.conf_resource = None

        self.stream.seek(0)
        try:
            with tarfile.open(fileobj=self.stream, mode="r:") as spk:
                names = spk.getnames()

                # check for required files
                if "INFO" not in names:
                    raise SPKParseError("Missing INFO file")
                if "package.tgz" not in names:
                    raise SPKParseError("Missing package.tgz file")

                # read LICENSE file
                if "LICENSE" in names:
                    try:
                        self.license = (
                            spk.extractfile("LICENSE").read().decode("utf-8").strip()
                        )
                    except UnicodeDecodeError:
                        raise SPKParseError("Wrong LICENSE encoding")

                # read syno_signature.asc file
                if "syno_signature.asc" in names:
                    try:
                        self.signature = (
                            spk.extractfile("syno_signature.asc")
                            .read()
                            .decode("ascii")
                            .strip()
                        )
                    except UnicodeDecodeError:
                        raise SPKParseError("Wrong syno_signature.asc encoding")

                # read INFO lines (pure parsing in domain.spk; tar I/O stays here)
                from .domain.spk import parse_info_lines, validate_required

                raw_lines = spk.extractfile("INFO").readlines()
                self.info, raw_icons = parse_info_lines(raw_lines)
                for size, payload in raw_icons.items():
                    self.icons[size] = io.BytesIO(payload)

                validate_required(self.info)

                # read conf files (bytes I/O here, pure parsing in domain.spk)
                if (
                    "support_conf_folder" in self.info
                    and self.info["support_conf_folder"]
                ):
                    from .domain.spk import parse_conf_file, parse_json_conf

                    if "conf" not in names:
                        raise SPKParseError("Missing conf folder")
                    if "conf/PKG_DEPS" in names:
                        raw = spk.extractfile("conf/PKG_DEPS").read()
                        self.conf_dependencies = json.dumps(
                            parse_conf_file(raw, "conf/PKG_DEPS")
                        )
                    if "conf/PKG_CONX" in names:
                        raw = spk.extractfile("conf/PKG_CONX").read()
                        self.conf_conflicts = json.dumps(
                            parse_conf_file(raw, "conf/PKG_CONX")
                        )
                    if "conf/privilege" in names:
                        raw = spk.extractfile("conf/privilege").read()
                        self.conf_privilege = parse_json_conf(raw, "conf/privilege")
                    if "conf/resource" in names:
                        raw = spk.extractfile("conf/resource").read()
                        self.conf_resource = parse_json_conf(raw, "conf/resource")
                    if (
                        self.conf_dependencies is None
                        and self.conf_conflicts is None
                        and self.conf_privilege is None
                        and self.conf_resource is None
                    ):
                        raise SPKParseError("Empty conf folder")

                # verify checksum (pure bytes check in domain.spk)
                if "checksum" in self.info:
                    from .domain.spk import verify_checksum

                    archive = spk.extractfile("package.tgz")
                    verify_checksum(self.info["checksum"], archive.read())

                # read icon files
                for name in names:
                    match = self.icon_filename_re.match(name)
                    if match:
                        self.icons[match.group("size") or "72"] = io.BytesIO(
                            spk.extractfile(name).read()
                        )

                if "72" not in self.icons:
                    raise SPKParseError("Missing 72px icon")

                # read wizard files
                if "WIZARD_UIFILES" in names:
                    for name in names:
                        match = self.wizard_filename_re.match(name)
                        if match:
                            self.wizards.add(match.group("process"))
        except tarfile.TarError:
            raise SPKParseError("Invalid SPK")
        self.stream.seek(0)

    def sign(self, timestamp_url, gnupghome):
        """Append a detached GPG + timestamp signature to the package stream.

        GPG/timestamp I/O stays here (see :mod:`spkrepo.domain` rule);
        raises ``ValueError`` if already signed, ``SPKSignError`` on failure.

        :param timestamp_url: url for the remote timestamping
        :param gnupghome: path to the gnupg home
        """
        if self.signature is not None:
            raise ValueError("Already signed")

        with io.BytesIO() as data_stream:
            self.stream.seek(0)
            with tarfile.open(fileobj=self.stream, mode="r:") as spk:
                names = sorted(spk.getnames())
                if "INFO" in names:
                    data_stream.write(spk.extractfile("INFO").read())
                if "LICENSE" in names:
                    data_stream.write(spk.extractfile("LICENSE").read())
                for name in names:
                    match = self.icon_filename_re.match(name)
                    if match:
                        data_stream.write(spk.extractfile(name).read())
                for name in names:
                    match = self.wizard_filename_re.match(name)
                    if match:
                        data_stream.write(spk.extractfile(name).read())
                for name in names:
                    match = self.conf_filename_re.match(name)
                    if match:
                        data_stream.write(spk.extractfile(name).read())
                if "package.tgz" in names:
                    data_stream.write(spk.extractfile("package.tgz").read())
                for name in names:
                    match = self.script_filename_re.match(name)
                    if match:
                        data_stream.write(spk.extractfile(name).read())

            data_stream.seek(0)
            signature = self._generate_signature(data_stream, timestamp_url, gnupghome)
            self.signature = signature

            signature_stream = io.BytesIO(signature.encode("ascii"))
            signature_tarinfo = tarfile.TarInfo(self.SIGNATURE_FILENAME)
            signature_tarinfo.mtime = time.time()
            signature_stream.seek(0, io.SEEK_END)
            signature_tarinfo.size = signature_stream.tell()
            signature_stream.seek(0)
            self.stream.seek(0)
            with tarfile.open(fileobj=self.stream, mode="a:") as spk:
                spk.addfile(tarinfo=signature_tarinfo, fileobj=signature_stream)
            self.stream.seek(0)

    def unsign(self):
        """Remove the signature file from the package stream in place."""
        if self.signature is None:
            raise ValueError("Not signed")

        with io.BytesIO() as unsigned_stream:
            self.stream.seek(0)
            with tarfile.open(fileobj=self.stream, mode="r:") as spk:
                with tarfile.open(fileobj=unsigned_stream, mode="w:") as unsigned_spk:
                    for member in spk.getmembers():
                        if member.name == self.SIGNATURE_FILENAME:
                            continue
                        unsigned_spk.addfile(member, spk.extractfile(member))
            unsigned_stream.seek(0)
            self.stream.seek(0)
            self.stream.write(unsigned_stream.read())
        self.stream.truncate()
        self.stream.seek(0)

    def calculate_md5(self):
        md5_hash = hashlib.md5()
        self.stream.seek(0)
        for chunk in iter(lambda: self.stream.read(4096), b""):
            md5_hash.update(chunk)
        return md5_hash.hexdigest()

    def _generate_signature(self, stream, timestamp_url, gnupghome):  # pragma: no cover
        gpg = gnupg.GPG(gnupghome=gnupghome)
        signature = gpg.sign_file(stream, detach=True)

        try:
            response = requests.post(
                timestamp_url, files={"file": signature.data}, timeout=2
            )
        except requests.RequestException:
            raise SPKSignError("Timestamp server did not respond in time")

        if response.status_code != 200:
            raise SPKSignError(
                f"Timestamp server returned with status code {response.status_code}"
            )

        if not gpg.verify(response.content):
            raise SPKSignError("Cannot verify timestamp")

        response.encoding = "ascii"
        return response.text


# ---------------------------------------------------------------------------
# Shared SPK processing helpers
# ---------------------------------------------------------------------------


def resolve_firmware(session, value, allow_none=False):
    """Resolve a firmware string like '6.2-23739' to a
    :class:`~spkrepo.models.Firmware`.

    Adapter: pure parsing via :func:`spkrepo.domain.shared_kernel.parse_firmware`,
    DB lookup via ``Firmware.find``. Pass a session for ``merge``.

    :param session: SQLAlchemy session
    :param value: firmware string from SPK INFO
    :param allow_none: if True, a missing/empty value returns None instead of raising
    :raises ValueError: if the value is missing (and allow_none is False), malformed,
                        or not found in the database
    """
    if not value:
        if allow_none:
            return None
        raise ValueError("Missing firmware information in INFO")

    try:
        _, build = parse_firmware(value)
    except ValueError:
        raise ValueError(f"Invalid firmware value: {value}")

    firmware = Firmware.find(build)
    if firmware is None:
        raise ValueError(f"Unknown firmware: {value}")

    return session.merge(firmware, load=False)


def resolve_architectures(session, arch_string):
    """Resolve a space-separated architecture string from SPK INFO to a list of
    :class:`~spkrepo.models.Architecture` instances.

    :param session: SQLAlchemy session
    :param arch_string: space-separated arch string e.g. "88f628x x86_64"
    :raises ValueError: if arch_string is missing or any architecture is unknown
    """
    if not arch_string:
        raise ValueError("Missing 'arch' field in INFO")
    architectures = []
    for info_arch in arch_string.split():
        architecture = Architecture.find(info_arch, syno=True)
        if architecture is None:
            raise ValueError(f"Unknown architecture: {info_arch}")
        architectures.append(session.merge(architecture, load=False))
    return architectures


def resolve_services(service_string):
    """Resolve a space-separated service dependency string from SPK INFO to a list of
    :class:`~spkrepo.models.Service` instances.

    :param service_string: space-separated service codes e.g. "apache-web mysql",
                           or None/empty for no dependencies
    :raises ValueError: if any service code is not found in the database
    """
    if not service_string:
        return []
    services = []
    for service_code in service_string.split():
        service = Service.find(service_code)
        if service is None:
            raise ValueError(f"Unknown dependent service: {service_code}")
        services.append(service)
    return services


def resolve_displayname_languages(info) -> dict[str, "Language"]:
    """Single-owner Language lookup for INFO displaynames.

    Pure mapping via :func:`spkrepo.domain.shared_kernel.map_displaynames`, DB
    lookup via ``Language.find``. Raises ``ValueError`` on unknown codes;
    HTTP adapters map this to 422.
    """
    from .domain.shared_kernel import map_displaynames as _map

    resolved: dict[str, Language] = {}
    for code in _map(info):
        language = Language.find(code)
        if language is None:
            raise ValueError(f"Unknown INFO displayname language: {code}")
        resolved[code] = language
    return resolved


def resolve_description_languages(info) -> dict[str, "Language"]:
    """Single-owner Language lookup for INFO descriptions.

    Raises ``ValueError`` on unknown codes; HTTP adapters map to 422.
    """
    from .domain.shared_kernel import map_descriptions as _map

    resolved: dict[str, Language] = {}
    for code in _map(info):
        language = Language.find(code)
        if language is None:
            raise ValueError(f"Unknown INFO description language: {code}")
        resolved[code] = language
    return resolved


def assign_version_common_fields(version, spk) -> None:
    """Single-owner writer for version-level fields shared by upload/resync.

    Assigns upstream_version, report/distributor/maintainer URLs, wizards,
    startable (via domain), license and service dependencies. Localized
    displaynames are handled by :func:`resolve_displayname_languages` +
    caller-owned relationship assignment (create vs clear semantics differ).
    """
    from .domain.shared_kernel import derive_startable as _startable
    from .domain.shared_kernel import parse_version as _parse_version

    info = spk.info if hasattr(spk, "info") else spk
    wizards = getattr(spk, "wizards", set())
    upstream, _ = _parse_version(info.get("version", ""))
    version.upstream_version = upstream
    version.report_url = info.get("report_url")
    version.distributor = info.get("distributor")
    version.distributor_url = info.get("distributor_url")
    version.maintainer = info.get("maintainer")
    version.maintainer_url = info.get("maintainer_url")
    version.install_wizard = "install" in wizards
    version.upgrade_wizard = "upgrade" in wizards
    version.startable = _startable(info)
    version.license = getattr(spk, "license", info.get("license"))
    version.service_dependencies = resolve_services(info.get("install_dep_services"))


def extract_version_metadata(spk):
    """Extract all version-level fields from an SPK into a plain dict.

    Adapter over :mod:`spkrepo.domain.versions` (single owner); kept here
    for backward compatibility.
    """
    from .domain.versions import extract_version_metadata as _pure

    return _pure(spk)


def assert_version_metadata_matches_db(version, spk):
    """Raise :exc:`ValueError` on version-level metadata conflicts.

    Adapter over :mod:`spkrepo.domain.versions` (single owner); kept here
    for backward compatibility.
    """
    from .domain.versions import assert_version_metadata_matches_db as _pure

    return _pure(version, spk)


def apply_info_from_spk(session, build, spk, md5_hash):
    """Apply all metadata from a parsed SPK onto the given build and its parent
    version. Resync-only entry point (``views/tasks.py``'s
    ``resync_build_metadata``, triggered from ``views/admin.py``); the upload
    path (``views/api.py``'s ``Packages.post``) creates new records instead.
    Shared version-level fields converge on
    :func:`spkrepo.utils.assign_version_common_fields` in both paths, while
    displaynames/descriptions/icons diverge by design (resync clears and
    rewrites; upload creates once).

    Version-level fields (shared across all builds of a version) are written
    unconditionally — callers must ensure consistency has already been checked
    via :func:`spkrepo.utils.assert_version_metadata_matches_db` before calling this.

    .. note::
        Icon files are written to disk before the database is flushed. If a
        subsequent error causes the caller to roll back the session, any newly
        written icon files will be left on disk. Callers that require strict
        atomicity should handle cleanup themselves (e.g. via
        :func:`~spkrepo.views.api._cleanup_on_failure`).

    .. note::
        This function calls ``session.flush()`` at the end to push all pending
        changes to the database within the current transaction. The caller is
        responsible for committing or rolling back.

    :param session: SQLAlchemy session
    :param build: the :class:`~spkrepo.models.Build` to update
    :param spk: a parsed :class:`SPK` instance
    :param md5_hash: pre-calculated MD5 hex string of the SPK file
    :raises ValueError: on any validation failure (package mismatch, bad version, etc.)
    """
    with session.no_autoflush:
        from .domain.shared_kernel import map_descriptions as _descriptions
        from .domain.shared_kernel import map_displaynames as _displaynames
        from .domain.shared_kernel import parse_version as _parse_version

        info = spk.info
        package = build.version.package

        if info.get("package") != package.name:
            raise ValueError("INFO package does not match build package")

        try:
            _, version_number = _parse_version(info.get("version", ""))
        except ValueError:
            raise ValueError("Invalid INFO version value")

        if version_number != build.version.version:
            raise ValueError("INFO version does not match build version")

        # -- Version-level fields (shared writer; upload path converges here) --
        version = build.version
        build.changelog = info.get("changelog")
        assign_version_common_fields(version, spk)

        version.displaynames.clear()
        for language_code, displayname in _displaynames(info).items():
            language = Language.find(language_code)
            if language is None:
                raise ValueError(
                    f"Unknown INFO displayname language: {language_code}"
                )
            version.displaynames[language.code] = DisplayName(
                language=language, displayname=displayname
            )

        build.descriptions.clear()
        for language_code, description in _descriptions(info).items():
            language = Language.find(language_code)
            if language is None:
                raise ValueError(
                    f"Unknown INFO description language: {language_code}"
                )
            build.descriptions[language.code] = BuildDescription(
                language=language, description=description
            )

        # Icon files are written to disk here. If anything raises after this point
        # the caller's session rollback will undo the DB changes but the files will
        # remain on disk — see docstring note above.
        existing_icons = dict(version.icons)
        new_sizes = set(spk.icons.keys()) if spk.icons else set()
        written_icon_paths = []
        for stale_size in set(existing_icons) - new_sizes:
            del version.icons[stale_size]

        if spk.icons:
            version_path = os.path.join(
                current_app.config["DATA_PATH"], package.name, str(version.version)
            )
            os.makedirs(version_path, exist_ok=True)
            try:
                for size, icon_stream in spk.icons.items():
                    icon_stream.seek(0)
                    icon_path = os.path.join(
                        package.name, str(version.version), f"icon_{size}.png"
                    )
                    icon = version.icons.get(size)
                    if icon is None:
                        icon = Icon(path=icon_path, size=size)
                        version.icons[size] = icon
                    else:
                        icon.path = icon_path
                    icon.save(icon_stream)
                    written_icon_paths.append(
                        os.path.join(current_app.config["DATA_PATH"], icon_path)
                    )
            except Exception:
                # Clean up any icon files written in this call before re-raising,
                # so a failed resync does not leave orphaned files on disk.
                for path in written_icon_paths:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                raise

        # -- Build-level fields --------------------------------------------------

        build.architectures = resolve_architectures(session, info.get("arch"))
        build.firmware_min = resolve_firmware(
            session, info.get("firmware") or info.get("os_min_ver")
        )

        firmware_max_value = info.get("os_max_ver")
        firmware_max = resolve_firmware(session, firmware_max_value, allow_none=True)
        from .domain.upload import validate_firmware_range as _validate_fw

        try:
            _validate_fw(
                build.firmware_min.build,
                firmware_max.build if firmware_max else None,
            )
        except ValueError as e:
            raise ValueError(str(e))
        build.firmware_max = firmware_max

        build.checksum = info.get("checksum")
        build.md5 = md5_hash
        build.signed = spk.signature is not None

        manifest = build.buildmanifest
        if manifest is None:
            manifest = BuildManifest()
            build.buildmanifest = manifest

        manifest.dependencies = info.get("install_dep_packages")
        manifest.conf_dependencies = spk.conf_dependencies
        manifest.conflicts = info.get("install_conflict_packages")
        manifest.conf_conflicts = spk.conf_conflicts
        manifest.conf_privilege = spk.conf_privilege
        manifest.conf_resource = spk.conf_resource

        session.flush()


def apply_sidecar_to_db(session, build, sidecar):
    """Apply sidecar metadata to a build and its version without the SPK archive.

    Sidecar field ownership differs from the SPK paths by design: version
    identity/URLs come from raw ``info``, wizard/startable/license flags
    from task-derived values (already resolved at upload time), and
    ``signed/storage`` mark the remote transition (sidecars only exist for
    remote builds). Upstream parsing converges on
    :func:`spkrepo.domain.shared_kernel.parse_upstream_lenient`.
    """
    from .domain.shared_kernel import parse_upstream_lenient

    info = sidecar["info"]
    derived = sidecar["derived"]
    calculated = sidecar["calculated"]

    version = build.version
    version.upstream_version = parse_upstream_lenient(info.get("version", ""))
    version.report_url = info.get("report_url")
    version.distributor = info.get("distributor")
    version.distributor_url = info.get("distributor_url")
    version.maintainer = info.get("maintainer")
    version.maintainer_url = info.get("maintainer_url")
    version.install_wizard = derived["install_wizard"]
    version.upgrade_wizard = derived["upgrade_wizard"]
    version.startable = derived["startable"]
    version.license = derived.get("license")

    build.changelog = info.get("changelog")
    build.checksum = info.get("checksum")
    build.md5 = calculated["md5"]
    build.size = calculated["size"]
    build.signed = True
    build.storage = "remote"

    session.flush()


def populate_db():
    """Populate the database"""
    db.session.execute(
        Architecture.__table__.insert().values(
            [
                {"code": "noarch"},
                {"code": "cedarview"},
                {"code": "88f628x"},
                {"code": "qoriq"},
            ]
        )
    )
    db.session.execute(
        Firmware.__table__.insert().values(
            [
                {"version": "3.1", "build": 1594, "type": "dsm"},
                {"version": "5.0", "build": 4458, "type": "dsm"},
                {"version": "6.2", "build": 23739, "type": "dsm"},
                {"version": "7.1", "build": 42661, "type": "dsm"},
            ]
        )
    )
    db.session.execute(
        Language.__table__.insert().values(
            [{"code": "enu", "name": "English"}, {"code": "fre", "name": "French"}]
        )
    )
    db.session.execute(
        Role.__table__.insert().values(
            [
                {"name": "admin", "description": "Administrator"},
                {"name": "package_admin", "description": "Package Administrator"},
                {"name": "developer", "description": "Developer"},
            ]
        )
    )
    db.session.execute(
        Service.__table__.insert().values([{"code": "apache-web"}, {"code": "mysql"}])
    )
