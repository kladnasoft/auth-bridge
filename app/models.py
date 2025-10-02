from __future__ import annotations

import secrets
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.core.types_loader import build_service_type_enum

ServiceType = build_service_type_enum()

class ServiceLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issuer_id: str
    audience_id: str
    context: Optional[Dict[str, Any]] = Field(default=None)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ServiceLink):
            return NotImplemented
        return self.issuer_id == other.issuer_id and self.audience_id == other.audience_id

    def __hash__(self) -> int:
        return hash((self.issuer_id, self.audience_id))


class DiscoveredServiceLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    service_id: str
    context: Optional[Dict[str, Any]] = None


class EntityType(Enum):
    WORKSPACE = "workspace"
    SERVICE = "service"

class AuthBridgeEntity(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    id: str = Field(default_factory=lambda: secrets.token_hex(8))
    api_key: str = Field(default_factory=lambda: secrets.token_hex(32))
    registered_at: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    version: str = Field(default_factory=lambda: secrets.token_hex(8))
    content: Optional[Dict[str, Any]] = None
    info: Optional[Dict[str, Any]] = None

    @field_validator("version", mode="before")
    @classmethod
    def _version_to_str(cls, v):
        return str(v)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(exclude_none=True)


class WorkspaceEntity(AuthBridgeEntity):
    services: List[ServiceLink] = Field(default_factory=list)


class ServiceEntity(AuthBridgeEntity):
    type: str = ServiceType.UNKNOWN.value

    @field_validator("type", mode="before")
    @classmethod
    def validate_type(cls, v: Any):
        try:
            if isinstance(v, str):
                return ServiceType[v.upper()].value
            return v
        except KeyError as exc:
            valid_types = ", ".join([item.value for item in ServiceType])
            raise ValueError(
                f"Invalid service type: {v}. It must be one of: [{valid_types}]"
            ) from exc



class WorkspaceLimited(BaseModel):
    name: str
    id: str
    version: str
    info: Optional[Dict[str, Any]]


class ServiceLimited(BaseModel):
    name: str
    id: str
    type: str
    version: str
    info: Optional[Dict[str, Any]]


class DiscoveredService(BaseModel):
    service: ServiceLimited
    workspaces: List[WorkspaceLimited]


class DiscoveryResponse(BaseModel):
    detail: str
    system_version: str
    service: ServiceEntity
    links: List[DiscoveredService]


class TokenPayload(BaseModel):
    sub: str
    aud: str
    claims: Optional[Dict[str, Any]] = Field(default_factory=dict)
