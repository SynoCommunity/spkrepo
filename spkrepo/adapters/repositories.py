# -*- coding: utf-8 -*-
"""Repository lookups: resolve SPK INFO strings to database rows.

Pure parsing delegates to :mod:`spkrepo.domain`; queries and session
merges stay here.
"""
from ..domain.shared_kernel import parse_firmware
from ..models import Architecture, Firmware, Language, Service


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
    from ..domain.shared_kernel import map_displaynames as _map

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
    from ..domain.shared_kernel import map_descriptions as _map

    resolved: dict[str, Language] = {}
    for code in _map(info):
        language = Language.find(code)
        if language is None:
            raise ValueError(f"Unknown INFO description language: {code}")
        resolved[code] = language
    return resolved
