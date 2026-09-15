# -*- coding: utf-8 -*-
"""Proxy-aware client-IP resolution adapter (used for rate limiting)."""
from flask import request

from .domain.access import resolve_client_ip


def get_client_ip():
    """Return the real client IP behind the reverse-proxy chain.

    Production is Fastly -> nginx -> gunicorn, so ``request.remote_addr``
    is always 127.0.0.1 there. Trust order is defined in
    :func:`spkrepo.domain.access.resolve_client_ip` (pure, unit-tested);
    this is the Flask adapter supplying headers/remote_addr.

    Note: ``CF-Connecting-IP`` is deliberately NOT trusted — Cloudflare is
    DNS-only here, so that header can never arrive legitimately; honoring it
    would let anyone bypass rate limiting by sending it themselves.
    """
    return resolve_client_ip(dict(request.headers), request.remote_addr)
