from __future__ import annotations

import asyncio
import json
from typing import Dict, List, Optional, Tuple, Type, TypeVar

import redis.asyncio as redis
from redis.exceptions import ConnectionError, TimeoutError, ResponseError
from cryptography.fernet import Fernet

from app.core.logging import get_logger
from app.models import EntityType, WorkspaceEntity, ServiceEntity
from app.settings import get_settings

log = get_logger("auth-bridge.redis")

T = TypeVar("T", WorkspaceEntity, ServiceEntity)


class RedisManager:
    """
    Async Redis manager with connection pooling and encryption.
    Safe to construct even if Redis is down; methods catch connection errors
    so the app can run in a degraded in-memory mode.
    """

    def __init__(self) -> None:
        s = get_settings()
        self._pool = redis.ConnectionPool(
            host=s.REDIS_HOST,
            port=s.REDIS_PORT,
            db=s.REDIS_DB,
            password=s.REDIS_PASSWORD,
            max_connections=512,          # high concurrency
            decode_responses=False,
            socket_keepalive=True,
            socket_timeout=2.0,
            socket_connect_timeout=2.0,
        )
        self.redis = redis.Redis(connection_pool=self._pool)
        self.cipher: Fernet = s.CIPHER_SUITE  # type: ignore[assignment]

    # ------------------- key helpers -------------------
    @staticmethod
    def item_key(item_id: str, prefix: str) -> str:
        return f"{prefix}:{item_id}:data"

    @staticmethod
    def version_key(item_id: str, prefix: str) -> str:
        return f"{prefix}:{item_id}:version"

    @staticmethod
    def system_key(item_type: str) -> str:
        return f"system:{item_type}:version"

    @staticmethod
    def rsa_key(item_id: str, prefix: str = "rsa") -> str:
        return f"{prefix}:{item_id}:data"

    # ------------------- connectivity -------------------
    async def is_available(self) -> bool:
        try:
            await self.redis.ping()
            return True
        except Exception:
            return False

    # ------------------- versioning -------------------
    async def get_system_version(self, item_type: str) -> str:
        try:
            val = await self.redis.get(self.system_key(item_type))
            return val.decode() if val else ""
        except Exception as exc:
            log.warning("Redis unavailable during get_system_version(%s): %s", item_type, exc)
            return ""

    async def set_system_version(self, item_type: str, version: str) -> None:
        try:
            await self.redis.set(self.system_key(item_type), version)
        except Exception as exc:
            # degradable path: log warning, don’t raise
            log.warning("Redis unavailable during set_system_version(%s): %s", item_type, exc)

    # ------------------- search -------------------
    async def search_ids(self, item_type: str) -> List[str]:
        ids: List[str] = []
        try:
            async for key in self.redis.scan_iter(match=f"{item_type}:*:data"):
                parts = key.decode().split(":")
                if len(parts) >= 3:
                    ids.append(parts[1])
        except Exception as exc:
            log.warning("Redis unavailable during search_ids(%s): %s", item_type, exc)
        return ids

    # ------------------- CRUD -------------------
    async def get_item(self, item_id: str, item_type: str) -> Optional[T]:
        key = self.item_key(item_id, item_type)
        try:
            blob = await self.redis.get(key)
        except Exception as exc:
            log.warning("Redis unavailable during get_item(%s:%s): %s", item_type, item_id, exc)
            return None

        if not blob:
            return None
        try:
            data = json.loads(self.cipher.decrypt(blob).decode())
            model: Type[T] = WorkspaceEntity if item_type == EntityType.WORKSPACE.value else ServiceEntity  # type: ignore[assignment]
            return model.model_validate(data)  # type: ignore[return-value]
        except Exception:
            log.exception("Failed to decrypt/parse item %s:%s", item_type, item_id)
            raise

    async def save_item(self, item: T, item_type: str, new_system_version: str) -> str:
        item.version = new_system_version
        ser = json.dumps(item.to_dict()).encode()
        enc = self.cipher.encrypt(ser)

        pipe = self.redis.pipeline()
        try:
            pipe.set(self.item_key(item.id, item_type), enc)
            pipe.set(self.version_key(item.id, item_type), item.version)
            pipe.set(self.system_key(item_type), new_system_version)
            await pipe.execute()
        except (ConnectionError, TimeoutError, ResponseError) as exc:
            # In write paths we keep ERROR (so you know persistence failed),
            # but the caller can decide whether to fail the request.
            log.error("Redis pipeline error during save_item: %s", exc)
            raise
        return item.version

    async def delete_item(self, item_id: str, item_type: str, new_system_version: str) -> None:
        pipe = self.redis.pipeline()
        try:
            pipe.delete(self.item_key(item_id, item_type))
            pipe.delete(self.version_key(item_id, item_type))
            pipe.set(self.system_key(item_type), new_system_version)
            await pipe.execute()
        except (ConnectionError, TimeoutError, ResponseError) as exc:
            log.error("Redis pipeline error during delete_item: %s", exc)
            raise

    # ------------------- RSA keys -------------------
    async def get_rsa(self) -> Optional[Tuple[str, str]]:
        try:
            pub = await self.redis.get(self.rsa_key("public"))
            prv = await self.redis.get(self.rsa_key("private"))
        except Exception as exc:
            log.warning("Redis unavailable during get_rsa(): %s", exc)
            return None

        if not pub or not prv:
            return None
        try:
            prv_dec = self.cipher.decrypt(prv).decode()
            return (pub.decode(), prv_dec)
        except Exception:
            log.exception("RSA private key decrypt failed")
            return None

    async def save_rsa(self, public_pem: str, private_pem: str) -> None:
        """
        Best-effort persistence of RSA. If Redis is down, log a WARNING and return
        without raising so startup remains clean in degraded mode.
        """
        enc_priv = self.cipher.encrypt(private_pem.encode())
        try:
            await self.redis.set(self.rsa_key("public"), public_pem)
            await self.redis.set(self.rsa_key("private"), enc_priv)
        except Exception as exc:
            log.warning("Redis unavailable during save_rsa(): %s", exc)
            # Do not raise; degraded mode is acceptable.
            return


