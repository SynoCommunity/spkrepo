# -*- coding: utf-8 -*-
"""Pure SPK INFO/conf parsing. Operates on bytes/dicts, never on tarfiles.

The tar adapter (utils.SPK) extracts raw bytes and delegates here, so all
branch logic is unit-testable without fixture archives.
"""
import base64
import binascii
import hashlib
import json
import re
from configparser import ConfigParser

from ..exceptions import SPKParseError

info_line_re = re.compile(r'^(?P<key>\w+)="(?P<value>.*)"$', re.MULTILINE)
package_re = re.compile(r"^[\w-]+$")
icon_info_re = re.compile(r"^package_icon(?:_(?P<size>120|256))?$")

REQUIRED_INFO = {"package", "version", "arch", "displayname", "description"}
BOOLEAN_INFO = {"ctl_stop", "startable", "support_conf_folder"}


def parse_info_lines(lines: list[bytes]) -> tuple[dict, dict]:
    """Parse raw INFO lines -> (info dict, icons {size: b64-bytes}).

    Raises SPKParseError on bad encoding, invalid lines, bad booleans,
    bad package names, or bad embedded icons.
    """
    info: dict = {}
    icons: dict[str, bytes] = {}
    for raw in lines:
        try:
            line = raw.decode("utf-8").strip()
        except UnicodeDecodeError:
            raise SPKParseError("Wrong INFO encoding")
        if not line:
            continue
        match = info_line_re.match(line)
        if not match:
            raise SPKParseError("Invalid INFO")
        key, value = match.group("key"), match.group("value")
        icon_match = icon_info_re.match(key)
        if icon_match:
            size = icon_match.group("size") or "72"
            try:
                icons[size] = base64.b64decode(value.encode("utf-8"))
            except (binascii.Error, TypeError):
                raise SPKParseError(f"Invalid INFO icon: {key}")
        elif key in BOOLEAN_INFO:
            if value == "yes":
                info[key] = True
            elif value == "no":
                info[key] = False
            else:
                raise SPKParseError(f"Invalid INFO boolean: {key}")
        elif key == "package":
            if not package_re.match(value):
                raise SPKParseError("Invalid INFO package")
            info[key] = value
        else:
            info[key] = value
    return info, icons


def validate_required(info: dict) -> None:
    """Raise SPKParseError if any REQUIRED_INFO key is missing."""
    if not set(info.keys()) >= REQUIRED_INFO:
        missing = ", ".join(REQUIRED_INFO - set(info.keys()))
        raise SPKParseError(f"Missing INFO: {missing}")


def parse_conf_file(raw: bytes, filename: str) -> dict:
    """Parse a conf/PKG_DEPS or PKG_CONX file -> section dict."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise SPKParseError(f"Wrong {filename} encoding")
    parser = ConfigParser()
    try:
        parser.read_string(text)
    except Exception:
        raise SPKParseError(f"Invalid {filename}")
    return {s: {k: v for k, v in parser.items(s)} for s in parser.sections()}


def parse_json_conf(raw: bytes, filename: str) -> str:
    """Validate a conf/privilege or conf/resource file, returning text."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise SPKParseError(f"Wrong {filename} encoding")
    try:
        json.loads(text)
    except (json.JSONDecodeError, ValueError):
        raise SPKParseError(f"File {filename} is not valid JSON")
    return text


def verify_checksum(expected: str, package_tgz_bytes: bytes) -> None:
    """Raise SPKParseError on checksum mismatch (pure bytes check)."""
    if hashlib.md5(package_tgz_bytes).hexdigest() != expected:
        raise SPKParseError("Checksum mismatch")


wizard_filename_re = re.compile(
    r"^WIZARD_UIFILES/(?P<process>install|upgrade|uninstall)"
    r"_uifile(?:_[a-z]{3})?(?:\.sh)?$"
)


def parse_loose_info_text(raw: str) -> dict:
    """Lenient `key=value` parse for the storage-task tar scan.

    Unlike :func:`parse_info_lines` (strict, validated, quote-aware), the
    upload task scans raw INFO bytes without failing the task on malformed
    lines: lines without ``=`` are skipped, keys/values are stripped and
    surrounding quotes removed. Single owner for this leniency.
    """
    info: dict = {}
    for line in (raw or "").split("\n"):
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        info[key] = value.strip().strip('"')
    return info


def has_wizard(names, process: str) -> bool:
    """True if any tar member name is a wizard file for ``process``.

    Uses the canonical wizard regex (incl. `_enu` / `.sh` variants),
    fixing the exact-match scan that missed suffixed wizards.
    """
    return any(
        (m := wizard_filename_re.match(name)) and m.group("process") == process
        for name in names
    )


def derive_startable_raw(info: dict) -> bool:
    """Startable from raw INFO strings: False only if startable/ctl_stop is 'no'."""
    return info.get("startable", "yes") != "no" and info.get("ctl_stop", "yes") != "no"
