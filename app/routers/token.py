from __future__ import annotations

import datetime
from typing import Dict

import jwt
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import APIRouter, Depends, HTTPException, Path, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, model_validator

from app.core.redis import RedisManager, caches
from app.core.security import get_header_api_key, validate_item_api_key
from app.models import EntityType, TokenPayload
from app.settings import get_settings
from app.routers.service import get_service
from app.routers.workspace import get_workspace, reload_workspaces

router_v1 = APIRouter(prefix="/api/v1", tags=["token"])
router_v2 = APIRouter(prefix="/api/v2", tags=["token-v2"])

PUBLIC_KEY_PEM: str
PRIVATE_KEY_PEM: str


class ResponseToken(BaseModel):
    access_token: str


class Payload(BaseModel):
    payload: Dict

    @model_validator(mode="after")
    def validate_payload(self):
        payload = self.payload
        if not payload:
            raise HTTPException(status_code=400, detail="Payload: payload is missing")

        iss = payload.get("iss")
        aud = payload.get("aud")
        sub = payload.get("sub")

        if iss is None:
            raise HTTPException(status_code=400, detail="Payload: iss is missing")
        if aud is None:
            raise HTTPException(status_code=400, detail="Payload: aud is missing")
        if sub is None:
            raise HTTPException(status_code=400, detail="Payload: sub is missing")

        if iss not in caches.services:
            raise HTTPException(status_code=400, detail=f"Payload: {iss} not an existing service")
        if aud not in caches.services:
            raise HTTPException(status_code=400, detail=f"Payload: {aud} not an existing service")
        if iss == aud:
            raise HTTPException(status_code=400, detail="Payload: iss == aud, service cannot be linked to itself")
        if sub not in caches.workspaces:
            raise HTTPException(status_code=400, detail=f"Payload: {sub} not an existing workspace")
        return self


def generate_rsa_keys() -> tuple[str, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
    public_key = private_key.public_key()
    pem_private = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pem_public = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return pem_public.decode(), pem_private.decode()


async def load_rsa_keys() -> tuple[str, str]:
    rm = RedisManager()
    if await rm.is_available():
        result = await rm.get_rsa()
        if result is None:
            result = generate_rsa_keys()
            pub, prv = result
            await rm.save_rsa(pub, prv)  # best-effort, non-raising
        return result
    return generate_rsa_keys()


async def issue_jwt_token(payload: Dict, algorithm: str = "RS256", expiration_minutes: int = 60) -> str:
    payload["exp"] = datetime.datetime.utcnow() + datetime.timedelta(minutes=expiration_minutes)
    token = jwt.encode(payload, PRIVATE_KEY_PEM, algorithm=algorithm)
    return token


@router_v1.post("/token/issue", response_model=ResponseToken, operation_id="issue_token")
async def issue_token(request: Request):
    payload: dict = await request.json()
    from app.routers.service import reload_services
    from app.routers.workspace import reload_workspaces
    await reload_services()
    await reload_workspaces()

    api_key = await get_header_api_key(request)

    validated_model = Payload(payload=payload)
    iss_service_id = validated_model.payload["iss"]
    aud_service_id = validated_model.payload["aud"]
    sub_workspace_id = validated_model.payload["sub"]

    service = await get_service(iss_service_id)
    await validate_item_api_key(api_key, service, EntityType.SERVICE)

    workspace = await get_workspace(sub_workspace_id)

    is_invalid_link = True
    for link in workspace.services:
        if link.issuer_id == iss_service_id and link.audience_id == aud_service_id:
            is_invalid_link = False
            break
    if is_invalid_link:
        raise HTTPException(
            status_code=400,
            detail=f"iss: {iss_service_id} and aud:{aud_service_id} is not linked together"
        )

    token = await issue_jwt_token(
        payload=validated_model.payload,
        expiration_minutes=get_settings().ACCESS_TOKEN_EXPIRATION_MIN
    )
    return ResponseToken(access_token=token)


@router_v2.post("/token/{service_id}/issue", response_model=ResponseToken, operation_id="issue_token_v2")
async def issue_token_v2(
    request: Request,
    payload: TokenPayload,
    service_id: str = Path(..., embed=True),
):
    from app.routers.service import reload_services
    from app.routers.workspace import reload_workspaces
    await reload_services()
    await reload_workspaces()

    api_key = await get_header_api_key(request)

    keys_to_exclude = {"iss", "aud", "sub", "exp"}
    content = {"iss": service_id, "aud": payload.aud, "sub": payload.sub}
    filtered_claims = {k: v for k, v in (payload.claims or {}).items() if k not in keys_to_exclude}

    validated_model = Payload(payload=content)
    iss_service_id = validated_model.payload["iss"]
    aud_service_id = validated_model.payload["aud"]
    sub_workspace_id = validated_model.payload["sub"]
    if filtered_claims:
        validated_model.payload.update({"claims": filtered_claims})

    service = await get_service(iss_service_id)
    await validate_item_api_key(api_key, service, EntityType.SERVICE)

    workspace = await get_workspace(sub_workspace_id)

    is_invalid_link = True
    context: dict = {}
    for link in workspace.services:
        if link.issuer_id == iss_service_id and link.audience_id == aud_service_id:
            is_invalid_link = False
            context = link.context or {}
            break

    if is_invalid_link:
        raise HTTPException(
            status_code=400,
            detail=f"iss: {iss_service_id} and aud:{aud_service_id} is not linked together"
        )
    elif context:
        validated_model.payload.update(context)

    token = await issue_jwt_token(
        payload=validated_model.payload,
        expiration_minutes=get_settings().ACCESS_TOKEN_EXPIRATION_MIN
    )
    return ResponseToken(access_token=token)


# New endpoints

@router_v1.get("/token/public_key", operation_id="get_public_key")
async def get_public_key():
    """Return the RSA public key in PEM format."""
    return JSONResponse({"public_key_pem": PUBLIC_KEY_PEM})


@router_v1.post("/token/verify", operation_id="verify_token")
async def verify_token(request: Request):
    """Verify a JWT sent by a service."""
    data = await request.json()
    token = data.get("token")
    if not token:
        raise HTTPException(status_code=400, detail="Missing token")

    try:
        decoded = jwt.decode(token, PUBLIC_KEY_PEM, algorithms=["RS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

    return {"detail": "Token is valid", "claims": decoded}


# Initialized during app lifespan in app.main
PUBLIC_KEY_PEM, PRIVATE_KEY_PEM = "", ""
