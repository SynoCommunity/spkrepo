# -*- coding: utf-8 -*-
"""Pure client-IP resolution. Adapter (net.py) supplies headers/remote_addr."""


def resolve_client_ip(headers: dict, remote_addr: str | None) -> str:
    """Trust order: Fastly-Client-IP, 2nd-to-last XFF entry, remote_addr.

    Header lookup is case-insensitive (Werkzeug normalises
    'Fastly-Client-IP' to 'Fastly-Client-Ip', so exact-case matching fails).
    ``CF-Connecting-IP`` is deliberately untrusted (see net.py adapter).
    """
    lowered = {str(k).lower(): (v or "") for k, v in dict(headers).items()}
    fastly_ip = (lowered.get("fastly-client-ip") or "").strip()
    if fastly_ip:
        return fastly_ip
    forwarded = (lowered.get("x-forwarded-for") or "").strip()
    if forwarded:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if len(parts) >= 2:
            # Fastly appends the real client, then nginx appends its peer
            # (the Fastly edge); entries left of those two are spoofable.
            return parts[-2]
        if parts:
            return parts[-1]
    return remote_addr or ""
