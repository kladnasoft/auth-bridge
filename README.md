## 🛡️ Auth Bridge — Secure Token Issuer & Service Discovery

**Auth Bridge** is a FastAPI-based **trust and discovery service** that enables microservices to **authenticate, authorize, and discover each other** using signed tokens.
It acts as a **central bridge** between services, providing a real-time registry, workspace isolation, and dashboard visibility — all backed by **Redis** and **JWT (RS256)** signing.

---

### 🚀 Features

* 🔑 **JWT Token Issuer / Verifier** (RS256, per-service keypair)
* 🧭 **Dynamic Service Discovery** and trust links per workspace
* 🗃️ **Admin Console** for managing services, workspaces, and relationships
* 🧩 **Service Console** for issuing and validating tokens interactively
* 📊 **Dashboard** with real-time D3 trust-graph visualization
* ⚡ **Asynchronous Redis caching** with instant refresh
* 🧰 **JSON-based configuration** (info/content for each entity)
* 🧠 **Python SDK** for programmatic use

---

### 🧱 Quick Start

#### 1️⃣ Pull the image

```bash
docker pull kladnasoft/auth-bridge:latest
```

#### 2️⃣ Create the network

```bash
docker network create reflection
```

#### 3️⃣ Start Redis

```bash
docker run -d --name redis \
  --network reflection \
  -p 6379:6379 \
  redis:7-alpine \
  redis-server --appendonly yes
```

#### 4️⃣ Start auth-bridge

```bash
docker run -d --name auth-bridge \
  --network reflection \
  -p 8000:8000 \
  -e AUTHBRIDGE_ENVIRONMENT=dev \
  -e AUTHBRIDGE_API_KEYS='["be6db1c88fe4ef81d63c7eea22f8c12fec94f2c32cabd5b47284a676aa8a22c8","293a22bf6ab906f5d57d1245abbce97ecf96664285ef3d8fc2b79ea00c83a303"]' \
  -e AUTHBRIDGE_CRYPT_KEY='0c88423805e975bce92edddcf2fa9dbd9ba5e770ca731da1d237f0b45e253aeb' \
  -e REDIS_HOST=redis \
  kladnasoft/auth-bridge:latest
```

#### 5️⃣ Verify both services are running

```bash
# Check both containers
docker ps

# Check auth-bridge logs
docker logs auth-bridge

# Test the API
curl -fsS http://localhost:8000/api/v1/system/heartbeat
```

---

### 🐳 docker-compose (alternative)

```yaml
version: "3.9"
services:
  redis:
    image: redis:7-alpine
    command: ["redis-server", "--appendonly", "yes"]
    ports:
      - "6379:6379"

  authbridge:
    image: kladnasoft/auth-bridge:latest
    environment:
      AUTHBRIDGE_ENVIRONMENT: dev
      AUTHBRIDGE_API_KEYS: '["<api-key1>", "<api-key2>"]'
      AUTHBRIDGE_CRYPT_KEY: 0c88423805e975bce92edddcf2fa9dbd9ba5e770ca731da1d237f0b45e253aeb
      REDIS_HOST: redis
    ports:
      - "8000:8000"

networks:
  default:
    name: reflection
```

Then open:

* **Admin Console:** [http://localhost:8000/admin](http://localhost:8000/admin)
* **Service Console:** [http://localhost:8000/bridge](http://localhost:8000/bridge)
* **Trust Dashboard:** [http://localhost:8000/dashboard](http://localhost:8000/dashboard)
* **API Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)

---

### ⚙️ Environment Variables

| Variable                      | Description                                                       | Example                        |
| ----------------------------- | ----------------------------------------------------------------- | ------------------------------ |
| `AUTHBRIDGE_ENVIRONMENT`      | Environment mode (`dev`, `stage`, `prod`)                         | `dev`                          |
| `AUTHBRIDGE_API_KEYS`         | **JSON array** of admin/API keys (used by `/admin`, `/dashboard`) | `["<api-key1>", "<api-key2>"]` |
| `AUTHBRIDGE_CRYPT_KEY`        | **32-byte hex key (64 hex chars)** used for encryption            | `0c8842…e253aeb`               |
| `ACCESS_TOKEN_EXPIRATION_MIN` | Token lifetime in minutes (optional)                              | `60`                           |
| `REDIS_HOST` / `REDIS_PORT`   | Redis connection host/port                                        | `redis` / `6379`               |
| `AUTHBRIDGE_SENTRY_DSN`       | Optional Sentry DSN for monitoring                                | *(empty)*                      |
| `AUTHBRIDGE_APP_TYPES`        | Optional comma-separated list of custom service types             | `reflection,supertable,ai`     |

> **Note:** `AUTHBRIDGE_API_KEYS` must be valid JSON (quoted strings inside square brackets).

---

### 🧭 Built-In Interfaces

#### 1️⃣ Admin Console (`/admin`)

Manage:

* Services (create, delete, rekey, update info/content)
* Workspaces (create, delete, update metadata)
* Links (issuer ⇄ audience per workspace)
* System ops (rotate RSA keys, diagnostics)

Front-end only (admin key stored in browser `localStorage`).
*Ideal for trusted DevOps / administrators.*

#### 2️⃣ Service Console (`/bridge`)

For individual microservices to:

* Validate identity via `x-api-key`
* Discover outbound / inbound trust links
* Issue tokens to linked services
* Decode / verify JWTs

All client-side, calling public endpoints.
*Ideal for developers or service owners.*

#### 3️⃣ Dashboard (`/dashboard`)

Visualizes:

* Real-time service trust graph (D3)
* Redis state and uptime
* JWKS key rotation status
* Type distribution and metrics

Optional Prometheus via `/metrics`.
*Ideal for stakeholders and observability.*

---

### 🧠 API Highlights

**Services**

```
GET  /api/v1/services/list
POST /api/v1/services
PUT  /api/v1/services/{id}/rekey
```

**Workspaces**

```
GET  /api/v1/workspaces/list
POST /api/v1/workspaces
POST /api/v1/workspaces/{id}/link-service
POST /api/v1/workspaces/{id}/unlink-service
```

**Tokens**

```
POST /api/v1/token/{service_id}/issue   → issue JWT
POST /api/v1/token/verify               → verify JWT
GET  /api/v1/token/public_key           → JWKS
```

**System**

```
GET  /api/v1/system/heartbeat
POST /api/v1/system/rotate-keys
POST /api/v1/system/rotate
```

---

### 🧩 Python SDK Example

```python
# Example usage from the repo's client code
from app.client import AdminClient, ServiceClient

# Admin registers a service
admin = AdminClient(api_key="admin-key")
svc = admin.create_service("reflection", "Reflection", "ai")

# Service issues a JWT token for its linked audience
client = ServiceClient(api_key="service-key")
token = client.issue_token(
    issuer_id="reflection",
    audience_id="supertable",
    sub="workspace-1",
    claims={"scope": ["read"]}
)
print(client.verify_token(token))
```

---

### 📊 Dashboard Preview

> Real-time interactive view of all service relationships.
> Each service type is color-coded (AI, BI, Reflection, SuperTable, etc.), and trust links are shown dynamically between nodes.

---

### 🧠 Tech Stack

**Backend:** FastAPI · Redis AsyncIO · JWT (RS256) · Encryption
**Frontend:** TailwindCSS · D3.js · FontAwesome
**Monitoring:** Prometheus (optional) · Sentry (optional)

---

### 📜 License

Apache 2.0 © 2025 **Kladna Soft Kft.**
Docker image maintained by **Kladna Soft** • part of the *Data Island* ecosystem.
