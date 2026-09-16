# -*- coding: utf-8 -*-
"""Transport views: web frontend, REST API, NAS catalog, admin, tasks."""

from .admin import (
    ArchitectureView,
    BuildView,
    FirmwareView,
    IndexView,
    PackageView,
    ScreenshotView,
    ServiceView,
    TaskStatusView,
    UserView,
    VersionView,
)
from .api import api
from .frontend import SpkrepoRegisterForm, frontend
from .nas import nas

__all__ = [
    "ArchitectureView",
    "BuildView",
    "FirmwareView",
    "IndexView",
    "PackageView",
    "ScreenshotView",
    "ServiceView",
    "UserView",
    "TaskStatusView",
    "VersionView",
    "api",
    "SpkrepoRegisterForm",
    "frontend",
    "nas",
]
