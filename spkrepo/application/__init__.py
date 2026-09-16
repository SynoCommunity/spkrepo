# -*- coding: utf-8 -*-
"""Application layer: use-case orchestration over domain + ports.

Transports (views/tasks/cli) resolve infrastructure state, then call these
planners/executors. No Flask/DB/boto3 imports here — only domain and ports.
"""

from . import activation  # noqa: F401

__all__ = ["activation"]
