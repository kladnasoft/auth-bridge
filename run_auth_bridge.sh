#!/usr/bin/env bash
set -euo pipefail

# ---------- Config (edit if needed) ----------
NETWORK_NAME="${NETWORK_NAME:-reflection}"
AUTH_IMAGE="${AUTH_IMAGE:-kladnasoft/auth-bridge:latest}"
AUTH_CONTAINER_NAME="${AUTH_CONTAINER_NAME:-auth-bridge}"
REDIS_CONTAINER_NAME="${REDIS_CONTAINER_NAME:-redis}"
AUTH_PORT="${AUTH_PORT:-8000}"

# You can override these via env before calling the script
AUTHBRIDGE_ENVIRONMENT="${AUTHBRIDGE_ENVIRONMENT:-dev}"
AUTHBRIDGE_API_KEYS="${AUTHBRIDGE_API_KEYS:-[\"be6db1c88fe4ef81d63c7eea22f8c12fec94f2c32cabd5b47284a676aa8a22c8\", \"293a22bf6ab906f5d57d1245abbce97ecf96664285ef3d8fc2b79ea00c83a303\"]}"
AUTHBRIDGE_CRYPT_KEY="${AUTHBRIDGE_CRYPT_KEY:-0c88423805e975bce92edddcf2fa9dbd9ba5e770ca731da1d237f0b45e253aeb}"
REDIS_HOST="${REDIS_HOST:-redis}"
# --------------------------------------------

GREEN="\033[1;32m"
YELLOW="\033[1;33m"
RED="\033[1;31m"
NC="\033[0m"

echo -e "${YELLOW}==> Ensuring Docker network '${NETWORK_NAME}' exists...${NC}"
if ! docker network inspect "${NETWORK_NAME}" >/dev/null 2>&1; then
  docker network create "${NETWORK_NAME}" >/dev/null
  echo -e "${GREEN}✓ Network '${NETWORK_NAME}' created.${NC}"
else
  echo -e "${GREEN}✓ Network '${NETWORK_NAME}' already exists.${NC}"
fi

# Start (or restart) Redis
if docker ps -a --format '{{.Names}}' | grep -q "^${REDIS_CONTAINER_NAME}$"; then
  echo -e "${YELLOW}==> Redis container '${REDIS_CONTAINER_NAME}' already exists. Restarting...${NC}"
  docker rm -f "${REDIS_CONTAINER_NAME}" >/dev/null 2>&1 || true
fi

echo -e "${YELLOW}==> Starting Redis...${NC}"
docker run -d --name "${REDIS_CONTAINER_NAME}" \
  --network "${NETWORK_NAME}" \
  -p 6379:6379 \
  redis:7-alpine \
  redis-server --appendonly yes >/dev/null

# Wait for Redis ready
echo -e "${YELLOW}==> Waiting for Redis to be ready...${NC}"
ATTEMPTS=60
SLEEP=1
for i in $(seq 1 $ATTEMPTS); do
  if docker exec "${REDIS_CONTAINER_NAME}" sh -lc 'redis-cli ping' 2>/dev/null | grep -q "PONG"; then
    echo -e "${GREEN}✓ Redis is ready.${NC}"
    break
  fi
  sleep "$SLEEP"
  if [ "$i" -eq "$ATTEMPTS" ]; then
    echo -e "${RED}✗ Redis did not become ready in time.${NC}"
    exit 1
  fi
done

# Start (or restart) auth-bridge
if docker ps -a --format '{{.Names}}' | grep -q "^${AUTH_CONTAINER_NAME}$"; then
  echo -e "${YELLOW}==> Auth-bridge container '${AUTH_CONTAINER_NAME}' already exists. Restarting...${NC}"
  docker rm -f "${AUTH_CONTAINER_NAME}" >/dev/null 2>&1 || true
fi

echo -e "${YELLOW}==> Starting auth-bridge...${NC}"
docker run -d --name "${AUTH_CONTAINER_NAME}" \
  --network "${NETWORK_NAME}" \
  -e AUTHBRIDGE_ENVIRONMENT="${AUTHBRIDGE_ENVIRONMENT}" \
  -e AUTHBRIDGE_API_KEYS="${AUTHBRIDGE_API_KEYS}" \
  -e AUTHBRIDGE_CRYPT_KEY="${AUTHBRIDGE_CRYPT_KEY}" \
  -e REDIS_HOST="${REDIS_HOST}" \
  -p ${AUTH_PORT}:8000 \
  "${AUTH_IMAGE}" >/dev/null

# Wait for service heartbeat
echo -e "${YELLOW}==> Waiting for auth-bridge to pass heartbeat...${NC}"
ATTEMPTS=90
SLEEP=1
for i in $(seq 1 $ATTEMPTS); do
  if curl -fsS "http://localhost:${AUTH_PORT}/api/v1/system/heartbeat" >/dev/null 2>&1; then
    echo -e "${GREEN}✓ auth-bridge is healthy and responding on port ${AUTH_PORT}.${NC}"
    echo -e "${GREEN}✓ All done.${NC}"
    exit 0
  fi
  sleep "$SLEEP"
done

echo -e "${RED}✗ auth-bridge did not become healthy in time. Check 'docker logs ${AUTH_CONTAINER_NAME}'.${NC}"
exit 1
