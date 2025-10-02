from __future__ import annotations

from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, RedirectResponse
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from app.core.logging import setup_logging, get_logger
from app.core.redis import RedisManager
from app.routers.system import router as system_router
from app.routers.service import (
    router_v1 as service_router_v1,
    router_v2 as service_router_v2,
    reload_services,
)
from app.routers.workspace import router as workspace_router_v1, reload_workspaces
from app.routers.token import (
    router_v1 as token_router_v1,
    router_v2 as token_router_v2,
    load_rsa_keys,
)
from app.settings import get_settings

setup_logging("INFO")
log = get_logger("auth-bridge.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()

    if s.AUTHBRIDGE_SENTRY_DSN:
        sentry_sdk.init(
            dsn=s.AUTHBRIDGE_SENTRY_DSN,
            environment=s.AUTHBRIDGE_ENVIRONMENT,
            release=str(s.AUTHBRIDGE_BUILD_VERSION),
            traces_sample_rate=0.2,
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

    pub, prv = await load_rsa_keys()
    from app.routers import token as token_module
    token_module.PUBLIC_KEY_PEM = pub
    token_module.PRIVATE_KEY_PEM = prv

    yield


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
    app.include_router(service_router_v2)
    app.include_router(token_router_v1)
    app.include_router(token_router_v2)

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
