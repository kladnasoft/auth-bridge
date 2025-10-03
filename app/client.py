"""
Auth Bridge Python SDK

Split-by-role clients:
- AdminClient   → provisioning (create/delete/link/rekey)
- ServiceClient → runtime (discovery, token issue, callers)

No third-party deps (uses urllib). Python 3.8+.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Tuple

# ------------------------- Configuration -------------------------------------

DEFAULT_BASE_URL = os.getenv("AUTHBRIDGE_BASE_URL", "http://localhost:8000")
ADMIN_KEY = os.getenv("AUTHBRIDGE_ADMIN_KEY")     # sysadmin x-api-key
ENTITY_KEY = os.getenv("AUTHBRIDGE_API_KEY")      # service x-api-key


# ------------------------- Internal HTTP base --------------------------------

class _HttpBase:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, *, admin_key: Optional[str] = None, entity_key: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.admin_key = admin_key
        self.entity_key = entity_key

    # Low-level request
    def _request(self, method: str, path: str, *, data: Optional[dict] = None,
                 headers: Optional[dict] = None, use_admin: bool = False) -> Any:
        url = self.base_url + path
        body: Optional[bytes] = None
        hdrs: Dict[str, str] = {"accept": "application/json"}
        if headers:
            hdrs.update(headers)

        # choose auth header
        if use_admin:
            if not self.admin_key:
                raise RuntimeError("Missing ADMIN key for admin-scoped operation.")
            hdrs["x-api-key"] = self.admin_key
        else:
            if not self.entity_key:
                raise RuntimeError("Missing ENTITY key for service-scoped operation.")
            hdrs["x-api-key"] = self.entity_key

        if data is not None:
            body = json.dumps(data).encode("utf-8")
            hdrs["content-type"] = "application/json"

        req = urllib.request.Request(url, data=body, headers=hdrs, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode()
                if not raw:
                    return {}
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            try:
                err = json.loads(e.read().decode() or "{}")
            except Exception:
                err = {"status": e.code, "message": e.reason}
            raise RuntimeError(f"HTTP {e.code} {e.reason}: {err}") from None
        except urllib.error.URLError as e:
            raise RuntimeError(f"Connection error: {e}") from None


# ------------------------- Service (runtime) client ---------------------------

class ServiceClient(_HttpBase):
    """
    Runtime client acting AS a registered service.
    Uses the service's own API key (x-api-key) for all calls.
    """

    # ---- Token operations (v1 only; v2 removed) ----
    def issue_token(self, iss: str, aud: str, sub: str, claims: Optional[dict] = None) -> str:
        """
        Issue a JWT on behalf of `iss` (issuer service) for audience `aud` scoped to workspace `sub`.
        Endpoint: /api/v1/token/issue
        """
        payload: Dict[str, Any] = {"iss": iss, "aud": aud, "sub": sub}
        if claims:
            payload["claims"] = claims
        data = self._request("POST", "/api/v1/token/issue", data=payload, use_admin=False)
        return data["access_token"]

    def verify_token(self, token: str) -> dict:
        """Verify a JWT. Endpoint: /api/v1/token/verify"""
        return self._request("POST", "/api/v1/token/verify", data={"token": token}, use_admin=False)

    # ---- Discovery & callers ----
    def discovery(self, service_id: str) -> dict:
        """Service discovery (v1). Endpoint: /api/v1/services/{id}/discovery"""
        sid = urllib.parse.quote(service_id)
        return self._request("GET", f"/api/v1/services/{sid}/discovery", use_admin=False)

    def callers(self, service_id: str) -> dict:
        """Who can call me? Endpoint: /api/v1/services/{id}/callers"""
        sid = urllib.parse.quote(service_id)
        return self._request("GET", f"/api/v1/services/{sid}/callers", use_admin=False)

    # ---- Public keys ----
    def get_jwks(self) -> dict:
        """Retrieve current JWKS (public keys)."""
        return self._request("GET", "/.well-known/jwks.json", use_admin=False)


# ------------------------- Admin (provisioning) client ------------------------

class AdminClient(_HttpBase):
    """
    Provisioning client for sysadmins.
    Uses the ADMIN x-api-key for all calls.
    """

    # ---- Services CRUD ----
    def create_service(self, service_id: str, name: str, type_: str,
                       api_key: Optional[str] = None, info: Optional[dict] = None,
                       content: Optional[dict] = None) -> dict:
        payload: Dict[str, Any] = {
            "id": service_id,
            "name": name,
            "type": type_,
        }
        if api_key:
            payload["api_key"] = api_key
        if info is not None:
            payload["info"] = info
        if content is not None:
            payload["content"] = content
        return self._request("POST", "/api/v1/services", data=payload, use_admin=True)

    def get_service(self, service_id: str) -> dict:
        sid = urllib.parse.quote(service_id)
        return self._request("GET", f"/api/v1/services/{sid}", use_admin=True)

    def delete_service(self, service_id: str) -> dict:
        sid = urllib.parse.quote(service_id)
        return self._request("DELETE", f"/api/v1/services/{sid}", use_admin=True)

    def rekey_service(self, service_id: str, if_match: Optional[str] = None) -> dict:
        sid = urllib.parse.quote(service_id)
        headers = {"If-Match": if_match} if if_match else None
        return self._request("PUT", f"/api/v1/services/{sid}/rekey", headers=headers, use_admin=True)

    def update_service_info(self, service_id: str, info: dict, if_match: Optional[str] = None) -> dict:
        sid = urllib.parse.quote(service_id)
        headers = {"If-Match": if_match} if if_match else None
        return self._request("PUT", f"/api/v1/services/{sid}/info", data=info, headers=headers, use_admin=True)

    def update_service_content(self, service_id: str, content: dict, if_match: Optional[str] = None) -> dict:
        sid = urllib.parse.quote(service_id)
        headers = {"If-Match": if_match} if if_match else None
        return self._request("PUT", f"/api/v1/services/{sid}/content", data=content, headers=headers, use_admin=True)

    # ---- Workspaces CRUD ----
    def create_workspace(self, workspace_id: str, name: str, api_key: Optional[str] = None,
                         info: Optional[dict] = None, content: Optional[dict] = None) -> dict:
        payload: Dict[str, Any] = {"id": workspace_id, "name": name}
        if api_key:
            payload["api_key"] = api_key
        if info is not None:
            payload["info"] = info
        if content is not None:
            payload["content"] = content
        return self._request("POST", "/api/v1/workspaces", data=payload, use_admin=True)

    def get_workspace(self, workspace_id: str) -> dict:
        wid = urllib.parse.quote(workspace_id)
        return self._request("GET", f"/api/v1/workspaces/{wid}", use_admin=True)

    def delete_workspace(self, workspace_id: str) -> dict:
        wid = urllib.parse.quote(workspace_id)
        return self._request("DELETE", f"/api/v1/workspaces/{wid}", use_admin=True)

    # ---- Linking ----
    def link_service(self, workspace_id: str, issuer_id: str, audience_id: str,
                     context: Optional[dict] = None, if_match: Optional[str] = None) -> dict:
        wid = urllib.parse.quote(workspace_id)
        headers = {"If-Match": if_match} if if_match else None
        payload = {"issuer_id": issuer_id, "audience_id": audience_id, "context": context or {}}
        return self._request("POST", f"/api/v1/workspaces/{wid}/link-service", data=payload, headers=headers, use_admin=True)

    def unlink_service(self, workspace_id: str, issuer_id: str, audience_id: str,
                       context: Optional[dict] = None, if_match: Optional[str] = None) -> dict:
        wid = urllib.parse.quote(workspace_id)
        headers = {"If-Match": if_match} if if_match else None
        payload = {"issuer_id": issuer_id, "audience_id": audience_id, "context": context or {}}
        return self._request("POST", f"/api/v1/workspaces/{wid}/unlink-service", data=payload, headers=headers, use_admin=True)


__all__ = ["ServiceClient", "AdminClient"]
