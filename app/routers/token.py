# app/routers/token.py

from __future__ import annotations

import datetime
import uuid
from typing import Dict, Optional, Tuple

import jwt
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import APIRouter, HTTPException, Path, Request
from pydantic import BaseModel, model_validator

from app.core.redis import RedisManager, caches
from app.core.security import (
    check_rate_limit,
    get_header_api_key,
    validate_item_api_key,
)
from app.models import EntityType, TokenPayload
from app.settings import get_settings
from app.routers.service import get_service
from app.routers.workspace import get_workspace

router_v1 = APIRouter(prefix="/api/v1", tags=["token"])

# Active keys in memory {kid: (public_pem, private_pem)}
RSA_KEYS: Dict[str, Tuple[str, str]] = {}
CURRENT_KID: Optional[str] = None


class ResponseToken(BaseModel):
    access_token: str


class Payload(BaseModel):
    payload: Dict

    @model_validator(mode="after")
    def validate_payload(self):
        payload = self.payload
        if not payload:
            raise HTTPException(
                status_code=400,
                detail={"error_code": "BAD_REQUEST", "message": "Payload is missing"},
            )

        iss = payload.get("iss")
        aud = payload.get("aud")
        sub = payload.get("sub")

        if iss is None:
            raise HTTPException(
                status_code=400,
                detail={"error_code": "BAD_REQUEST", "message": "iss is missing"},
            )
        if aud is None:
            raise HTTPException(
                status_code=400,
                detail={"error_code": "BAD_REQUEST", "message": "aud is missing"},
            )
        if sub is None:
            raise HTTPException(
                status_code=400,
                detail={"error_code": "BAD_REQUEST", "message": "sub is missing"},
            )

        if iss not in caches.services:
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "NOT_FOUND",
                    "message": f"{iss} not an existing service",
                },
            )
        if aud not in caches.services:
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "NOT_FOUND",
                    "message": f"{aud} not an existing service",
                },
            )
        if iss == aud:
            raise HTTPException(
                status_code=400, detail={"error_code": "BAD_REQUEST", "message": "iss == aud"}
            )
        if sub not in caches.workspaces:
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "NOT_FOUND",
                    "message": f"{sub} not an existing workspace",
                },
            )
        return self


def generate_rsa_keypair() -> Tuple[str, str]:
    private_key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )
    public_key = private_key.public_key()
    pem_private = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    pem_public = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return pem_public, pem_private


async def load_rsa_keys() -> None:
    """
    Load RSA keys (multi-key with KID) from Redis or generate a new one if none exist.
    Safe to call often; cheap when cached in Redis.
    """
    global RSA_KEYS, CURRENT_KID
    rm = RedisManager()
    if not await rm.is_available():
        # Fallback: single ephemeral key (per-process)
        if not RSA_KEYS or not CURRENT_KID:
            kid = str(uuid.uuid4())
            pub, prv = generate_rsa_keypair()
            RSA_KEYS = {kid: (pub, prv)}
            CURRENT_KID = kid
        return

    keys_blob = await rm.get_raw("rsa:keys")
    if keys_blob:
        try:
            parsed = eval(keys_blob.decode())  # stored as str(RSA_KEYS); content is ours.
            RSA_KEYS = {kid: (pair[0], pair[1]) for kid, pair in parsed.items()}
            CURRENT_KID = sorted(RSA_KEYS.keys())[-1] if RSA_KEYS else None
            if CURRENT_KID is None:
                kid = str(uuid.uuid4())
                pub, prv = generate_rsa_keypair()
                RSA_KEYS = {kid: (pub, prv)}
                CURRENT_KID = kid
                await rm.set_raw("rsa:keys", str(RSA_KEYS))
            return
        except Exception:
            # fall through to fresh generation
            pass

    # If no valid keys, generate a new one and persist
    kid = str(uuid.uuid4())
    pub, prv = generate_rsa_keypair()
    RSA_KEYS = {kid: (pub, prv)}
    CURRENT_KID = kid
    await rm.set_raw("rsa:keys", str(RSA_KEYS))


async def rotate_rsa_key() -> str:
    """
    Manually rotate RSA keys: generate new, set as CURRENT, persist.
    """
    global RSA_KEYS, CURRENT_KID
    rm = RedisManager()
    kid = str(uuid.uuid4())
    pub, prv = generate_rsa_keypair()
    RSA_KEYS[kid] = (pub, prv)
    CURRENT_KID = kid
    if await rm.is_available():
        await rm.set_raw("rsa:keys", str(RSA_KEYS))
    return kid


def _get_service_specific_ttl_minutes(service_id: str) -> int:
    """
    Allow per-service override of token TTL via service.info.get('token_ttl_min').
    Falls back to global ACCESS_TOKEN_EXPIRATION_MIN.
    """
    s = get_settings()
    svc = caches.services.get(service_id)
    if svc and isinstance(svc.info, dict):
        ttl = svc.info.get("token_ttl_min")
        if isinstance(ttl, int) and ttl > 0:
            return ttl
    return s.ACCESS_TOKEN_EXPIRATION_MIN


