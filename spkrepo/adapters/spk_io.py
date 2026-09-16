# -*- coding: utf-8 -*-
"""SPK archive adapter: parse, sign, and inspect ``.spk`` tar streams.

Archive I/O lives here; INFO/conf/checksum parsing delegates to
:mod:`spkrepo.domain.spk`.
"""
import hashlib
import io
import json
import re
import tarfile
import time

import gnupg
import requests

from ..domain.spk import BOOLEAN_INFO as _DOMAIN_BOOLEAN_INFO
from ..domain.spk import REQUIRED_INFO as _DOMAIN_REQUIRED_INFO
from ..domain.spk import icon_info_re as _domain_icon_info_re
from ..domain.spk import info_line_re as _domain_info_line_re
from ..domain.spk import package_re as _domain_package_re
from ..domain.spk import wizard_filename_re as _domain_wizard_filename_re
from ..exceptions import SPKParseError, SPKSignError


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
                from ..domain.spk import parse_info_lines, validate_required

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
                    from ..domain.spk import parse_conf_file, parse_json_conf

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
                    from ..domain.spk import verify_checksum

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
