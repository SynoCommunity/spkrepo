# -*- coding: utf-8 -*-
"""Pure version-consistency domain: extract SPK metadata, compare versions.

Operates on duck-typed objects (``spk.info/wizards/license``,
``version.<fields>/service_dependencies/displaynames``), never on the
database. Adapters pass ORM objects or fakes.
"""

from .shared_kernel import derive_startable, map_displaynames, parse_version


def extract_version_metadata(spk):
    """Extract all version-level fields from an SPK into a plain dict without
    touching the database. Used to compare builds of the same version for
    consistency before writing anything.

    :param spk: a parsed SPK (or fake with ``info``/``wizards``/``license``)
    :returns: dict of version-level field values
    """
    info = spk.info
    try:
        upstream_version, _ = parse_version(info.get("version", ""))
    except ValueError:
        upstream_version = None
    startable = derive_startable(info)
    # Normalise displaynames to language-code keys (matching DB storage).
    # See shared_kernel.map_displaynames for ordering rules.
    displaynames = map_displaynames(info)

    return {
        "upstream_version": (upstream_version),
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
    what is already stored on an existing version record.

    Call this before writing anything when uploading a new build to an existing
    version, to ensure all builds within a version carry consistent metadata.

    :param version: the existing version record (ORM or fake)
    :param spk: a parsed SPK for the incoming build
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
        # startable=None means "default true", same as an SPK omitting the key
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
