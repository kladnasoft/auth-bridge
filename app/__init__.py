# app/__init__.py
"""
Auth Bridge package initializer.

Exposes package metadata and keeps initialization side-effect free.
"""

from __future__ import annotations

import os

__all__ = ["__version__"]

# Prefer runtime-provided build/version; fall back to project default.
__version__: str = os.getenv("AUTHBRIDGE_BUILD_VERSION", "1.0.0")