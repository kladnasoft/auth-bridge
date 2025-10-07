#!/usr/bin/env sh
set -e

REDIS_HOST="${REDIS_HOST:-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"
APP_MODULE="${APP_MODULE:-app.main:app}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

printf "\033[1;33m==> Waiting for Redis at %s:%s...\033[0m\n" "$REDIS_HOST" "$REDIS_PORT"

# Use Python to test TCP connect (works on slim without netcat/bash /dev/tcp)
python - <<PYEOF
import os, socket, time, sys
host = os.environ.get("REDIS_HOST", "redis")
port = int(os.environ.get("REDIS_PORT", "6379"))
deadline = time.time() + 120
while time.time() < deadline:
    s = socket.socket()
    try:
        s.settimeout(1.0)
        s.connect((host, port))
        print("\033[1;32m✓ Redis reachable.\033[0m", flush=True)
        sys.exit(0)
    except Exception:
        time.sleep(1)
    finally:
        s.close()
print("\033[0;31m✗ Redis did not become reachable in time.\033[0m", flush=True)
sys.exit(1)
PYEOF

printf "\033[1;32m✓ Starting API...\033[0m\n"

exec uvicorn "${APP_MODULE}" --host "${HOST}" --port "${PORT}" --proxy-headers --forwarded-allow-ips='*'
