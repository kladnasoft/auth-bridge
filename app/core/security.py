from __future__ import annotations

import secrets
from typing import Any

from fastapi import Depends, HTTPException, Request
from app.core.logging import get_logger
from app.models import EntityType
from app.settings import get_settings

log = get_logger("auth-bridge.security")


async def get_header_api_key(request: Request) -> str:
    api_key = request.headers.get("x-api-key")
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing API key")
    return api_key


async def validate_authbridge_api_key(api_key: str = Depends(get_header_api_key)) -> str:
    settings = get_settings()
    if api_key not in settings.AUTHBRIDGE_API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key


async def validate_item_api_key(api_key: str, item: Any, item_type: EntityType) -> None:
    if not item:
        raise HTTPException(status_code=404, detail=f"{item_type.value} not found")
    item_key = getattr(item, "api_key", None)
    settings = get_settings()
    if api_key not in settings.AUTHBRIDGE_API_KEYS and api_key != item_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


def new_system_token(size: int = 8) -> str:
    return secrets.token_hex(size)
