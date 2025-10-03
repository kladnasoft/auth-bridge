# Auth Bridge

FastAPI-based service discovery, workspace & service registry, and token issuer
for secure inter-service communication. Optimized for high throughput with
async Redis caching and optional Sentry.

## Features
- Modular `APIRouter` (current public surface under **v1** paths)
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

Pass `x-api-key` header with either a global admin key or an entity's `api_key`.

### Services
- `GET /api/v1/services/list`
- `GET /api/v1/services` (admin)
- `GET /api/v1/services/{service_id}` (entity or admin)
- `GET /api/v1/services/{service_id}/version` (entity or admin)
- `POST /api/v1/services` create (admin)
- `PUT /api/v1/services/{service_id}/content` (admin)
- `PUT /api/v1/services/{service_id}/info` (admin)
- `PUT /api/v1/services/{service_id}/rekey` (admin)
- `DELETE /api/v1/services/{service_id}` (admin)
- `GET /api/v1/services/{service_id}/callers` — *Who can call me?* (entity or admin)

### Discovery
- `GET /api/v1/services/{service_id}/discovery` (entity or admin) — **v2-style response under v1 path**
  - Returns service links grouped by target service with workspace contexts.

### Token
- `POST /api/v1/token/{service_id}/issue` — **structured issuer path (formerly v2), now under v1**
  - Body:
    ```json
    {
      "aud": "<audience_service_id>",
      "sub": "<workspace_id>",
      "claims": { "k": "v" }
    }
    ```
- `POST /api/v1/token/verify` — verify JWT
- `GET /api/v1/token/public_key` — current public key
- `GET /api/v1/token/jwks` — all active public keys

### Workspaces
- `GET /api/v1/workspaces/list`
- `GET /api/v1/workspaces` (admin)
- `GET /api/v1/workspaces/{workspace_id}` (entity or admin)
- `GET /api/v1/workspaces/{workspace_id}/version` (entity or admin)
- `POST /api/v1/workspaces` create (admin)
- `POST /api/v1/workspaces/{workspace_id}/link-service` (admin)
- `POST /api/v1/workspaces/{workspace_id}/unlink-service` (admin)
- `PUT /api/v1/workspaces/{workspace_id}/content` (admin)
- `PUT /api/v1/workspaces/{workspace_id}/info` (admin)
- `PUT /api/v1/workspaces/{workspace_id}/rekey` (admin)
- `DELETE /api/v1/workspaces/{workspace_id}` (admin)

## Health & System

- `GET /api/v1/system/version`
- `GET /api/v1/system/heartbeat`
- `GET /api/v1/system/jwks`
- `POST /api/v1/system/rotate-keys` (admin)
- `POST /api/v1/system/rotate` reloads API keys (admin)
- `GET /api/v1/system/diagnostics`

## Python SDK (CLI) Usage

Environment variables:
- `AUTHBRIDGE_BASE_URL` (default: `http://localhost:8000`)
- `AUTHBRIDGE_ADMIN_KEY` (admin `x-api-key`)
- `AUTHBRIDGE_API_KEY` (entity `x-api-key`)

Examples:

**Issue a token (v1 structured path):**
```bash
python -m app.client token issue --service-id svc_a --aud svc_b --sub ws1 --claims '{"role": "writer"}'
```

**Verify a token:**
```bash
python -m app.client token verify --token "$JWT"
```

**Discovery (v1 path, v2-style response):**
```bash
python -m app.client discovery --service-id svc_a
```

**Create a service (admin):**
```bash
python -m app.client services create --id svc_a --name "Service A" --type app
```

**Create a workspace (admin) and link services:**
```bash
python -m app.client workspaces create --id ws1 --name "Workspace 1"
python -m app.client workspaces link --workspace-id ws1 --issuer svc_a --audience svc_b --context '{"database":"db","schema":"dbo"}'
```
