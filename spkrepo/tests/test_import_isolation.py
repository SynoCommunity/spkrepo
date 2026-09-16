# -*- coding: utf-8 -*-
"""Architectural guard: pure subpackages must import without the web stack.

Runs in a subprocess so the parent test session's already-imported Flask/
SQLAlchemy modules cannot mask a regression.
"""

import subprocess
import sys

import pytest

BOUNDARIES = (
    "flask",
    "sqlalchemy",
    "boto3",
    "celery",
    "gnupg",
    "requests",
    "spkrepo.app",
    "spkrepo.ext",
    "spkrepo.models",
)

PROBE = (
    "import sys\n"
    "import spkrepo.{mod}\n"
    "bad = [m for m in {boundaries!r} if m in sys.modules]\n"
    "print(','.join(bad))\n"
)


@pytest.mark.parametrize(
    "module",
    [
        "domain",
        "domain.catalog",
        "domain.downloads",
        "domain.shared_kernel",
        "domain.spk",
        "domain.upload",
        "domain.versions",
        "domain.access",
        "domain.storage_policy",
        "application.activation",
    ],
)
def test_pure_subpackage_import_is_isolated(module):
    """Importing a pure module must not preload Flask/DB/boto3/Celery."""
    result = subprocess.run(
        [sys.executable, "-c", PROBE.format(mod=module, boundaries=BOUNDARIES)],
        capture_output=True,
        text=True,
        check=True,
    )
    loaded = [m for m in result.stdout.strip().split(",") if m]
    assert loaded == [], f"importing spkrepo.{module} preloaded {loaded}"
