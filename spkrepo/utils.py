# -*- coding: utf-8 -*-
import base64
import binascii
import hashlib
import io
import json
import re
import tarfile
import time
from configparser import ConfigParser

import gnupg
import requests

from .exceptions import SPKParseError, SPKSignError
from .ext import db
from .models import Architecture, Firmware, Language, Role, Service


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
                    # decode utf-8
                    try:
                        self.license = (
                            spk.extractfile("LICENSE").read().decode("utf-8").strip()
                        )
                    except UnicodeDecodeError:
                        raise SPKParseError("Wrong LICENSE encoding")

                # read syno_signature.asc file
                if "syno_signature.asc" in names:
                    # decode ascii
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
                    # decode utf-8
                    try:
                        line = line.decode("utf-8").strip()
                    except UnicodeDecodeError:
                        raise SPKParseError("Wrong INFO encoding")

                    # skip blank line
                    if not line:
                        continue

                    # validate line
                    match = self.info_line_re.match(line)
                    if not match:
                        raise SPKParseError("Invalid INFO")
                    key, value = match.group("key"), match.group("value")

                    # read icons
                    match = self.icon_info_re.match(key)
                    if match:
                        size = match.group("size") or "72"
                        try:
                            self.icons[size] = io.BytesIO(
                                base64.b64decode(value.encode("utf-8"))
                            )
                        except binascii.Error:
                            raise SPKParseError("Invalid INFO icon: %s" % key)
                        except TypeError:
                            raise SPKParseError("Invalid INFO icon: %s" % key)
                    # read booleans
                    elif key in self.BOOLEAN_INFO:
                        if value == "yes":
                            self.info[key] = True
                        elif value == "no":
                            self.info[key] = False
                        else:
                            raise SPKParseError("Invalid INFO boolean: %s" % key)
                    elif key == "package":
                        match = self.package_re.match(value)
                        if not match:
                            raise SPKParseError("Invalid INFO package")
                        self.info[key] = value
                    else:
                        self.info[key] = value

                # validate info
                if not set(self.info.keys()) >= self.REQUIRED_INFO:
                    raise SPKParseError(
                        "Missing INFO: %s"
                        % ", ".join(self.REQUIRED_INFO - set(self.info.keys()))
                    )

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
                        except json.JSONDecodeError:
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
                        except json.JSONDecodeError:
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
        # check no signature exists
        if self.signature is not None:
            raise ValueError("Already signed")

        # collect the streams
        with io.BytesIO() as data_stream:
            self.stream.seek(0)
            with tarfile.open(fileobj=self.stream, mode="r:") as spk:
                names = sorted(spk.getnames())
                # INFO
                if "INFO" in names:
                    data_stream.write(spk.extractfile("INFO").read())

                # LICENSE
                if "LICENSE" in names:
                    data_stream.write(spk.extractfile("LICENSE").read())

                # icons
                for name in names:
                    match = self.icon_filename_re.match(name)
                    if match:
                        data_stream.write(spk.extractfile(name).read())

                # wizards
                for name in names:
                    match = self.wizard_filename_re.match(name)
                    if match:
                        data_stream.write(spk.extractfile(name).read())

                # conf
                for name in names:
                    match = self.conf_filename_re.match(name)
                    if match:
                        data_stream.write(spk.extractfile(name).read())

                # package.tgz
                if "package.tgz" in names:
                    data_stream.write(spk.extractfile("package.tgz").read())

                # scripts
                for name in names:
                    match = self.script_filename_re.match(name)
                    if match:
                        data_stream.write(spk.extractfile(name).read())

            # generate the signature
            data_stream.seek(0)
            signature = self._generate_signature(data_stream, timestamp_url, gnupghome)
            self.signature = signature

            # add the signature to the SPK
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
        # check signature exists
        if self.signature is None:
            raise ValueError("Not signed")

        # remove the signature file
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

    def _generate_signature(self, stream, timestamp_url, gnupghome):  # pragma: no cover
        # generate the signature
        gpg = gnupg.GPG(gnupghome=gnupghome)
        signature = gpg.sign_file(stream, detach=True)

        # have the signature remotely timestamped
        try:
            response = requests.post(
                timestamp_url, files={"file": signature.data}, timeout=2
            )
        except requests.Timeout:
            raise SPKSignError("Timestamp server did not respond in time")

        # check the response status
        if response.status_code != 200:
            raise SPKSignError(
                "Timestamp server returned with status code %d" % response.status_code
            )

        # verify the timestamp
        if not gpg.verify(response.content):
            raise SPKSignError("Cannot verify timestamp")

        response.encoding = "ascii"
        return response.text


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
            [{"version": "3.1", "build": 1594}, {"version": "5.0", "build": 4458}]
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
