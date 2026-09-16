# -*- coding: utf-8 -*-
"""spkrepo package.

``create_app`` is exposed lazily so pure subpackages (``spkrepo.domain``,
``spkrepo.application``, ``spkrepo.adapters``) can be imported without
pulling in Flask/SQLAlchemy/boto3/Celery — see PEP 562.
"""

__all__ = ["create_app"]


def __getattr__(name):
    if name == "create_app":
        from .app import create_app

        return create_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
