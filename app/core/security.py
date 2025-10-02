from __future__ import annotations

import json
import os
import secrets
from typing import Optional

from fastapi import Header, HTTPException

from app.core.redis import RedisManager
from app.models import EntityType
from app.settings import get_settings

# ------------------- API Key helpers -------------------

async def get_header_api_key(x_api_key: Optional[str] = Header(None)) -> str:
    if not x_api_key:
        raise HTTPException(status_code=401, detail={"error_code": "NO_API_KEY", "message": "x-api-key header missing"})
    return x_api_key


async def validate_authbridge_api_key(x_api_key: str = Header(...)) -> str:
    s = get_settings()
    if x_api_key not in s.AUTHBRIDGE_API_KEYS:
        raise HTTPException(status_code=401, detail={"error_code": "INVALID_ADMIN_KEY", "message": "Invalid admin API key"})
    return x_api_key


async def validate_item_api_key(api_key: str, item, entity_type: EntityType) -> None:
    s = get_settings()
    # admin keys always allowed
    if api_key in s.AUTHBRIDGE_API_KEYS:
        return
    if getattr(item, "api_key", None) != api_key:
        raise HTTPException(status_code=401, detail={
            "error_code": "INVALID_ENTITY_KEY",
            "message": f"Invalid API key for {entity_type.value}"
        })


def new_system_token() -> str:
    # cryptographically random (16 bytes hex)
    return secrets.token_hex(16)

# ------------------- Rate limiting -------------------

async def check_rate_limit(bucket: str, key: str, limit: int, window_sec: int) -> None:
    """
    Sliding-windowish simple limiter:
      - INCR a counter at key "rl:{bucket}:{key}:{current_window}"
      - Set EXPIRE window_sec for the key on first increment.
      - If counter > limit: raise 429
    """
    rm = RedisManager()
    if not await rm.is_available():
        # Fail-open if Redis down: do not block requests, but this is logged server-side
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
