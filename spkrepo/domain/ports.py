# -*- coding: utf-8 -*-
"""Outbound port contracts (hexagonal adapters implement these).

Domain and application layers depend only on these Protocols, never on
concrete clients (boto3, Flask-Cache, CDN HTTP). Adapters inject
implementations at the edges (storage.py, tasks.py, admin.py).
"""

from typing import Protocol


class StoragePort(Protocol):
    """Object-storage file operations for package artifacts."""

    def upload(self, local_path: str, object_key: str) -> bool:
        """Upload a local file; True on success, False if skipped/failed."""
        ...

    def download(self, object_key: str, local_path: str) -> bool:
        """Download to a local path; True on success, False otherwise."""
        ...

    def delete(self, object_key: str) -> bool:
        """Delete a remote object; True on success, False otherwise."""
        ...


class CdnPort(Protocol):
    """CDN cache invalidation."""

    def purge(self, url_path: str) -> None:
        """Issue a purge for a path; no-op when unconfigured."""
        ...


class CachePort(Protocol):
    """Catalog/version cache invalidation."""

    def invalidate_catalog(self) -> None:
        """Drop all memoized NAS catalog entries."""
        ...

    def invalidate_packages(self) -> None:
        """Drop the cached package/version listing."""
        ...
