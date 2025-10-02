from __future__ import annotations

import json
import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from app.core.redis import RedisManager, caches
from app.core.security import validate_authbridge_api_key, check_rate_limit
from app.settings import get_settings
from app.routers.token import RSA_KEYS, CURRENT_KID, rotate_rsa_key

router = APIRouter(prefix="/api/v1", tags=["system"])


@router.post("/system/rotate", operation_id="rotate_authbridge_key")
async def rotate_authbridge_key(x_api_key: str = Depends(validate_authbridge_api_key)):
    # rate limit admin action
    s = get_settings()
    await check_rate_limit("admin", x_api_key, 30, 60)

    api_keys = os.getenv("AUTHBRIDGE_API_KEYS")
    if api_keys is None:
        raise HTTPException(status_code=404, detail={"error_code": "MISSING_ENV", "message": "AUTHBRIDGE_API_KEYS not found"})

    try:
        json_keys = json.loads(api_keys)
        if not isinstance(json_keys, list) or not all(isinstance(k, str) for k in json_keys):
            raise ValueError
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"error_code": "BAD_KEYS_JSON", "message": "Invalid AUTHBRIDGE_API_KEYS JSON"}) from exc

    if len(json_keys) >= 1:
        s.AUTHBRIDGE_API_KEYS = json_keys
        return {"detail": f"Reloaded AUTHBRIDGE_API_KEYS (count={len(json_keys)})"}
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


@router.get("/system/jwks", operation_id="get_jwks_system")
async def get_jwks():
    """JWKS endpoint for all active RSA public keys."""
    keys = []
    for kid, (pub, _) in RSA_KEYS.items():
        keys.append({"kid": kid, "kty": "RSA", "use": "sig", "alg": "RS256", "pem": pub})
    return {"keys": keys}


@router.post("/system/rotate-keys", operation_id="rotate_rsa_keys")
async def rotate_keys(x_api_key: str = Depends(validate_authbridge_api_key)):
    """Manually rotate RSA keys. New tokens will be issued with new KID."""
    s = get_settings()
    await check_rate_limit("admin", x_api_key, 30, 60)
    kid = await rotate_rsa_key()
    return {"detail": "Rotated RSA keys", "new_kid": kid, "current": CURRENT_KID}


@router.get("/system/diagnostics", operation_id="diagnostics")
async def diagnostics():
    """
    Extended readiness/diagnostics:
    - Redis ping
    - JWKS key count
    - Current kid
    - Cache sizes
    """
    s = get_settings()
    rm = RedisManager()
    try:
        redis_ok = await rm.is_available()
    except Exception:
        redis_ok = False

    return {
        "redis": "ok" if redis_ok else "down",
        "jwks_keys": len(RSA_KEYS),
        "current_kid": CURRENT_KID,
        "cache": {
            "services": len(caches.services),
            "workspaces": len(caches.workspaces),
            "service_sys_ver": caches.service_sys_ver,
            "workspace_sys_ver": caches.workspace_sys_ver,
        },
        "pubsub_channel": s.PUBSUB_CHANNEL,
        "audit_stream": s.AUDIT_STREAM_NAME,
    }
