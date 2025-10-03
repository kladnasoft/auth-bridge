# app/core/__init__.py
"""
Core utilities for Auth Bridge.

This subpackage groups logging, Redis access, security helpers,
and dynamic service-type loading.
"""

from __future__ import annotations

from .logging import get_logger, setup_logging
from .redis import RedisManager, caches
from .security import (
    check_rate_limit,
    get_header_api_key,
    new_system_token,
    validate_authbridge_api_key,
    validate_item_api_key,
)
from .types_loader import build_service_type_enum, load_service_types

__all__ = [
    # logging
    "get_logger",
    "setup_logging",
    # redis
    "RedisManager",
    "caches",
    # security
    "get_header_api_key",
    "validate_authbridge_api_key",
    "validate_item_api_key",
    "new_system_token",
    "check_rate_limit",
    # service types
    "load_service_types",
    "build_service_type_enum",
]
