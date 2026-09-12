# -*- coding: utf-8 -*-
from flask import request


def get_client_ip():
    """Return the real client IP behind the reverse-proxy chain.

    Production is Cloudflare -> nginx -> gunicorn, so ``request.remote_addr``
    is always 127.0.0.1 there. Trust order:
    1. ``CF-Connecting-IP`` — set (and overwritten) by Cloudflare itself,
       so authoritative when proxied and absent when DNS-only.
    2. Last ``X-Forwarded-For`` entry — nginx's ``proxy_add_x_forwarded_for``
       *appends* the direct peer, so the last entry is the IP nginx actually
       saw. Earlier entries are client-spoofable and must not be trusted.
    3. ``request.remote_addr`` — direct dev/test traffic.
    """
    cf_ip = (request.headers.get("CF-Connecting-IP") or "").strip()
    if cf_ip:
        return cf_ip
    forwarded_for = (request.headers.get("X-Forwarded-For") or "").strip()
    if forwarded_for:
        return forwarded_for.rsplit(",", 1)[-1].strip()
    return request.remote_addr or ""
