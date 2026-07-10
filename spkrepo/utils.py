# -*- coding: utf-8 -*-
import base64
import binascii
import hashlib
import io
import json
import os
import re
import tarfile
import time
from configparser import ConfigParser

import gnupg
import requests
from flask import current_app

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

#: Regex for a firmware string e.g. "6.2-23739"
firmware_re = re.compile(r"^(?P<version>\d+\.\d)-(?P<build>\d{3,6})$")

#: Regex for a version string e.g. "1.2.3-10"
version_re = re.compile(r"^(?P<upstream_version>.*)-(?P<version>\d+)$")


class SPK(object):
    """SPK utilities

    :param fileobj stream: SPK file stream
    """

    #: Required keys in the INFO file
    REQUIRED_INFO = {"package", "version", "arch", "displayname", "description"}

    #: Boolean INFO keys
    BOOLEAN_INFO = set(["ctl_stop", "startable", "support_conf_folder"])

    #: Signature filename
    SIGNATURE_FILENAME = "syno_signature.asc"

    #: Regex for a line of the INFO file
    info_line_re = re.compile(r'^(?P<key>\w+)="(?P<value>.*)"$', re.MULTILINE)

    #: Regex for package in INFO file
    package_re = re.compile(r"^[\w-]+$")

    #: Regex for a wizard filename
    wizard_filename_re = re.compile(
        (
            r"^WIZARD_UIFILES/(?P<process>install|upgrade|uninstall)"
            r"_uifile(?:_[a-z]{3})?(?:\.sh)?$"
        )
    )

    #: Regex for icons in INFO
    icon_info_re = re.compile(r"^package_icon(?:_(?P<size>120|256))?$")

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

                # read INFO lines
                for line in spk.extractfile("INFO").readlines():
                    try:
                        line = line.decode("utf-8").strip()
                    except UnicodeDecodeError:
                        raise SPKParseError("Wrong INFO encoding")

                    if not line:
                        continue

                    match = self.info_line_re.match(line)
                    if not match:
                        raise SPKParseError("Invalid INFO")
                    key, value = match.group("key"), match.group("value")

                    match = self.icon_info_re.match(key)
                    if match:
                        size = match.group("size") or "72"
                        try:
                            self.icons[size] = io.BytesIO(
                                base64.b64decode(value.encode("utf-8"))
                            )
                        except binascii.Error:
                            raise SPKParseError(f"Invalid INFO icon: {key}")
                        except TypeError:
                            raise SPKParseError(f"Invalid INFO icon: {key}")
                    elif key in self.BOOLEAN_INFO:
                        if value == "yes":
                            self.info[key] = True
                        elif value == "no":
                            self.info[key] = False
                        else:
                            raise SPKParseError(f"Invalid INFO boolean: {key}")
                    elif key == "package":
                        match = self.package_re.match(value)
                        if not match:
                            raise SPKParseError("Invalid INFO package")
                        self.info[key] = value
                    else:
                        self.info[key] = value

                # validate info
                if not set(self.info.keys()) >= self.REQUIRED_INFO:
                    missing = ", ".join(self.REQUIRED_INFO - set(self.info.keys()))
                    raise SPKParseError(f"Missing INFO: {missing}")

                # read conf files
                if (
                    "support_conf_folder" in self.info
                    and self.info["support_conf_folder"]
                ):
                    if "conf" not in names:
                        raise SPKParseError("Missing conf folder")
                    if "conf/PKG_DEPS" in names:
                        c = ConfigParser()
                        try:
                            c.read_string(
                                spk.extractfile("conf/PKG_DEPS").read().decode("utf-8")
                            )
                        except UnicodeDecodeError:
                            raise SPKParseError("Wrong conf/PKG_DEPS encoding")
                        self.conf_dependencies = json.dumps(
                            {s: {k: v for k, v in c.items(s)} for s in c.sections()}
                        )
                    if "conf/PKG_CONX" in names:
                        c = ConfigParser()
                        try:
                            c.read_string(
                                spk.extractfile("conf/PKG_CONX").read().decode("utf-8")
                            )
                        except UnicodeDecodeError:
                            raise SPKParseError("Wrong conf/PKG_CONX encoding")
                        self.conf_conflicts = json.dumps(
                            {s: {k: v for k, v in c.items(s)} for s in c.sections()}
                        )
                    if "conf/privilege" in names:
                        try:
                            conf_privilege = (
                                spk.extractfile("conf/privilege").read().decode("utf-8")
                            )
                        except UnicodeDecodeError:
                            raise SPKParseError("Wrong conf/privilege encoding")
                        try:
                            json.loads(conf_privilege)
                        except (json.JSONDecodeError, ValueError):
                            raise SPKParseError("File conf/privilege is not valid JSON")
                        self.conf_privilege = conf_privilege
                    if "conf/resource" in names:
                        try:
                            conf_resource = (
                                spk.extractfile("conf/resource").read().decode("utf-8")
                            )
                        except UnicodeDecodeError:
                            raise SPKParseError("Wrong conf/resource encoding")
                        try:
                            json.loads(conf_resource)
                        except (json.JSONDecodeError, ValueError):
                            raise SPKParseError("File conf/resource is not valid JSON")
                        self.conf_resource = conf_resource
                    if (
                        self.conf_dependencies is None
                        and self.conf_conflicts is None
                        and self.conf_privilege is None
                        and self.conf_resource is None
                    ):
                        raise SPKParseError("Empty conf folder")

                # verify checksum
                if "checksum" in self.info:
                    checksum = hashlib.md5()
                    archive = spk.extractfile("package.tgz")
                    for chunk in iter(
                        lambda: archive.read(io.DEFAULT_BUFFER_SIZE), b""
                    ):
                        checksum.update(chunk)
                    if checksum.hexdigest() != self.info["checksum"]:
                        raise SPKParseError("Checksum mismatch")

                # read icon files
                for name in names:
                    match = self.icon_filename_re.match(name)
                    if match:
                        self.icons[match.group("size") or "72"] = io.BytesIO(
                            spk.extractfile(name).read()
                        )

                # validate icons
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
        """
        Sign the package

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
        """Remove the signature file of the package"""
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

    match = firmware_re.match(value)
    if not match:
        raise ValueError(f"Invalid firmware value: {value}")

    firmware = Firmware.find(int(match.group("build")))
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


def extract_version_metadata(spk):
    """Extract all version-level fields from an SPK into a plain dict without
    touching the database. Used to compare builds of the same version for
    consistency before writing anything.

    :param spk: a parsed :class:`SPK` instance
    :returns: dict of version-level field values
    """
    info = spk.info
    version_match = version_re.match(info.get("version", ""))
    startable = True
    if info.get("startable") is False or info.get("ctl_stop") is False:
        startable = False
    # Normalise displaynames to language-code keys (matching DB storage):
    # INFO key "displayname" -> "enu", "displayname_fre" -> "fre", etc.
    # Note: create_info also emits "displayname_enu" alongside "displayname",
    # so we process suffixed keys first, then let the bare key set "enu" last,
    # ensuring an override of info["displayname"] is not shadowed by
    # info["displayname_enu"] still holding the original value.
    displaynames = {}
    for k, v in info.items():
        if k.startswith("displayname_"):
            displaynames[k.split("_", 1)[1]] = v
    if "displayname" in info:
        displaynames["enu"] = info["displayname"]

    return {
        "upstream_version": (
            version_match.group("upstream_version") if version_match else None
        ),
        "report_url": info.get("report_url"),
        "distributor": info.get("distributor"),
        "distributor_url": info.get("distributor_url"),
        "maintainer": info.get("maintainer"),
        "maintainer_url": info.get("maintainer_url"),
        "install_wizard": "install" in spk.wizards,
        "upgrade_wizard": "upgrade" in spk.wizards,
        "startable": startable,
        "license": spk.license,
        "install_dep_services": (
            set(info["install_dep_services"].split())
            if info.get("install_dep_services")
            else set()
        ),
        "displaynames": displaynames,
    }


def assert_version_metadata_matches_db(version, spk):
    """Raise :exc:`ValueError` if the SPK's version-level metadata conflicts with
    what is already stored on an existing :class:`~spkrepo.models.Version` record.

    Call this before writing anything when uploading a new build to an existing
    version, to ensure all builds within a version carry consistent metadata.

    :param version: the existing :class:`~spkrepo.models.Version` DB record
    :param spk: a parsed :class:`SPK` instance for the incoming build
    :raises ValueError: listing all mismatched fields if any inconsistency is found
    """
    incoming = extract_version_metadata(spk)
    mismatches = []

    simple_fields = (
        "upstream_version",
        "report_url",
        "distributor",
        "distributor_url",
        "maintainer",
        "maintainer_url",
        "install_wizard",
        "upgrade_wizard",
        "startable",
        "license",
    )
    for field in simple_fields:
        spk_val = incoming[field]
        db_val = getattr(version, field)
        # startable=None in the DB means "default true", same as SPK omitting the key
        if field == "startable" and db_val is None:
            db_val = True
        if spk_val != db_val:
            mismatches.append(f"{field}: SPK has {spk_val!r}, DB has {db_val!r}")

    existing_services = {s.code for s in version.service_dependencies}
    if incoming["install_dep_services"] != existing_services:
        mismatches.append(
            f"service_dependencies: SPK has {incoming['install_dep_services']}, "
            f"DB has {existing_services}"
        )

    existing_displaynames = {k: v.displayname for k, v in version.displaynames.items()}
    if incoming["displaynames"] != existing_displaynames:
        mismatches.append(
            f"displaynames: SPK has {incoming['displaynames']}, "
            f"DB has {existing_displaynames}"
        )

    if mismatches:
        raise ValueError(
            "SPK version-level metadata conflicts with existing builds:\n"
            + "\n".join(f"  - {m}" for m in mismatches)
        )


def apply_info_from_spk(session, build, spk, md5_hash):
    """Apply all metadata from a parsed SPK onto the given build and its parent
    version. Used by the resync path (tasks.py's resync_build_metadata,
    triggered from admin.py). NOT currently used by the upload path
    (api.py's Packages.post), which has its own separate, inline
    implementation of similar logic for creating new Package/Version/Build
    records — see that function if you need to keep both in sync.

    Version-level fields (shared across all builds of a version) are written
    unconditionally — callers must ensure consistency has already been checked
    via :func:`assert_version_metadata_matches_db` before calling this.

    .. note::
        Icon files are written to disk before the database is flushed. If a
        subsequent error causes the caller to roll back the session, any newly
        written icon files will be left on disk. Callers that require strict
        atomicity should handle cleanup themselves (e.g. via
        :func:`~spkrepo.api._cleanup_on_failure`).

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
        info = spk.info
        package = build.version.package

        if info.get("package") != package.name:
            raise ValueError("INFO package does not match build package")

        version_match = version_re.match(info.get("version", ""))
        if not version_match:
            raise ValueError("Invalid INFO version value")

        version_number = int(version_match.group("version"))
        if version_number != build.version.version:
            raise ValueError("INFO version does not match build version")

        # -- Version-level fields ------------------------------------------------

        version = build.version
        version.upstream_version = version_match.group("upstream_version")
        build.changelog = info.get("changelog")
        version.report_url = info.get("report_url")
        version.distributor = info.get("distributor")
        version.distributor_url = info.get("distributor_url")
        version.maintainer = info.get("maintainer")
        version.maintainer_url = info.get("maintainer_url")
        version.install_wizard = "install" in spk.wizards
        version.upgrade_wizard = "upgrade" in spk.wizards

        startable = True  # default per Synology docs
        if info.get("startable") is False or info.get("ctl_stop") is False:
            startable = False
        version.startable = startable

        version.license = spk.license
        version.service_dependencies = resolve_services(
            info.get("install_dep_services")
        )

        version.displaynames.clear()
        default_display = info.get("displayname")
        if default_display:
            language = Language.find("enu")
            if language is None:
                raise ValueError("Language 'enu' is not defined")
            version.displaynames[language.code] = DisplayName(
                language=language, displayname=default_display
            )
        for key, value in info.items():
            if key.startswith("displayname_"):
                language_code = key.split("_", 1)[1]
                language = Language.find(language_code)
                if language is None:
                    raise ValueError(
                        f"Unknown INFO displayname language: {language_code}"
                    )
                version.displaynames[language.code] = DisplayName(
                    language=language, displayname=value
                )

        build.descriptions.clear()
        default_description = info.get("description")
        if default_description:
            language = Language.find("enu")
            if language is None:
                raise ValueError("Language 'enu' is not defined")
            build.descriptions[language.code] = BuildDescription(
                language=language, description=default_description
            )
        for key, value in info.items():
            if key.startswith("description_"):
                language_code = key.split("_", 1)[1]
                language = Language.find(language_code)
                if language is None:
                    raise ValueError(
                        f"Unknown INFO description language: {language_code}"
                    )
                build.descriptions[language.code] = BuildDescription(
                    language=language, description=value
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
        if firmware_max and firmware_max.build < build.firmware_min.build:
            raise ValueError(
                "Maximum firmware must be greater than or equal to minimum firmware"
            )
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
    """Apply sidecar metadata to a build and its version without the SPK archive."""
    info = sidecar["info"]
    derived = sidecar["derived"]
    calculated = sidecar["calculated"]

    version = build.version
    version.upstream_version = info.get("version", "").rsplit("-", 1)[0]
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
