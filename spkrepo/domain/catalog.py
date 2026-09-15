# -*- coding: utf-8 -*-
"""Pure catalog domain: compat predicate, quick-install flags, entry shaping.

All URL generation stays in the Flask adapter; this module takes
pre-resolved link/thumbnail/snapshot strings.
"""


def firmware_in_range(build: int, min_build: int, max_build: int | None) -> bool:
    """True if device fw ``build`` is served by [min, max] (None = unbounded)."""
    if build < min_build:
        return False
    if max_build is not None and build > max_build:
        return False
    return True


def derive_quick_flags(
    license_text: str | None,
    install_wizard: bool | None,
    upgrade_wizard: bool | None,
    startable: bool | None,
) -> tuple[bool, bool, bool]:
    """Derive (qinst, qupgrade, qstart) exactly as DSM clients expect."""
    qinst = license_text is None and install_wizard is False
    qupgrade = license_text is None and upgrade_wizard is False
    qstart = (
        license_text is None
        and install_wizard is False
        and startable is not False
    )
    return qinst, qupgrade, qstart


def set_if_truthy(entry: dict, key: str, value) -> None:
    """Set entry[key] = value only if truthy (pure helper)."""
    if value:
        entry[key] = value


def _firmware_sort_key(version: str) -> tuple:
    """Sort key for '7.2' style versions: numeric parts numerically."""
    return tuple(int(p) if p.isdigit() else p for p in version.split("."))


def group_builds_per_dsm(builds) -> dict:
    """Group builds by DSM/SRM major version, newest-first.

    Duck-typed on ``build.firmware_min.version`` so ORM and fakes both work.
    Single owner (was ``models.group_builds_per_dsm``); models re-exports.
    """
    groups: dict = {}
    for build in builds:
        major = build.firmware_min.version.split(".")[0]
        groups.setdefault(major, []).append(build)
    for grouped in groups.values():
        grouped.sort(key=lambda b: _firmware_sort_key(b.firmware_min.version), reverse=True)
    return dict(
        sorted(
            groups.items(),
            key=lambda item: int(item[0]) if item[0].isdigit() else item[0],
            reverse=True,
        )
    )


def build_entry_data(
    *,
    package_name: str,
    version_string: str,
    displayname: str,
    description: str,
    link: str,
    thumbnails: list[str],
    snapshots: list[str],
    license_text: str | None,
    install_wizard: bool | None,
    upgrade_wizard: bool | None,
    startable: bool | None,
    dependencies: str | None,
    conflicts: str | None,
    download_count: int,
    recent_download_count: int,
    report_url: str | None = None,
    changelog: str | None = None,
    distributor: str | None = None,
    distributor_url: str | None = None,
    maintainer: str | None = None,
    maintainer_url: str | None = None,
    md5: str | None = None,
    size: int | None = None,
    retina_url: str | None = None,
) -> dict:
    """Build one catalog entry dict from plain values (no ORM/Flask)."""
    qinst, qupgrade, qstart = derive_quick_flags(
        license_text, install_wizard, upgrade_wizard, startable
    )
    entry: dict = {
        "package": package_name,
        "version": version_string,
        "dname": displayname,
        "desc": description,
        "link": link,
        "thumbnail": thumbnails,
        "qinst": qinst,
        "qupgrade": qupgrade,
        "qstart": qstart,
        "deppkgs": dependencies,
        "conflictpkgs": conflicts,
        "download_count": download_count,
        "recent_download_count": recent_download_count,
        "snapshot": snapshots,
    }
    if report_url:
        entry["report_url"] = report_url
        entry["beta"] = True
    set_if_truthy(entry, "changelog", changelog)
    set_if_truthy(entry, "distributor", distributor)
    set_if_truthy(entry, "distributor_url", distributor_url)
    set_if_truthy(entry, "maintainer", maintainer)
    set_if_truthy(entry, "maintainer_url", maintainer_url)
    set_if_truthy(entry, "md5", md5)
    set_if_truthy(entry, "size", size)
    if retina_url:
        entry["thumbnail_retina"] = [retina_url, retina_url]
    if startable is not None:
        entry["startable"] = "yes" if startable else "no"
    return entry
