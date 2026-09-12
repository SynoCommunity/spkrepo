# -*- coding: utf-8 -*-
from flask import request


def get_client_ip():
    """Return the real client IP behind the reverse-proxy chain.

    Production is Fastly -> nginx -> gunicorn, so ``request.remote_addr``
    is always 127.0.0.1 there. Trust order:
    1. ``Fastly-Client-IP`` — set by Fastly to its connecting client and
       preserved across shielding hops. Spoofable if a client pre-sets the
       header, so harden it in VCL (see deployment docs); still the best
       signal available at the app layer.
    2. Second-to-last ``X-Forwarded-For`` entry — Fastly appends the real
       client, then our nginx appends its peer (the Fastly edge). Anything
       left of those two is client-spoofable and must not be trusted. With
       a single entry (direct-to-nginx traffic), that entry is nginx's peer.
    3. ``request.remote_addr`` — direct dev/test traffic.

    Note: ``CF-Connecting-IP`` is deliberately NOT trusted — Cloudflare is
    DNS-only here, so that header can never arrive legitimately; honoring it
    would let anyone bypass rate limiting by sending it themselves.
    """
    fastly_ip = (request.headers.get("Fastly-Client-IP") or "").strip()
    if fastly_ip:
        return fastly_ip
    forwarded_for = (request.headers.get("X-Forwarded-For") or "").strip()
    if forwarded_for:
        parts = [part.strip() for part in forwarded_for.split(",") if part.strip()]
        if len(parts) >= 2:
            return parts[-2]
        if parts:
            return parts[-1]
    return request.remote_addr or ""
