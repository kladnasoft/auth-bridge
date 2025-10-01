# AuthBridge 🔐

[![PyPI version](https://img.shields.io/pypi/v/auth-bridge.svg)](https://pypi.org/project/auth-bridge/)
[![Python Version](https://img.shields.io/pypi/pyversions/auth-bridge.svg)](https://pypi.org/project/auth-bridge/)
[![License](https://img.shields.io/pypi/l/auth-bridge.svg)](https://pypi.org/project/auth-bridge/)

FastAPI-based service discovery, organization & application registry, and token issuer for secure inter-service communication. Optimized for high throughput with async Redis caching and optional Sentry integration.

## Features

- **Organization & Application Management** - Multi-tenant registry with isolated environments
- **JWT Token Issuance** - Secure inter-service authentication with RSA key management
- **High Performance** - Async Redis caching with in-process cache fallback
- **Production Ready** - Comprehensive logging, monitoring, and environment-based configuration
- **Modular Design** - Versioned API endpoints with clean separation of concerns
- **Security First** - Encrypted key storage with Fernet, admin API key authentication

## Quick Start

### Installation

```bash
# Install from PyPI
pip install auth-bridge

# Or install from source
git clone https://github.com/kladnasoft/auth-bridge
cd auth-bridge
pip install -e .
```

### Running the Service

```bash
# Set required environment variables
export AUTHBRIDGE_ENVIRONMENT=dev
export AUTHBRIDGE_API_KEYS='["your-admin-key-here"]'
export AUTHBRIDGE_CRYPT_KEY="your-32-char-encryption-key-here"
export REDIS_HOST=localhost
export REDIS_PORT=6379

# Start the service
uvicorn auth_bridge.app.main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000` with interactive docs at `http://localhost:8000/docs`.

## Core Concepts

### Organizations
Represent tenants or business entities that own and manage applications.

### Applications
Microservices, APIs, or software components that belong to organizations and need secure communication.

### Tokens
JWT tokens issued to applications for authenticating inter-service requests.

## API Usage

### Managing Organizations

```bash
# List all organizations
curl -H "x-api-key: your-admin-key" http://localhost:8000/api/v1/orgs

# Create a new organization
curl -X POST -H "x-api-key: your-admin-key" -H "Content-Type: application/json" \
  -d '{"name": "Acme Corp", "metadata": {"contact": "admin@acme.com"}}' \
  http://localhost:8000/api/v1/orgs
```

### Managing Applications

```bash
# Create an application for an organization
curl -X POST -H "x-api-key: your-admin-key" -H "Content-Type: application/json" \
  -d '{"name": "payment-service", "description": "Handles payment processing"}' \
  http://localhost:8000/api/v1/orgs/{org_id}/apps

# List applications in an organization
curl -H "x-api-key: your-admin-key" \
  http://localhost:8000/api/v1/orgs/{org_id}/apps
```

### Token Management

```bash
# Issue a token for an application
curl -X POST -H "x-api-key: your-admin-key" \
  http://localhost:8000/api/v1/orgs/{org_id}/apps/{app_id}/tokens/issue

# The response will include a JWT token for secure service communication
```

## Environment Configuration

| Variable | Description | Required |
|----------|-------------|----------|
| `AUTHBRIDGE_ENVIRONMENT` | Environment: dev, stage, qa, prod | Yes |
| `AUTHBRIDGE_API_KEYS` | JSON list of admin API keys | Yes |
| `AUTHBRIDGE_CRYPT_KEY` | 32+ char secret for encryption | Yes |
| `AUTHBRIDGE_BUILD_VERSION` | Build version identifier | No |
| `AUTHBRIDGE_SENTRY_DSN` | Sentry DSN for error tracking | No |
| `REDIS_HOST` | Redis server hostname | Yes |
| `REDIS_PORT` | Redis server port | Yes |
| `REDIS_PASSWORD` | Redis password (if required) | No |
| `REDIS_DB` | Redis database number | No |
| `ACCESS_TOKEN_EXPIRATION_MIN` | Token TTL in minutes (default: 60) | No |

## Docker Deployment

### Using Docker Compose

```yaml
# docker-compose.yml
version: '3.8'
services:
  auth-bridge:
    build: .
    ports:
      - "8000:8000"
    environment:
      - AUTHBRIDGE_ENVIRONMENT=prod
      - AUTHBRIDGE_API_KEYS=${AUTHBRIDGE_API_KEYS}
      - AUTHBRIDGE_CRYPT_KEY=${AUTHBRIDGE_CRYPT_KEY}
      - REDIS_HOST=redis
    depends_on:
      - redis

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
```

```bash
# Start with Docker Compose
docker compose up --build
```

### Building the Image

```bash
docker build -t auth-bridge:latest .
docker run -p 8000:8000 --env-file .env auth-bridge:latest
```

## Development

### Setting up Development Environment

```bash
# Clone and setup
git clone https://github.com/yourusername/auth-bridge
cd auth-bridge
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install in development mode
pip install -e .

# Run with auto-reload
uvicorn auth_bridge.app.main:app --reload
```

## Security

- All sensitive data encrypted with Fernet using your `AUTHBRIDGE_CRYPT_KEY`
- RSA key pairs for JWT signing stored securely in Redis
- Admin API key authentication required for management operations
- JWT tokens for secure inter-service communication
- Optional Sentry integration for security monitoring

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit your changes: `git commit -m 'Add amazing feature'`
4. Push to the branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- 📖 [Documentation](https://github.com/kladnasoft/auth-bridge/wiki)
- 🐛 [Issue Tracker](https://github.com/kladnasoft/auth-bridge/issues)
- 💬 [Discussions](https://github.com/kladnasoft/auth-bridge/discussions)

---

Built with ❤️ using FastAPI, Redis, and Python.
```
