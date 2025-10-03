#!/usr/bin/env python3
"""
example-client.py

Provisioning (Admin) + Runtime (Service) example:
  - create workspace "kladna-soft"
  - create services "supertable" and "reflection"
  - link reflection -> supertable with DB context
  - let "reflection" discover its linked services

ENV:
  AUTHBRIDGE_BASE_URL   (default: http://localhost:8000)
  AUTHBRIDGE_ADMIN_KEY  (required for admin ops)
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict

try:
    from app.client import AdminClient, ServiceClient
except Exception:
    print("ERROR: Could not import AdminClient/ServiceClient from app.client. Run from project root.", file=sys.stderr)
    raise

WS_ID = "kladna-soft"
WS_NAME = "Kladna Soft"

SVC_REFLECTION = {"id": "reflection", "name": "Reflection", "type": "reflection"}
SVC_SUPERTABLE = {"id": "supertable", "name": "SuperTable", "type": "supertable"}

LINK_CONTEXT: Dict[str, Any] = {
    "db": {
        "engine": "postgresql",
        "host": "db.local",
        "port": 5432,
        "database": "warehouse",
        "user": "reflex",
        "options": {"sslmode": "prefer"},
    },
    "purpose": "reflection->supertable metadata+query access",
}


def _pp(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True)


def ensure_workspace(admin: AdminClient, ws_id: str, ws_name: str) -> Dict[str, Any]:
    try:
        res = admin.create_workspace(ws_id, ws_name)
        print(f"[OK] Workspace created: {ws_id}")
        return res
    except RuntimeError as e:
        if "ALREADY_EXISTS" in str(e) or "400" in str(e):
            ws = admin.get_workspace(ws_id)
            print(f"[SKIP] Workspace exists: {ws_id}")
            return ws
        raise


def ensure_service(admin: AdminClient, svc: Dict[str, str]) -> Dict[str, Any]:
    sid, name, typ = svc["id"], svc["name"], svc["type"]
    try:
        res = admin.create_service(sid, name, typ)
        print(f"[OK] Service created: {sid} ({typ})")
        return res
    except RuntimeError as e:
        if "ALREADY_EXISTS" in str(e) or "400" in str(e):
            payload = admin.get_service(sid)
            print(f"[SKIP] Service exists: {sid}")
            return payload
        raise


def ensure_link(admin: AdminClient, ws_id: str, issuer: str, audience: str, context: Dict[str, Any]) -> None:
    try:
        admin.link_service(ws_id, issuer, audience, context=context)
        print(f"[OK] Linked {issuer} -> {audience} in workspace {ws_id}")
    except RuntimeError as e:
        if "ALREADY_LINKED" in str(e):
            print(f"[SKIP] Link already present: {issuer} -> {audience}")
        else:
            raise


def run() -> None:
    base_url = os.getenv("AUTHBRIDGE_BASE_URL", "http://localhost:8000")
    admin_key = os.getenv("AUTHBRIDGE_ADMIN_KEY")
    if not admin_key:
        print("ERROR: AUTHBRIDGE_ADMIN_KEY missing from environment.", file=sys.stderr)
        sys.exit(2)

    # Sysadmin client for provisioning
    admin = AdminClient(base_url=base_url, admin_key=admin_key)

    # 1) Ensure workspace + services
    ensure_workspace(admin, WS_ID, WS_NAME)
    ref = ensure_service(admin, SVC_REFLECTION)
    st = ensure_service(admin, SVC_SUPERTABLE)

    # Extract service API keys (admin.get_service returns the service dict)
    reflection_api_key = (ref.get("api_key") or (ref.get("service") or {}).get("api_key"))
    supertable_api_key = (st.get("api_key") or (st.get("service") or {}).get("api_key"))

    if not reflection_api_key:
        print("ERROR: reflection api_key not found in response.", file=sys.stderr)
        sys.exit(3)

    # 2) Link reflection -> supertable with context
    ensure_link(admin, WS_ID, issuer=SVC_REFLECTION["id"], audience=SVC_SUPERTABLE["id"], context=LINK_CONTEXT)

    # 3) Runtime actions as 'reflection'
    reflection = ServiceClient(base_url=base_url, entity_key=reflection_api_key)
    discovery = reflection.discovery(SVC_REFLECTION["id"])
    print("\n=== discovery (reflection) ===")
    print(_pp(discovery))

    # Optional: check who can call supertable (requires supertable or admin privileges)
    if supertable_api_key:
        supertable = ServiceClient(base_url=base_url, entity_key=supertable_api_key)
        callers = supertable.callers(SVC_SUPERTABLE["id"])
        print("\n=== callers (who can call supertable) ===")
        print(_pp(callers))


if __name__ == "__main__":
    run()
