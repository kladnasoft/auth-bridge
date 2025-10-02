# Auth Bridge

FastAPI-based service discovery, workspace & service registry, and token issuer
for secure inter-service communication. Optimized for high throughput with
async Redis caching and optional Sentry.

## Features
- Modular `APIRouter` with versioned endpoints
- Async Redis + in-process caches guarded by version keys
- Optional Sentry (enable by setting `AUTHBRIDGE_SENTRY_DSN`)
- RSA key management for JWTs stored in Redis (encrypted with Fernet)
- Unified logging; production-grade settings via environment
- **Dynamic Service Types**: configurable via ENV (`AUTHBRIDGE_APP_TYPES`) or `application_types.json`

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Environment Variables

- `AUTHBRIDGE_BUILD_VERSION`
- `AUTHBRIDGE_ENVIRONMENT` = dev|stage|qa|prod
- `AUTHBRIDGE_API_KEYS` = JSON list of admin keys (e.g. `["hex1","hex2"]`)
- `AUTHBRIDGE_CRYPT_KEY` = >=32 chars secret used to derive Fernet key
- `ACCESS_TOKEN_EXPIRATION_MIN` = token TTL (minutes)
- `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `REDIS_PASSWORD` (optional)
- `AUTHBRIDGE_SENTRY_DSN` (optional)
- `AUTHBRIDGE_APP_TYPES` (optional, comma-separated list of dynamic service types)

## Docker

Build image:
```bash
docker build -t auth-bridge:latest .
```

Run with Compose (requires external network `reflection`):
```bash
docker compose up --build
```

## Make requests

Pass `x-api-key` header with either a global admin key or an entity`s api_key.

- `GET /api/v1/services/list`
- `POST /api/v1/services` create
- `POST /api/v1/token/{service_id}/issue`
- Workspace management endpoints under `/api/v1/workspaces`
- System endpoints under `/api/v1/system`

## Dynamic Service Types

You can define service types dynamically without changing code.

### Option 1: ENV variable

```bash
export AUTHBRIDGE_APP_TYPES="crm,erp,etl"
```

### Option 2: JSON file

Create `application_types.json` in project root:

```json
["crm", "erp", "etl"]
```

### Fallback (default)

If neither ENV nor JSON is found, the defaults are used:

```json
["unknown", "reflection", "supertable", "mirage", "ai", "bi", "email_api"]
```

## Health & System

- `GET /api/v1/system/version`
- `GET /api/v1/system/heartbeat`
- `POST /api/v1/system/rotate` reloads API keys

