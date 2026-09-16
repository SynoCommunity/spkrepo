# -*- coding: utf-8 -*-
"""spkrepo package.

``create_app`` is exposed lazily so the pure ``spkrepo.domain`` and
``spkrepo.application`` subpackages can be imported without pulling in
Flask/SQLAlchemy/boto3/Celery — see PEP 562. (``spkrepo.adapters`` is *not*
pure: it owns the DB/FS/S3/tar I/O and imports those libraries.)
"""

__all__ = ["create_app"]


def __getattr__(name):
    if name == "create_app":
        from .app import create_app

        return create_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
