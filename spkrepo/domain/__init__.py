# -*- coding: utf-8 -*-
"""Pure domain core: no Flask, no DB, no I/O.

Hexagonal rule: everything in this package must be importable without
an app context, database, filesystem, network, or config.
Adapters (views/tasks/cli/storage) inject data and call these functions.
"""

from . import access, catalog, downloads, ports, shared_kernel, spk, storage_policy, upload, versions  # noqa: F401

__all__ = [
    "access",
    "catalog",
    "downloads",
    "ports",
    "shared_kernel",
    "spk",
    "storage_policy",
    "upload",
    "versions",
]