async def issue_jwt_token(
    payload: Dict, algorithm: str = "RS256", expiration_minutes: int = 60
) -> str:
    global CURRENT_KID
    # Ensure keys are present
    if not CURRENT_KID or CURRENT_KID not in RSA_KEYS:
        await load_rsa_keys()
    if not CURRENT_KID or CURRENT_KID not in RSA_KEYS:
        raise RuntimeError("No RSA key available")

    payload["exp"] = datetime.datetime.utcnow() + datetime.timedelta(
        minutes=expiration_minutes
    )
    headers = {"kid": CURRENT_KID}
    _, prv = RSA_KEYS[CURRENT_KID]
    return jwt.encode(payload, prv, algorithm=algorithm, headers=headers)


# ------------------- Endpoints -------------------


@router_v1.post("/token/{service_id}/issue", response_model=ResponseToken, operation_id="issue_token")
async def issue_token(
    request: Request,
    payload: TokenPayload,
    service_id: str = Path(..., embed=True),
):
    # Ensure keys are loaded before issuing
    await load_rsa_keys()

    # rate limit (per API key)
    api_key = await get_header_api_key(request)
    s = get_settings()
    await check_rate_limit("issue", api_key, s.RL_TOKEN_ISSUE_LIMIT_PER_MIN, 60)

    # Ensure fresh caches (services/workspaces)
    from app.routers.service import reload_services
    from app.routers.workspace import reload_workspaces

    await reload_services()
    await reload_workspaces()

    keys_to_exclude = {"iss", "aud", "sub", "exp"}
    content = {"iss": service_id, "aud": payload.aud, "sub": payload.sub}
    filtered_claims = {
        k: v for k, v in (payload.claims or {}).items() if k not in keys_to_exclude
    }

    validated_model = Payload(payload=content)
    if filtered_claims:
        validated_model.payload.update({"claims": filtered_claims})

    service = await get_service(service_id)
    await validate_item_api_key(api_key, service, EntityType.SERVICE)

    workspace = await get_workspace(payload.sub)
    valid_link = next(
        (
            l
            for l in workspace.services
            if l.issuer_id == service_id and l.audience_id == payload.aud
        ),
        None,
    )
    if not valid_link:
        raise HTTPException(
            status_code=400,
            detail={"error_code": "UNLINKED", "message": "Services not linked"},
        )

    if valid_link.context:
        validated_model.payload.update(valid_link.context)

    ttl = _get_service_specific_ttl_minutes(service_id)
    token = await issue_jwt_token(validated_model.payload, expiration_minutes=ttl)
    return ResponseToken(access_token=token)


@router_v1.get("/token/public_key", operation_id="get_public_key_token")
async def get_public_key():
    """Return current RSA public key and kid."""
    global CURRENT_KID
    if not CURRENT_KID or CURRENT_KID not in RSA_KEYS:
        await load_rsa_keys()
    if not CURRENT_KID or CURRENT_KID not in RSA_KEYS:
        raise HTTPException(
            status_code=503,
            detail={"error_code": "KEYS_UNAVAILABLE", "message": "RSA keys unavailable"},
        )
    return {"kid": CURRENT_KID, "public_key_pem": RSA_KEYS[CURRENT_KID][0]}


@router_v1.get("/token/jwks", operation_id="get_jwks_token")
async def get_jwks():
    """
    Return all active RSA public keys in JWKS-like format.
    Ensures keys are loaded so multi-worker deployments see a consistent view.
    """
    if not RSA_KEYS:
        await load_rsa_keys()
    keys = [
        {"kid": kid, "kty": "RSA", "use": "sig", "alg": "RS256", "pem": pub}
        for kid, (pub, _) in RSA_KEYS.items()
    ]
    return {"keys": keys}


@router_v1.post("/token/verify", operation_id="verify_token")
async def verify_token(request: Request):
    """
    Verify a JWT with KID header.

    Fixes:
    - Convert stored PEM string to a cryptography public key object before decode.
    - Disable audience verification here (model-level checks already validate `aud`),
      avoiding InvalidAudienceError unless you later pass `audience=...`.
    - Reload keys from Redis once if the incoming KID is unknown (multi-worker safety).
    """
    data = await request.json()
    token = data.get("token")
    if not token:
        raise HTTPException(
            status_code=400,
            detail={"error_code": "BAD_REQUEST", "message": "Missing token"},
        )

    # rate limit verify to prevent abuse (requires x-api-key)
    api_key = await get_header_api_key(request)
    s = get_settings()
    await check_rate_limit("verify", api_key, s.RL_DISCOVERY_LIMIT_PER_MIN, 60)

    # Ensure keys are available
    if not RSA_KEYS or not CURRENT_KID:
        await load_rsa_keys()

    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if not kid or kid not in RSA_KEYS:
            # Try to refresh from Redis once (handles other worker having rotated/issued)
            await load_rsa_keys()
            if not kid or kid not in RSA_KEYS:
                raise HTTPException(
                    status_code=401,
                    detail={"error_code": "UNKNOWN_KID", "message": "Unknown key ID"},
                )

        pub_pem, _ = RSA_KEYS[kid]
        # Convert PEM string → cryptography public key object
        public_key = serialization.load_pem_public_key(
            pub_pem.encode("utf-8"), backend=default_backend()
        )

        # Decode; disable audience verification here
        decoded = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail={"error_code": "TOKEN_EXPIRED", "message": "Token expired"},
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=401, detail={"error_code": "INVALID_TOKEN", "message": str(e)}
        )

    return {"detail": "Token is valid", "claims": decoded}
