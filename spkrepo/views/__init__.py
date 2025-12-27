# -*- coding: utf-8 -*-
from .admin import (
    ArchitectureView,
    BuildView,
    FirmwareView,
    IndexView,
    PackageView,
    ScreenshotView,
    ServiceView,
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
    "VersionView",
    "api",
    "SpkrepoRegisterForm",
    "frontend",
    "nas",
]
