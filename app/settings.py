from __future__ import annotations

import base64
import hashlib
import json
import os
from functools import lru_cache
from typing import List, Optional, Tuple

from cryptography.fernet import Fernet
from dotenv import load_dotenv
from pydantic import PrivateAttr
from pydantic_settings import BaseSettings

load_dotenv()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_sentinels(raw: Optional[str]) -> List[Tuple[str, int]]:
    if not raw:
        return []
    sentinels: List[Tuple[str, int]] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            host, port = part.rsplit(":", 1)
            try:
                sentinels.append((host.strip(), int(port.strip())))
            except ValueError:
                # ignore malformed entries
                continue
        else:
            # default sentinel port
            sentinels.append((part, 26379))
    return sentinels


class Settings(BaseSettings):
    AUTHBRIDGE_BUILD_VERSION: str = os.getenv("AUTHBRIDGE_BUILD_VERSION", "1.0.0")
    AUTHBRIDGE_ENVIRONMENT: str = os.getenv("AUTHBRIDGE_ENVIRONMENT", "dev")

    # Admin API keys as list
    AUTHBRIDGE_API_KEYS: List[str] = []
    AUTHBRIDGE_CRYPT_KEY: str = os.getenv(
        "AUTHBRIDGE_CRYPT_KEY", "change-me-please-change-me-32bytes-min"
    )

    ACCESS_TOKEN_EXPIRATION_MIN: int = int(os.getenv("ACCESS_TOKEN_EXPIRATION_MIN", "60"))

    # Redis (AUTHBRIDGE_* preferred; REDIS_* kept for backward compatibility)
    AUTHBRIDGE_REDIS_NAMESPACE: str = os.getenv("AUTHBRIDGE_REDIS_NAMESPACE", "authbridge")

    AUTHBRIDGE_REDIS_SENTINEL: bool = _env_bool("AUTHBRIDGE_REDIS_SENTINEL", False)
    AUTHBRIDGE_REDIS_SENTINELS: str = os.getenv("AUTHBRIDGE_REDIS_SENTINELS", "")
    AUTHBRIDGE_REDIS_SENTINEL_MASTER: str = os.getenv(
        "AUTHBRIDGE_REDIS_SENTINEL_MASTER", "mymaster"
    )

    # Standard Redis
    REDIS_HOST: str = os.getenv("AUTHBRIDGE_REDIS_HOST", os.getenv("REDIS_HOST", "localhost"))
    REDIS_PORT: int = int(os.getenv("AUTHBRIDGE_REDIS_PORT", os.getenv("REDIS_PORT", "6379")))
    REDIS_DB: int = int(os.getenv("AUTHBRIDGE_REDIS_DB", os.getenv("REDIS_DB", "0")))
    REDIS_PASSWORD: Optional[str] = os.getenv(
        "AUTHBRIDGE_REDIS_PASSWORD", os.getenv("REDIS_PASSWORD")
    )
    AUTHBRIDGE_REDIS_DECODE_RESPONSES: bool = _env_bool(
        "AUTHBRIDGE_REDIS_DECODE_RESPONSES",
        _env_bool("REDIS_DECODE_RESPONSES", False),
    )

    # Sentry
    AUTHBRIDGE_SENTRY_DSN: Optional[str] = os.getenv("AUTHBRIDGE_SENTRY_DSN")

    # App types loading (not modified here)
    AUTHBRIDGE_APP_TYPES: Optional[str] = os.getenv("AUTHBRIDGE_APP_TYPES")

    # Streams / pubsub
    AUDIT_STREAM_NAME: str = os.getenv("AUDIT_STREAM_NAME") or f"{os.getenv('AUTHBRIDGE_REDIS_NAMESPACE', 'authbridge')}:audit"
    PUBSUB_CHANNEL: str = os.getenv("PUBSUB_CHANNEL") or f"{os.getenv('AUTHBRIDGE_REDIS_NAMESPACE', 'authbridge')}:caches"

    # Rate limit defaults
    RL_TOKEN_ISSUE_LIMIT_PER_MIN: int = int(os.getenv("RL_TOKEN_ISSUE_LIMIT_PER_MIN", "120"))
    RL_DISCOVERY_LIMIT_PER_MIN: int = int(os.getenv("RL_DISCOVERY_LIMIT_PER_MIN", "240"))

    # Derived sentinel endpoints (computed in model_post_init)
    AUTHBRIDGE_REDIS_SENTINELS_PARSED: List[Tuple[str, int]] = []

    # Private attribute: not part of pydantic validation
    _cipher_suite: Fernet = PrivateAttr()

    # --- Compute derived values & parse env after validation ---
    def model_post_init(self, __context) -> None:  # pydantic v2 hook
        # Parse admin keys JSON or CSV if provided in env
        env_keys = os.getenv("AUTHBRIDGE_API_KEYS")
        if env_keys:
            parsed: List[str] = []
            try:
                maybe_json = json.loads(env_keys)
                if isinstance(maybe_json, list):
                    parsed = [str(x) for x in maybe_json]
                elif isinstance(maybe_json, str) and maybe_json.strip():
                    parsed = [maybe_json.strip()]
            except Exception:
                parsed = [k.strip() for k in env_keys.split(",") if k.strip()]
            if parsed:
                self.AUTHBRIDGE_API_KEYS = parsed

        # Parse sentinel list
        self.AUTHBRIDGE_REDIS_SENTINELS_PARSED = _parse_sentinels(self.AUTHBRIDGE_REDIS_SENTINELS)

        # Derive Fernet key from AUTHBRIDGE_CRYPT_KEY (sha256 → base64)
        key = hashlib.sha256(self.AUTHBRIDGE_CRYPT_KEY.encode()).digest()
        fkey = base64.urlsafe_b64encode(key)
        self._cipher_suite = Fernet(fkey)

    @property
    def CIPHER_SUITE(self) -> Fernet:
        """Read-only accessor for the derived cipher suite."""
        return self._cipher_suite


@lru_cache()
def get_settings() -> Settings:
    return Settings()
