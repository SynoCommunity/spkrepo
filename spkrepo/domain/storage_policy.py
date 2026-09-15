# -*- coding: utf-8 -*-
"""Pure storage/CDN policy. S3/NET clients stay in adapters."""


def should_attempt_upload(path: str | None, exists: bool, signed: bool) -> tuple[bool, str]:
    """Decide whether upload_to_storage should proceed.

    Returns (proceed, reason) where reason is 'ok' or a skip code.
    """
    if not path:
        return False, "no-path"
    if not exists:
        return False, "missing-file"
    if not signed:
        return False, "unsigned"
    return True, "ok"


def cdn_purge_url(host: str, path: str) -> str:
    """Build the CDN purge URL for a storage path (pure string concat)."""
    return f"https://{host}/{path.lstrip('/')}"
