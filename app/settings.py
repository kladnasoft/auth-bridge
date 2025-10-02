from __future__ import annotations

import base64
import hashlib
import json
from functools import lru_cache
from typing import List, Optional

from cryptography.fernet import Fernet
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="allow")

    AUTHBRIDGE_BUILD_VERSION: str = Field(default="1.0.0")
    AUTHBRIDGE_ENVIRONMENT: str = Field(default="dev")  # dev|stage|qa|prod

    AUTHBRIDGE_API_KEYS: List[str] = Field(default_factory=list)
    AUTHBRIDGE_SENTRY_DSN: str = Field(default="")

    ACCESS_TOKEN_EXPIRATION_MIN: int = Field(default=10, gt=0)

    REDIS_HOST: str = Field(default="localhost")
    REDIS_PORT: int = Field(default=6379)
    REDIS_DB: int = Field(default=0)
    REDIS_PASSWORD: Optional[str] = Field(default=None)

    AUTHBRIDGE_CRYPT_KEY: str = Field(min_length=32)

    CIPHER_SUITE: Fernet | None = None

    @field_validator("AUTHBRIDGE_ENVIRONMENT")
    @classmethod
    def _valid_env(cls, v: str) -> str:
        allowed = {"dev", "stage", "qa", "prod"}
        if v not in allowed:
            raise ValueError(f"AUTHBRIDGE_ENVIRONMENT must be one of {allowed}")
        return v

    @field_validator("AUTHBRIDGE_API_KEYS", mode="before")
    @classmethod
    def _parse_api_keys(cls, v):
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            try:
                parsed = json.loads(v)
                if not isinstance(parsed, list) or not all(isinstance(x, str) for x in parsed):
                    raise ValueError
                if any(len(k) < 16 for k in parsed):
                    raise ValueError("One or more AUTHBRIDGE_API_KEYS are too short.")
                return parsed
            except Exception as exc:
                raise ValueError(
                    'AUTHBRIDGE_API_KEYS must be JSON list of strings, e.g. ["hex1","hex2"]'
                ) from exc
        return v

    @field_validator("CIPHER_SUITE", mode="before")
    @classmethod
    def _build_cipher(cls, v, info):
        secret = info.data.get("AUTHBRIDGE_CRYPT_KEY")
        if not secret or len(secret) < 32:
            raise ValueError("AUTHBRIDGE_CRYPT_KEY must be provided (>= 32 chars).")
        hashed = hashlib.sha256(secret.encode()).digest()
        key = base64.urlsafe_b64encode(hashed)
        return Fernet(key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv(override=False)
    return Settings()  # type: ignore[call-arg]
