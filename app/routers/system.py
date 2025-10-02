from __future__ import annotations

import json
import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import validate_authbridge_api_key
from app.core.redis import caches
from app.settings import get_settings

router = APIRouter(prefix="/api/v1", tags=["system"])


@router.post("/system/rotate", operation_id="rotate_authbridge_key")
async def rotate_authbridge_key(_: str = Depends(validate_authbridge_api_key)):
    api_keys = os.getenv("AUTHBRIDGE_API_KEYS")
    if api_keys is None:
        raise HTTPException(status_code=404, detail="AUTHBRIDGE_API_KEYS not found")

    try:
        json_keys = json.loads(api_keys)
        if not isinstance(json_keys, list) or not all(isinstance(k, str) for k in json_keys):
            raise ValueError
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid AUTHBRIDGE_API_KEYS JSON") from exc

    if len(json_keys) >= 2:
        s = get_settings()
        s.AUTHBRIDGE_API_KEYS = json_keys  # hot-reload
        return {"detail": "Reloaded: AUTHBRIDGE_API_KEYS"}
    return {"detail": "Error: AUTHBRIDGE_API_KEYS cannot be loaded"}


@router.get("/system/version", operation_id="get_system_version")
async def get_system_version():
    return {
        "detail": "System Version.",
        "system_version": caches.service_sys_ver or caches.workspace_sys_ver or "unknown",
    }


@router.get("/system/heartbeat", operation_id="heartbeat_check")
async def heartbeat_check():
    current_time = datetime.utcnow().isoformat() + "Z"
    return {"status": "alive", "timestamp": current_time}
