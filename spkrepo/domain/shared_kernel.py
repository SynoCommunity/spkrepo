# -*- coding: utf-8 -*-
"""Shared kernel: arch translation, firmware/version parsing, filename.

Pure value-object logic shared by upload, catalog, resync and downloads.
No Flask/DB/FS imports.
"""

import re

#: Synology-reported -> canonical arch code.
ARCH_FROM_SYNO = {"88f6281": "88f628x", "88f6282": "88f628x"}
#: Canonical -> Synology-reported arch code.
ARCH_TO_SYNO = {"88f628x": "88f6281"}

#: e.g. "6.2-23739"
firmware_re = re.compile(r"^(?P<version>\d+\.\d)-(?P<build>\d{3,6})$")
#: e.g. "1.2.3-10"
version_re = re.compile(r"^(?P<upstream_version>.*)-(?P<version>\d+)$")
#: e.g. ".f42661[apollolake-avoton]" inside an SPK filename
filename_target_re = re.compile(r"\.f(\d+)\[([^\]]+)\]")


def translate_arch_from_syno(code: str) -> str:
    """Translate a Synology-reported arch code to its canonical form."""
    return ARCH_FROM_SYNO.get(code, code)


def parse_firmware(value: str) -> tuple[str, int]:
    """Parse '6.2-23739' -> ('6.2', 23739). Raises ValueError if malformed."""
    if not value:
        raise ValueError("Missing firmware value")
    match = firmware_re.match(value)
    if not match:
        raise ValueError(f"Invalid firmware value: {value}")
    return match.group("version"), int(match.group("build"))


def parse_version(value: str) -> tuple[str, int]:
    """Parse '1.2.3-10' -> ('1.2.3', 10). Raises ValueError if malformed."""
    match = version_re.match(value or "")
    if not match:
        raise ValueError(f"Invalid version value: {value}")
    return match.group("upstream_version"), int(match.group("version"))


def parse_upstream_lenient(value: str) -> str:
    """Best-effort upstream extraction for the sidecar path.

    Sidecars are written by our own upload task (not validated SPKs), so a
    malformed version string falls back to an `rsplit` prefix instead of
    raising. Single owner for this leniency (SPK/upload paths raise).
    """
    try:
        upstream, _ = parse_version(value or "")
    except ValueError:
        upstream = (value or "").rsplit("-", 1)[0]
    return upstream


def build_filename(
    package_name: str, version: int, firmware_build: int, arch_codes: list[str]
) -> str:
    """Build a Build's .spk filename from its parts (pre-insert usable)."""
    arch_part = "-".join(arch_codes)
    return f"{package_name}.v{version}.f{firmware_build}[{arch_part}].spk"


def derive_startable(info: dict) -> bool:
    """Default True per Synology docs; False if startable/ctl_stop is False."""
    if info.get("startable") is False or info.get("ctl_stop") is False:
        return False
    return True


def map_displaynames(info: dict) -> dict[str, str]:
    """Normalise INFO displayname keys to language-code keys.

    Bare 'displayname' -> 'enu', suffixed 'displayname_fre' -> 'fre'.
    Bare key wins last so an override is not shadowed by a stale suffix.
    """
    displaynames: dict[str, str] = {}
    for key, value in info.items():
        if key.startswith("displayname_"):
            displaynames[key.split("_", 1)[1]] = value
    if info.get("displayname"):
        # Bare key wins last: DSM sends both displayname and displayname_enu
        # and the bare key is the canonical enu value.
        displaynames["enu"] = info["displayname"]
    return displaynames


def map_descriptions(info: dict, prefix: str = "description_") -> dict[str, str]:
    """Collect 'description_xxx' (+ bare 'description' as 'enu') entries."""
    descriptions: dict[str, str] = {}
    if info.get("description"):
        descriptions["enu"] = info["description"]
    for key, value in info.items():
        if key.startswith(prefix):
            descriptions[key.split("_", 1)[1]] = value
    return descriptions


def validate_firmware_range(min_build: int, max_build: int | None) -> None:
    """Raise ValueError if max < min."""
    if max_build is not None and max_build < min_build:
        raise ValueError(
            "Maximum firmware must be greater than or equal to minimum firmware"
        )


def parse_filename_target(filename: str) -> tuple[int | None, bool]:
    """Parse '.f<build>[archs]' -> (target_fw_build|None, target_noarch)."""
    match = filename_target_re.search(filename or "")
    if not match:
        return None, False
    archs = match.group(2).split("-")
    if "noarch" in archs:
        return None, True
    return int(match.group(1)), False
