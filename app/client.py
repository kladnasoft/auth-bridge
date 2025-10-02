"""
Auth Bridge Python SDK + CLI

- Zero external dependencies (uses urllib).
- Works against the Auth Bridge FastAPI service.
- Supports:
    * Token issue/verify
    * Service discovery (v1, v2) and "who-can-call-me"
    * JWKS retrieval, manual key rotation
    * CRUD: create service/workspace, rekey, update info/content
    * Link/unlink services inside a workspace
- Optional optimistic concurrency via If-Match header.

Environment variables:
    AUTHBRIDGE_BASE_URL   (default: http://localhost:8000)
    AUTHBRIDGE_ADMIN_KEY  (admin x-api-key for privileged ops)
    AUTHBRIDGE_API_KEY    (entity x-api-key for service/workspace scoped ops)

CLI usage examples:
    python -m app.client token issue --iss svc_a --aud svc_b --sub ws1
    python -m app.client token verify --token <JWT>
    python -m app.client discovery v2 --service-id svc_a
    python -m app.client services create --id svc_a --name "Service A" --type APP
    python -m app.client workspaces create --id ws1 --name "Workspace 1"
    python -m app.client workspaces link --workspace-id ws1 --issuer svc_a --audience svc_b
    python -m app.client system jwks
    python -m app.client system rotate-keys
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional


DEFAULT_BASE_URL = os.getenv("AUTHBRIDGE_BASE_URL", "http://localhost:8000")
ADMIN_KEY = os.getenv("AUTHBRIDGE_ADMIN_KEY")  # used for privileged operations
ENTITY_KEY = os.getenv("AUTHBRIDGE_API_KEY")   # used for entity-scoped operations


class AuthBridgeClient:
    """
    Minimal, dependency-free HTTP client for Auth Bridge.
    """

    def __init__(self, base_url: str = DEFAULT_BASE_URL, admin_key: Optional[str] = ADMIN_KEY, entity_key: Optional[str] = ENTITY_KEY):
        self.base_url = base_url.rstrip("/")
        self.admin_key = admin_key
        self.entity_key = entity_key

    # ------------------------- Internal HTTP helpers -------------------------

    def _headers(self, admin: bool = False, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        key = (self.admin_key if admin else self.entity_key) or self.entity_key or self.admin_key
        if key:
            headers["x-api-key"] = key
        if extra:
            headers.update(extra)
        return headers

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.base_url}{path}"

    def _request(self, method: str, path: str, data: Optional[dict] = None, headers: Optional[dict] = None, admin: bool = False) -> Any:
        url = self._url(path)
        body = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(url, data=body, method=method.upper(), headers=self._headers(admin=admin, extra=headers))
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                ct = resp.headers.get("Content-Type", "")
                payload = resp.read()
                if "application/json" in ct:
                    return json.loads(payload.decode())
                return payload.decode()
        except urllib.error.HTTPError as e:
            try:
                err = json.loads(e.read().decode())
            except Exception:
                err = {"status": e.code, "message": e.reason}
            raise RuntimeError(f"HTTP {e.code} {e.reason}: {err}") from None
        except urllib.error.URLError as e:
            raise RuntimeError(f"Connection error: {e}") from None

    # ------------------------- Token operations ------------------------------

    def issue_token(self, iss: str, aud: str, sub: str, claims: Optional[dict] = None) -> str:
        """
        Issue a JWT on behalf of `iss` for audience `aud` within workspace `sub`.
        Uses /api/v1/token/issue
        """
        payload = {"iss": iss, "aud": aud, "sub": sub}
        if claims:
            payload["claims"] = claims
        data = self._request("POST", "/api/v1/token/issue", data=payload, admin=False)
        return data["access_token"]

    def issue_token_v2(self, service_id: str, aud: str, sub: str, claims: Optional[dict] = None) -> str:
        """Issue token via /api/v2/token/{service_id}/issue (more structured claims handling)."""
        payload = {"aud": aud, "sub": sub, "claims": claims or {}}
        data = self._request("POST", f"/api/v2/token/{urllib.parse.quote(service_id)}/issue", data=payload, admin=False)
        return data["access_token"]

    def verify_token(self, token: str) -> dict:
        """Verify a JWT via /api/v1/token/verify"""
        return self._request("POST", "/api/v1/token/verify", data={"token": token}, admin=False)

    def get_public_key(self) -> dict:
        """Get current public key (PEM) and kid."""
        return self._request("GET", "/api/v1/token/public_key", admin=False)

    def get_jwks(self) -> dict:
        """Get JWKS-like list of all public keys."""
        return self._request("GET", "/api/v1/token/jwks", admin=False)

    # ------------------------- Discovery operations --------------------------

    def discovery_v1(self, service_id: str) -> dict:
        return self._request("GET", f"/api/v1/services/{urllib.parse.quote(service_id)}/discovery", admin=False)

    def discovery_v2(self, service_id: str) -> dict:
        return self._request("GET", f"/api/v2/services/{urllib.parse.quote(service_id)}/discovery", admin=False)

    def callers(self, service_id: str) -> dict:
        """Who can call me?"""
        return self._request("GET", f"/api/v1/services/{urllib.parse.quote(service_id)}/callers", admin=False)

    # ------------------------- System/Admin operations -----------------------

    def system_jwks(self) -> dict:
        return self._request("GET", "/api/v1/system/jwks", admin=False)

    def rotate_keys(self) -> dict:
        """Manual RSA key rotation (admin)."""
        return self._request("POST", "/api/v1/system/rotate-keys", admin=True)

    def rotate_admin_keys_from_env(self) -> dict:
        """Reload AUTHBRIDGE_API_KEYS from the environment (admin)."""
        return self._request("POST", "/api/v1/system/rotate", admin=True)

    def diagnostics(self) -> dict:
        return self._request("GET", "/api/v1/system/diagnostics", admin=False)

    # ------------------------- Services CRUD ---------------------------------

    def create_service(self, service_id: str, name: str, type_: str, api_key: Optional[str] = None,
                       info: Optional[dict] = None, content: Optional[dict] = None) -> dict:
        payload = {
            "id": service_id,
            "name": name,
            "type": type_,
            "api_key": api_key or self._generate_key(),
            "info": info or {},
            "content": content or {},
            "version": "",
        }
        return self._request("POST", "/api/v1/services", data=payload, admin=True)

    def get_service(self, service_id: str) -> dict:
        return self._request("GET", f"/api/v1/services/{urllib.parse.quote(service_id)}", admin=False)

    def get_service_version(self, service_id: str) -> str:
        res = self._request("GET", f"/api/v1/services/{urllib.parse.quote(service_id)}/version", admin=False)
        return res["version"]

    def rekey_service(self, service_id: str, if_match: Optional[str] = None) -> dict:
        headers = {"If-Match": if_match} if if_match else None
        return self._request("PUT", f"/api/v1/services/{urllib.parse.quote(service_id)}/rekey", headers=headers, admin=True)

    def update_service_content(self, service_id: str, content: dict, if_match: Optional[str] = None) -> dict:
        headers = {"If-Match": if_match} if if_match else None
        return self._request("PUT", f"/api/v1/services/{urllib.parse.quote(service_id)}/content", data=content, headers=headers, admin=True)

    def update_service_info(self, service_id: str, info: dict, if_match: Optional[str] = None) -> dict:
        headers = {"If-Match": if_match} if if_match else None
        return self._request("PUT", f"/api/v1/services/{urllib.parse.quote(service_id)}/info", data=info, headers=headers, admin=True)

    def delete_service(self, service_id: str) -> dict:
        return self._request("DELETE", f"/api/v1/services/{urllib.parse.quote(service_id)}", admin=True)

    # ------------------------- Workspaces CRUD --------------------------------

    def create_workspace(self, workspace_id: str, name: str, api_key: Optional[str] = None,
                         info: Optional[dict] = None, content: Optional[dict] = None) -> dict:
        payload = {
            "id": workspace_id,
            "name": name,
            "api_key": api_key or self._generate_key(),
            "info": info or {},
            "content": content or {},
            "version": "",
            "services": [],
        }
        return self._request("POST", "/api/v1/workspaces", data=payload, admin=True)

    def get_workspace(self, workspace_id: str) -> dict:
        return self._request("GET", f"/api/v1/workspaces/{urllib.parse.quote(workspace_id)}", admin=False)

    def get_workspace_version(self, workspace_id: str) -> str:
        res = self._request("GET", f"/api/v1/workspaces/{urllib.parse.quote(workspace_id)}/version", admin=False)
        return res["version"]

    def rekey_workspace(self, workspace_id: str, if_match: Optional[str] = None) -> dict:
        headers = {"If-Match": if_match} if if_match else None
        return self._request("PUT", f"/api/v1/workspaces/{urllib.parse.quote(workspace_id)}/rekey", headers=headers, admin=True)

    def update_workspace_content(self, workspace_id: str, content: dict, if_match: Optional[str] = None) -> dict:
        headers = {"If-Match": if_match} if if_match else None
        return self._request("PUT", f"/api/v1/workspaces/{urllib.parse.quote(workspace_id)}/content", data=content, headers=headers, admin=True)

    def update_workspace_info(self, workspace_id: str, info: dict, if_match: Optional[str] = None) -> dict:
        headers = {"If-Match": if_match} if if_match else None
        return self._request("PUT", f"/api/v1/workspaces/{urllib.parse.quote(workspace_id)}/info", data=info, headers=headers, admin=True)

    def delete_workspace(self, workspace_id: str) -> dict:
        return self._request("DELETE", f"/api/v1/workspaces/{urllib.parse.quote(workspace_id)}", admin=True)

    # ------------------------- Linking ---------------------------------------

    def link_service(self, workspace_id: str, issuer_id: str, audience_id: str, context: Optional[dict] = None, if_match: Optional[str] = None) -> dict:
        headers = {"If-Match": if_match} if if_match else None
        payload = {"issuer_id": issuer_id, "audience_id": audience_id, "context": context or {}}
        return self._request("POST", f"/api/v1/workspaces/{urllib.parse.quote(workspace_id)}/link-service", data=payload, headers=headers, admin=True)

    def unlink_service(self, workspace_id: str, issuer_id: str, audience_id: str, context: Optional[dict] = None, if_match: Optional[str] = None) -> dict:
        headers = {"If-Match": if_match} if if_match else None
        payload = {"issuer_id": issuer_id, "audience_id": audience_id, "context": context or {}}
        return self._request("POST", f"/api/v1/workspaces/{urllib.parse.quote(workspace_id)}/unlink-service", data=payload, headers=headers, admin=True)

    # ------------------------- Utilities -------------------------------------

    @staticmethod
    def _generate_key() -> str:
        import secrets
        return secrets.token_hex(32)


# ============================================================================ #
#                                      CLI                                     #
# ============================================================================ #

def _print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2, sort_keys=True))


def cli() -> None:
    parser = argparse.ArgumentParser(description="Auth Bridge CLI")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"Base URL (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--admin-key", default=ADMIN_KEY, help="Admin x-api-key (for privileged ops)")
    parser.add_argument("--api-key", default=ENTITY_KEY, help="Entity x-api-key (for service/workspace ops)")

    sub = parser.add_subparsers(dest="cmd", required=True)

    # token
    token = sub.add_parser("token")
    token_sub = token.add_subparsers(dest="token_cmd", required=True)
    t_issue = token_sub.add_parser("issue")
    t_issue.add_argument("--iss", required=True)
    t_issue.add_argument("--aud", required=True)
    t_issue.add_argument("--sub", required=True)
    t_issue.add_argument("--claims", help="JSON string of extra claims", default="{}")
    t_issue_v2 = token_sub.add_parsers()

    t_verify = token_sub.add_parser("verify")
    t_verify.add_argument("--token", required=True)

    # discovery
    disc = sub.add_parser("discovery")
    disc_sub = disc.add_subparsers(dest="disc_cmd", required=True)
    d_v1 = disc_sub.add_parser("v1")
    d_v1.add_argument("--service-id", required=True)
    d_v2 = disc_sub.add_parser("v2")
    d_v2.add_argument("--service-id", required=True)
    d_callers = disc_sub.add_parser("callers")
    d_callers.add_argument("--service-id", required=True)

    # system
    sys_p = sub.add_parser("system")
    sys_sub = sys_p.add_subparsers(dest="sys_cmd", required=True)
    sys_sub.add_parser("jwks")
    sys_sub.add_parser("rotate-keys")
    sys_sub.add_parser("rotate-admin-keys")
    sys_sub.add_parser("diagnostics")

    # services
    svc = sub.add_parser("services")
    svc_sub = svc.add_subparsers(dest="svc_cmd", required=True)
    svc_create = svc_sub.add_parser("create")
    svc_create.add_argument("--id", required=True)
    svc_create.add_argument("--name", required=True)
    svc_create.add_argument("--type", required=True)
    svc_create.add_argument("--api-key")
    svc_create.add_argument("--info", default="{}")
    svc_create.add_argument("--content", default="{}")

    svc_sub.add_parser("list")
    svc_get = svc_sub.add_parser("get")
    svc_get.add_argument("--id", required=True)
    svc_ver = svc_sub.add_parser("version")
    svc_ver.add_argument("--id", required=True)
    svc_rekey = svc_sub.add_parser("rekey")
    svc_rekey.add_argument("--id", required=True)
    svc_rekey.add_argument("--if-match")
    svc_ucontent = svc_sub.add_parser("update-content")
    svc_ucontent.add_argument("--id", required=True)
    svc_ucontent.add_argument("--content", required=True)
    svc_ucontent.add_argument("--if-match")
    svc_uinfo = svc_sub.add_parser("update-info")
    svc_uinfo.add_argument("--id", required=True)
    svc_uinfo.add_argument("--info", required=True)
    svc_uinfo.add_argument("--if-match")
    svc_delete = svc_sub.add_parser("delete")
    svc_delete.add_argument("--id", required=True)

    # workspaces
    ws = sub.add_parser("workspaces")
    ws_sub = ws.add_subparsers(dest="ws_cmd", required=True)
    ws_create = ws_sub.add_parser("create")
    ws_create.add_argument("--id", required=True)
    ws_create.add_argument("--name", required=True)
    ws_create.add_argument("--api-key")
    ws_create.add_argument("--info", default="{}")
    ws_create.add_argument("--content", default="{}")
    ws_sub.add_parser("list")
    ws_get = ws_sub.add_parser("get")
    ws_get.add_argument("--id", required=True)
    ws_ver = ws_sub.add_parser("version")
    ws_ver.add_argument("--id", required=True)
    ws_rekey = ws_sub.add_parser("rekey")
    ws_rekey.add_argument("--id", required=True)
    ws_rekey.add_argument("--if-match")
    ws_ucontent = ws_sub.add_parser("update-content")
    ws_ucontent.add_argument("--id", required=True)
    ws_ucontent.add_argument("--content", required=True)
    ws_ucontent.add_argument("--if-match")
    ws_uinfo = ws_sub.add_parser("update-info")
    ws_uinfo.add_argument("--id", required=True)
    ws_uinfo.add_argument("--info", required=True)
    ws_uinfo.add_argument("--if-match")

    ws_link = ws_sub.add_parser("link")
    ws_link.add_argument("--workspace-id", required=True)
    ws_link.add_argument("--issuer", required=True)
    ws_link.add_argument("--audience", required=True)
    ws_link.add_argument("--context", default="{}")
    ws_link.add_argument("--if-match")

    ws_unlink = ws_sub.add_parser("unlink")
    ws_unlink.add_argument("--workspace-id", required=True)
    ws_unlink.add_argument("--issuer", required=True)
    ws_unlink.add_argument("--audience", required=True)
    ws_unlink.add_argument("--context", default="{}")
    ws_unlink.add_argument("--if-match")

    args = parser.parse_args()

    client = AuthBridgeClient(base_url=args.base_url, admin_key=args.admin_key, entity_key=args.api_key)

    try:
        if args.cmd == "token":
            if args.token_cmd == "issue":
                claims = json.loads(args.claims) if args.claims else {}
                token = client.issue_token(iss=args.iss, aud=args.aud, sub=args.sub, claims=claims)
                print(token)
            elif args.token_cmd == "verify":
                res = client.verify_token(args.token)
                _print_json(res)

        elif args.cmd == "discovery":
            if args.disc_cmd == "v1":
                _print_json(client.discovery_v1(args.service_id))
            elif args.disc_cmd == "v2":
                _print_json(client.discovery_v2(args.service_id))
            elif args.disc_cmd == "callers":
                _print_json(client.callers(args.service_id))

        elif args.cmd == "system":
            if args.sys_cmd == "jwks":
                _print_json(client.system_jwks())
            elif args.sys_cmd == "rotate-keys":
                _print_json(client.rotate_keys())
            elif args.sys_cmd == "rotate-admin-keys":
                _print_json(client.rotate_admin_keys_from_env())
            elif args.sys_cmd == "diagnostics":
                _print_json(client.diagnostics())

        elif args.cmd == "services":
            if args.svc_cmd == "create":
                info = json.loads(args.info) if args.info else {}
                content = json.loads(args.content) if args.content else {}
                _print_json(client.create_service(args.id, args.name, args.type, api_key=args.api_key, info=info, content=content))
            elif args.svc_cmd == "list":
                _print_json(client._request("GET", "/api/v1/services", admin=True))
            elif args.svc_cmd == "get":
                _print_json(client.get_service(args.id))
            elif args.svc_cmd == "version":
                print(client.get_service_version(args.id))
            elif args.svc_cmd == "rekey":
                _print_json(client.rekey_service(args.id, if_match=args.if_match))
            elif args.svc_cmd == "update-content":
                content = json.loads(args.content)
                _print_json(client.update_service_content(args.id, content, if_match=args.if_match))
            elif args.svc_cmd == "update-info":
                info = json.loads(args.info)
                _print_json(client.update_service_info(args.id, info, if_match=args.if_match))
            elif args.svc_cmd == "delete":
                _print_json(client.delete_service(args.id))

        elif args.cmd == "workspaces":
            if args.ws_cmd == "create":
                info = json.loads(args.info) if args.info else {}
                content = json.loads(args.content) if args.content else {}
                _print_json(client.create_workspace(args.id, args.name, api_key=args.api_key, info=info, content=content))
            elif args.ws_cmd == "list":
                _print_json(client._request("GET", "/api/v1/workspaces", admin=True))
            elif args.ws_cmd == "get":
                _print_json(client.get_workspace(args.id))
            elif args.ws_cmd == "version":
                print(client.get_workspace_version(args.id))
            elif args.ws_cmd == "rekey":
                _print_json(client.rekey_workspace(args.id, if_match=args.if_match))
            elif args.ws_cmd == "update-content":
                content = json.loads(args.content)
                _print_json(client.update_workspace_content(args.id, content, if_match=args.if_match))
            elif args.ws_cmd == "update-info":
                info = json.loads(args.info)
                _print_json(client.update_workspace_info(args.id, info, if_match=args.if_match))
            elif args.ws_cmd == "link":
                context = json.loads(args.context) if args.context else {}
                _print_json(client.link_service(args.workspace_id, args.issuer, args.audience, context=context, if_match=args.if_match))
            elif args.ws_cmd == "unlink":
                context = json.loads(args.context) if args.context else {}
                _print_json(client.unlink_service(args.workspace_id, args.issuer, args.audience, context=context, if_match=args.if_match))

    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    cli()