# -------- In-process caches with version guards (high-throughput) -------------
class InMemoryCaches:
    """
    Keeps latest workspaces/services in memory, refreshed only when the
    respective Redis system version changes. Guarded by asyncio locks.
    Safe if Redis is temporarily unavailable (no refresh, stale cache).
    """
    def __init__(self) -> None:
        self.workspaces: Dict[str, WorkspaceEntity] = {}
        self.services: Dict[str, ServiceEntity] = {}
        self.workspace_sys_ver: str = ""
        self.service_sys_ver: str = ""
        self._lock_workspaces = asyncio.Lock()
        self._lock_services = asyncio.Lock()

    async def reload_workspaces_if_needed(self, rm: RedisManager, log_details: bool = False) -> None:
        new_ver = await rm.get_system_version(EntityType.WORKSPACE.value)
        if new_ver and new_ver == self.workspace_sys_ver:
            return
        async with self._lock_workspaces:
            new_ver = await rm.get_system_version(EntityType.WORKSPACE.value)
            if new_ver and new_ver == self.workspace_sys_ver:
                return
            ids = await rm.search_ids(EntityType.WORKSPACE.value)
            items: Dict[str, WorkspaceEntity] = {}
            for i in ids:
                it = await rm.get_item(i, EntityType.WORKSPACE.value)
                if it:
                    items[i] = it
                    if log_details:
                        log.info("Loaded workspace: id=%s name=%s ver=%s", i, it.name, it.version)
            if ids:
                self.workspaces = items
                self.workspace_sys_ver = new_ver or ""

    async def reload_services_if_needed(self, rm: RedisManager, log_details: bool = False) -> None:
        new_ver = await rm.get_system_version(EntityType.SERVICE.value)
        if new_ver and new_ver == self.service_sys_ver:
            return
        async with self._lock_services:
            new_ver = await rm.get_system_version(EntityType.SERVICE.value)
            if new_ver and new_ver == self.service_sys_ver:
                return
            ids = await rm.search_ids(EntityType.SERVICE.value)
            items: Dict[str, ServiceEntity] = {}
            for i in ids:
                it = await rm.get_item(i, EntityType.SERVICE.value)
                if it:
                    items[i] = it
                    if log_details:
                        log.info("Loaded service: id=%s name=%s ver=%s", i, it.name, it.version)
            if ids:
                self.services = items
                self.service_sys_ver = new_ver or ""


caches = InMemoryCaches()
