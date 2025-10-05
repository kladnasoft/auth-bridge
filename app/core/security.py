# app/core/security.py
from __future__ import annotations

import secrets
from typing import Optional, Union

from starlette.requests import Request

from app.core.redis import RedisManager
from app.models import EntityType
from app.settings import get_settings


# ------------------- API Key helpers -------------------
from fastapi import Header, HTTPException, status
from app.core.redis import caches

async def validate_service_api_key(
    x_api_key: str = Header(..., description="Service API key"),
    x_service_id: str | None = Header(None, description="Optional service ID for extra validation")
) -> str:
    """
    Validates a service API key.
    Optionally crosschecks it against the provided service_id for added security.
    """
    if not x_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing x-api-key header")

    # Ensure services are loaded
    if not caches.services:
        raise HTTPException(status_code=503, detail="Service cache not ready")

    # Find matching service by API key
    matched_service = next((s for s in caches.services.values() if s.api_key == x_api_key), None)
    if not matched_service:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    # Optional cross-check by service ID
    if x_service_id and matched_service.id != x_service_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="API key does not match service ID")

    return matched_service.id


async def get_header_api_key(x_api_key: Optional[str] = Header(None)) -> str:
    """
    Extracts `x-api-key` header. Raises 401 if missing.
    """
    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail={"error_code": "NO_API_KEY", "message": "x-api-key header missing"},
        )
    return x_api_key


async def validate_authbridge_api_key(x_api_key: str = Header(...)) -> str:
    """
    Validates that the provided header is one of the *admin* keys.
    """
    s = get_settings()
    if x_api_key not in s.AUTHBRIDGE_API_KEYS:
        raise HTTPException(
            status_code=401,
            detail={
                "error_code": "AUTHBRIDGE_API_KEYS",
                "message": "Invalid admin API key",
            },
        )
    return x_api_key


async def validate_item_api_key(
    api_key: Union[str, Request],
    item,
    entity_type: EntityType,
) -> None:
    """
    Validates that `api_key` is permitted to act on `item` of the given entity type.

    Fix:
      - If api_key is a `Request` object, extract the header value.
      - For EntityType.SERVICE, must strictly match the service's own api_key (no admin bypass).
      - For others, admin keys are accepted or must match the item's api_key.
    """
    # normalize api_key -> string
    if isinstance(api_key, Request):
        api_key = api_key.headers.get("x-api-key")

    if not api_key:
        raise HTTPException(
            status_code=401,
            detail={
                "error_code": "NO_API_KEY",
                "message": "x-api-key missing in request",
            },
        )

    if item is None:
        raise HTTPException(
            status_code=401,
            detail={
                "error_code": "INVALID_ENTITY",
                "message": f"Unknown {entity_type.value}",
            },
        )

    s = get_settings()
    item_key = getattr(item, "api_key", None)

    if entity_type == EntityType.SERVICE:
        # STRICT: must match the service's own key
        if api_key != item_key:
            raise HTTPException(
                status_code=401,
                detail={
                    "error_code": "INVALID_ENTITY_KEY",
                    "message": f"Invalid API key for {entity_type.value}",
                },
            )
        return

    # Non-service entities: admin keys allowed OR must match item's key.
    if api_key in s.AUTHBRIDGE_API_KEYS:
        return
    if api_key != item_key:
        raise HTTPException(
            status_code=401,
            detail={
                "error_code": "INVALID_ENTITY_KEY",
                "message": f"Invalid API key for {entity_type.value}",
            },
        )


def new_system_token() -> str:
    return secrets.token_hex(16)


# ------------------- Rate limiting -------------------


async def check_rate_limit(bucket: str, key: str, limit: int, window_sec: int) -> None:
    rm = RedisManager()
    if not await rm.is_available():
        return

    from time import time

    window = int(time() // window_sec)
    rkey = f"rl:{bucket}:{key}:{window}"
    count = await rm.redis.incr(rkey)
    if count == 1:
        await rm.redis.expire(rkey, window_sec)
    if count > limit:
        ttl = await rm.redis.ttl(rkey)
        raise HTTPException(
            status_code=429,
            detail={
                "error_code": "RATE_LIMITED",
                "message": f"Too many requests (limit {limit}/{window_sec}s)",
                "retry_after_sec": max(ttl, 1),
            },
        )
