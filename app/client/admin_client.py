"""
Auth Bridge Python SDK — Admin Client (provisioning)

This client performs privileged provisioning operations:
  - CRUD for services/workspaces
  - Rekey/update info/content
  - Link/unlink services in a workspace
  - System ops (rotate RSA keys, reload admin keys)

Auth:
- Header: x-api-key = one entry from AUTHBRIDGE_API_KEYS (env)

Env:
- AUTHBRIDGE_BASE_URL  (default: http://localhost:8000)
- AUTHBRIDGE_API_KEYS  ← JSON list or CSV of admin keys; first one is used by default

Python: 3.8+ (no third-party deps, uses urllib)
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Sequence

from dotenv import load_dotenv
load_dotenv()

DEFAULT_BASE_URL = os.getenv("AUTHBRIDGE_BASE_URL", "http://localhost:8000")


def _pick_admin_key() -> Optional[str]:
    """
    Accepts:
      - AUTHBRIDGE_API_KEYS='["k1","k2"]'
      - AUTHBRIDGE_API_KEYS='k1,k2'
      - AUTHBRIDGE_API_KEYS='k1'
    Uses the *first* key by default.
    """
    raw = os.getenv("AUTHBRIDGE_API_KEYS")
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, Sequence) and parsed:
            return str(parsed[0])
        if isinstance(parsed, str) and parsed.strip():
            return parsed.strip()
    except Exception:
        # CSV fallback
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        if parts:
            return parts[0]
    return None


class _HttpBase:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, *, admin_key: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.admin_key = admin_key or _pick_admin_key()

    def _request(
        self,
        method: str,
        path: str,
        *,
        data: Optional[dict] = None,
        headers: Optional[dict] = None,
    ) -> Any:
        if not self.admin_key:
            raise RuntimeError("Missing admin key. Set AUTHBRIDGE_API_KEYS or pass admin_key.")
        url = self.base_url + (path if path.startswith("/") else f"/{path}")

        body: Optional[bytes] = None
        hdrs: Dict[str, str] = {"accept": "application/json", "x-api-key": self.admin_key}
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


class AdminClient(_HttpBase):
    """
    Provisioning/admin operations.
    """

    # -------- Services --------

    def create_service(
        self,
        service_id: str,
        name: str,
        type_: str,
        api_key: Optional[str] = None,
        info: Optional[dict] = None,
        content: Optional[dict] = None,
    ) -> dict:
        payload: Dict[str, Any] = {"id": service_id, "name": name, "type": type_}
        if api_key:
            payload["api_key"] = api_key
        if info is not None:
            payload["info"] = info
        if content is not None:
            payload["content"] = content
        return self._request("POST", "/api/v1/services", data=payload)

    def get_service(self, service_id: str) -> dict:
        sid = urllib.parse.quote(service_id)
        return self._request("GET", f"/api/v1/services/{sid}")

    def delete_service(self, service_id: str) -> dict:
        sid = urllib.parse.quote(service_id)
        return self._request("DELETE", f"/api/v1/services/{sid}")

    def rekey_service(self, service_id: str, if_match: Optional[str] = None) -> dict:
        sid = urllib.parse.quote(service_id)
        headers = {"If-Match": if_match} if if_match else None
        return self._request("PUT", f"/api/v1/services/{sid}/rekey", headers=headers)

    def update_service_info(self, service_id: str, info: dict, if_match: Optional[str] = None) -> dict:
        sid = urllib.parse.quote(service_id)
        headers = {"If-Match": if_match} if if_match else None
        return self._request("PUT", f"/api/v1/services/{sid}/info", data=info, headers=headers)

    def update_service_content(self, service_id: str, content: dict, if_match: Optional[str] = None) -> dict:
        sid = urllib.parse.quote(service_id)
        headers = {"If-Match": if_match} if if_match else None
        return self._request("PUT", f"/api/v1/services/{sid}/content", data=content, headers=headers)

    # -------- Workspaces --------

    def create_workspace(
        self,
        workspace_id: str,
        name: str,
        api_key: Optional[str] = None,
        info: Optional[dict] = None,
        content: Optional[dict] = None,
    ) -> dict:
        payload: Dict[str, Any] = {"id": workspace_id, "name": name}
        if api_key:
            payload["api_key"] = api_key
        if info is not None:
            payload["info"] = info
        if content is not None:
            payload["content"] = content
        return self._request("POST", "/api/v1/workspaces", data=payload)

    def get_workspace(self, workspace_id: str) -> dict:
        wid = urllib.parse.quote(workspace_id)
        return self._request("GET", f"/api/v1/workspaces/{wid}")

    def delete_workspace(self, workspace_id: str) -> dict:
        wid = urllib.parse.quote(workspace_id)
        return self._request("DELETE", f"/api/v1/workspaces/{wid}")

    # -------- Links --------

    def link_service(
        self,
        workspace_id: str,
        issuer_id: str,
        audience_id: str,
        context: Optional[dict] = None,
        if_match: Optional[str] = None,
    ) -> dict:
        wid = urllib.parse.quote(workspace_id)
        headers = {"If-Match": if_match} if if_match else None
        payload = {"issuer_id": issuer_id, "audience_id": audience_id, "context": context or {}}
        return self._request("POST", f"/api/v1/workspaces/{wid}/link-service", data=payload, headers=headers)

    def unlink_service(
        self,
        workspace_id: str,
        issuer_id: str,
        audience_id: str,
        context: Optional[dict] = None,
        if_match: Optional[str] = None,
    ) -> dict:
        wid = urllib.parse.quote(workspace_id)
        headers = {"If-Match": if_match} if if_match else None
        payload = {"issuer_id": issuer_id, "audience_id": audience_id, "context": context or {}}
        return self._request("POST", f"/api/v1/workspaces/{wid}/unlink-service", data=payload, headers=headers)

    # -------- System --------

    def rotate_rsa_keys(self) -> dict:
        """POST /api/v1/system/rotate-keys"""
        return self._request("POST", "/api/v1/system/rotate-keys")

    def reload_admin_keys_from_env(self) -> dict:
        """POST /api/v1/system/rotate — reload AUTHBRIDGE_API_KEYS env on server"""
        return self._request("POST", "/api/v1/system/rotate")


__all__ = ["AdminClient"]
