# -*- coding: utf-8 -*-
"""Outbound port contracts (hexagonal adapters implement these).

Domain and application layers depend only on these Protocols, never on
concrete clients (boto3, Flask-Cache, CDN HTTP). Adapters inject
implementations at the edges (storage.py, tasks.py, admin.py).
"""
from typing import Protocol


class StoragePort(Protocol):
    """Object-storage file operations for package artifacts."""

    def upload(self, local_path: str, object_key: str) -> bool: ...
    def download(self, object_key: str, local_path: str) -> bool: ...
    def delete(self, object_key: str) -> bool: ...


class CdnPort(Protocol):
    """CDN cache invalidation."""

    def purge(self, url_path: str) -> None: ...


class CachePort(Protocol):
    """Catalog/version cache invalidation."""

    def invalidate_catalog(self) -> None: ...
    def invalidate_packages(self) -> None: ...
