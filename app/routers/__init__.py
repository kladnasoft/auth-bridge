# app/routers/__init__.py
"""
FastAPI routers for Auth Bridge.

Routers are split by concern and versioned where appropriate.
Importing this module does not create an application instance.
"""

from __future__ import annotations

from .service import router_v1 as service_router_v1
from .system import router as system_router
from .token import router_v1 as token_router_v1, router_v1 as token_router_v2
from .workspace import router as workspace_router_v1

__all__ = [
    "service_router_v1",
    "system_router",
    "token_router_v1",
    "workspace_router_v1",
]
