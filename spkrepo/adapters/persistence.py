# -*- coding: utf-8 -*-
"""Persistence writers: apply SPK/sidecar metadata to ORM rows and files.

Shared version-field logic lives in
:func:`spkrepo.adapters.persistence.assign_version_common_fields`, used by
both the upload and resync paths.
"""
import os

from flask import current_app

from ..models import BuildDescription, BuildManifest, DisplayName, Icon, Language
from .repositories import resolve_architectures, resolve_firmware, resolve_services


def assign_version_common_fields(version, spk) -> None:
    """Single-owner writer for version-level fields shared by upload/resync.

    Assigns upstream_version, report/distributor/maintainer URLs, wizards,
    startable (via domain), license and service dependencies. Localized
    displaynames are handled by :func:`resolve_displayname_languages` +
    caller-owned relationship assignment (create vs clear semantics differ).
    """
    from ..domain.shared_kernel import derive_startable as _startable
    from ..domain.shared_kernel import parse_version as _parse_version

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
    from ..domain.versions import extract_version_metadata as _pure

    return _pure(spk)


def assert_version_metadata_matches_db(version, spk):
    """Raise :exc:`ValueError` on version-level metadata conflicts.

    Adapter over :mod:`spkrepo.domain.versions` (single owner); kept here
    for backward compatibility.
    """
    from ..domain.versions import assert_version_metadata_matches_db as _pure

    return _pure(version, spk)


def apply_info_from_spk(session, build, spk, md5_hash):
    """Apply all metadata from a parsed SPK onto the given build and its parent
    version. Resync-only entry point (``views/tasks.py``'s
    ``resync_build_metadata``, triggered from ``views/admin.py``); the upload
    path (``views/api.py``'s ``Packages.post``) creates new records instead.
    Shared version-level fields converge on
    :func:`spkrepo.adapters.persistence.assign_version_common_fields` in
    both paths, while
    displaynames/descriptions/icons diverge by design (resync clears and
    rewrites; upload creates once).

    Version-level fields (shared across all builds of a version) are written
    unconditionally — callers must ensure consistency has already been checked
    via :func:`spkrepo.domain.versions.assert_version_metadata_matches_db`
    before calling this.

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
        from ..domain.shared_kernel import map_descriptions as _descriptions
        from ..domain.shared_kernel import map_displaynames as _displaynames
        from ..domain.shared_kernel import parse_version as _parse_version

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
                raise ValueError(f"Unknown INFO displayname language: {language_code}")
            version.displaynames[language.code] = DisplayName(
                language=language, displayname=displayname
            )

        build.descriptions.clear()
        for language_code, description in _descriptions(info).items():
            language = Language.find(language_code)
            if language is None:
                raise ValueError(f"Unknown INFO description language: {language_code}")
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
        from ..domain.upload import validate_firmware_range as _validate_fw

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
    from ..domain.shared_kernel import parse_upstream_lenient

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
