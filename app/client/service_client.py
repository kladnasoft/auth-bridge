"""
Auth Bridge Python SDK — Service Client (runtime)

This client acts *as a registered service* using its own API key.

Auth:
- Header: x-api-key = SERVICE_KEY (env)

Env:
- AUTHBRIDGE_BASE_URL (default: http://localhost:8000)
- SERVICE_KEY           ← service-scoped API key

Python: 3.8+ (no third-party deps, uses urllib)
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

from dotenv import load_dotenv
load_dotenv()

DEFAULT_BASE_URL = os.getenv("AUTHBRIDGE_BASE_URL", "http://localhost:8000")
SERVICE_KEY = os.getenv("SERVICE_KEY")  # specific service key (x-api-key)


class _HttpBase:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, *, entity_key: Optional[str] = SERVICE_KEY):
        self.base_url = base_url.rstrip("/")
        self.entity_key = entity_key

    def _request(
        self,
        method: str,
        path: str,
        *,
        data: Optional[dict] = None,
        headers: Optional[dict] = None,
    ) -> Any:
        if not self.entity_key:
            raise RuntimeError("Missing SERVICE_KEY for service-scoped operation.")
        url = self.base_url + (path if path.startswith("/") else f"/{path}")

        body: Optional[bytes] = None
        hdrs: Dict[str, str] = {"accept": "application/json", "x-api-key": self.entity_key}
        if headers:
            hdrs.update(headers)
        if data is not None:
            body = json.dumps(data).encode("utf-8")
            hdrs["content-type"] = "application/json"

        req = urllib.request.Request(url, data=body, headers=hdrs, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode()
                ctype = resp.headers.get("Content-Type", "")
                if not raw:
                    return {}
                return json.loads(raw) if "application/json" in ctype else raw
        except urllib.error.HTTPError as e:
            try:
                err = json.loads(e.read().decode() or "{}")
            except Exception:
                err = {"status": e.code, "message": e.reason}
            raise RuntimeError(f"HTTP {e.code} {e.reason}: {err}") from None
        except urllib.error.URLError as e:
            raise RuntimeError(f"Connection error: {e}") from None


class ServiceClient(_HttpBase):
    """
    Runtime client for:
      - Token issue/verify (v1)
      - Service discovery & 'who can call me'
      - JWKS/public key retrieval
    """

    # ---------------- Token (v1) ----------------

    def issue_token(self, service_id: str, aud: str, sub: str, claims: Optional[dict] = None) -> str:
        """
        Issue a JWT *as* `service_id` (issuer) for audience `aud` within workspace `sub`.

        Endpoint: POST /api/v1/token/{service_id}/issue
        Body: { "aud": "...", "sub": "...", "claims": {...} }
        """
        sid = urllib.parse.quote(service_id)
        payload: Dict[str, Any] = {"aud": aud, "sub": sub}
        if claims:
            payload["claims"] = claims
        data = self._request("POST", f"/api/v1/token/{sid}/issue", data=payload)
        return data["access_token"]

    def verify_token(self, token: str) -> dict:
        """Verify a JWT. Endpoint: POST /api/v1/token/verify"""
        return self._request("POST", "/api/v1/token/verify", data={"token": token})

    # --------------- Discovery ------------------

    def discovery(self, service_id: str) -> dict:
        """Service discovery (v1). Endpoint: GET /api/v1/services/{id}/discovery"""
        sid = urllib.parse.quote(service_id)
        return self._request("GET", f"/api/v1/services/{sid}/discovery")

    def callers(self, service_id: str) -> dict:
        """Who can call me? Endpoint: GET /api/v1/services/{id}/callers"""
        sid = urllib.parse.quote(service_id)
        return self._request("GET", f"/api/v1/services/{sid}/callers")

    # --------------- Keys/JWKS ------------------

    def get_public_key(self) -> dict:
        """Current RSA public key and kid."""
        return self._request("GET", "/api/v1/token/public_key")

    def get_jwks(self) -> dict:
        """JWKS-like document of all active public keys."""
        return self._request("GET", "/api/v1/token/jwks")


__all__ = ["ServiceClient"]
