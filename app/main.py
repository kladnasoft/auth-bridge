# app/main.py
from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, RedirectResponse
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from app.core.logging import setup_logging, get_logger
from app.core.redis import RedisManager, caches
from app.routers.system import router as system_router
from app.routers.service import (
    router_v1 as service_router_v1,
    reload_services,
)
from app.routers.workspace import router as workspace_router_v1, reload_workspaces
from app.routers.token import (
    router_v1 as token_router_v1,
    load_rsa_keys,
)
from app.routers.dashboard import router as dashboard_router
from app.settings import get_settings

setup_logging("INFO")
log = get_logger("auth-bridge.app")


async def _pubsub_listener():
    """
    Background task to listen for cache invalidation events and eagerly refresh caches.
    """
    s = get_settings()
    rm = RedisManager()
    if not await rm.is_available():
        log.warning("PubSub disabled: Redis unavailable at startup.")
        return
    pubsub = rm.redis.pubsub()
    await pubsub.subscribe(s.PUBSUB_CHANNEL)
    log.info("Subscribed to pubsub channel: %s", s.PUBSUB_CHANNEL)
    try:
        async for msg in pubsub.listen():
            if msg is None or msg.get("type") != "message":
                continue
            try:
                payload = msg["data"].decode()
                # On any event, we simply trigger reloads (on-demand caches will dedupe)
                await caches.reload_services_if_needed(rm, log_details=False)
                await caches.reload_workspaces_if_needed(rm, log_details=False)
                log.debug("Processed cache event: %s", payload)
            except Exception:
                log.exception("Error processing pubsub message")
    except asyncio.CancelledError:
        log.info("Pubsub listener cancelled.")
    finally:
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(s.PUBSUB_CHANNEL)
            await pubsub.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()

    if s.AUTHBRIDGE_SENTRY_DSN:
        sentry_sdk.init(
            dsn=s.AUTHBRIDGE_SENTRY_DSN,
            environment=s.AUTHBRIDGE_ENVIRONMENT,
            release=str(s.AUTHBRIDGE_BUILD_VERSION),
            traces_sample_rate=1,
            integrations=[
                FastApiIntegration(transaction_style="url"),
                StarletteIntegration(transaction_style="url"),
            ],
        )
        log.info("Sentry initialized.")
    else:
        log.info("Sentry disabled (AUTHBRIDGE_SENTRY_DSN empty).")

    log.info(
        "---------- AUTH BRIDGE ----------\n"
        f"Version: {s.AUTHBRIDGE_BUILD_VERSION}\n"
        f"Environment: {s.AUTHBRIDGE_ENVIRONMENT}\n"
        f"Token TTL: {s.ACCESS_TOKEN_EXPIRATION_MIN}\n"
        f"Redis Host: {s.REDIS_HOST}\n"
        f"Redis Port: {s.REDIS_PORT}\n"
        "------------------------------"
    )

    rm = RedisManager()
    if await rm.is_available():
        await reload_services(False)
        await reload_workspaces(False)
    else:
        log.warning(
            "Redis is not reachable at startup; running in degraded in-memory mode until Redis is up."
        )

    await load_rsa_keys()  # sets key ring in token router

    # start pubsub listener
    pubsub_task = asyncio.create_task(_pubsub_listener())

    try:
        yield
    finally:
        pubsub_task.cancel()
        with contextlib.suppress(Exception):
            await pubsub_task


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="Auth Bridge",
        version=s.AUTHBRIDGE_BUILD_VERSION,
        lifespan=lifespan,
    )

    @app.get("/", include_in_schema=False)
    async def _root():
        return RedirectResponse(url="/docs", status_code=302)

    @app.get("/healthz", include_in_schema=False)
    async def _healthz():
        return JSONResponse({"status": "ok"})

    # Routers
    app.include_router(system_router)
    app.include_router(workspace_router_v1)
    app.include_router(service_router_v1)
    app.include_router(token_router_v1)
    app.include_router(dashboard_router)

    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        openapi_schema = get_openapi(
            title="Auth Bridge API schema",
            version=s.AUTHBRIDGE_BUILD_VERSION,
            description="Auth Bridge API",
            routes=app.routes,
        )
        openapi_schema["openapi"] = "3.0.3"
        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.openapi = custom_openapi
    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
