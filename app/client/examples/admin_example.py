#!/usr/bin/env python3
# admin_example.py
"""
Auth-Bridge — Admin example (provisioning)

Goal:
  - Delete-if-exists, then (re)create the workspace and both services.
  - Link Reflection (issuer) -> SuperTable (audience) in the workspace.
  - Rotate RSA keys (optional) to demonstrate system ops.

Why this version?
  Some servers return 400 ALREADY_EXISTS if the pre-check GET fails or races.
  This script now ALWAYS attempts a best-effort DELETE first (no prior GET),
  swallowing 404/NOT_FOUND, then creates fresh resources.

.env requirements:
  AUTHBRIDGE_BASE_URL=http://localhost:8000
  AUTHBRIDGE_API_KEYS=["your-admin-key"]   # or comma-separated string

Run:
  python admin_example.py
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from dotenv import load_dotenv

load_dotenv()

from app.client.admin_client import AdminClient


# ─────────────────────────── helpers ───────────────────────────

def _print_title(title: str) -> None:
    bar = "─" * max(10, len(title))
    print(f"\n{bar}\n{title}\n{bar}")


def _safe_get(dct: Dict[str, Any], key: str, default: Any = None) -> Any:
    try:
        return dct.get(key, default)
    except Exception:
        return default


def _best_effort_delete(callable_delete, resource_id: str, label: str) -> None:
    """
    Call the provided delete function and swallow 'not found' errors.
    Any other error will be printed but not raised (best-effort semantics).
    """
    _print_title(f"Deleting existing {label} '{resource_id}' (best-effort)")
    try:
        callable_delete(resource_id)
        print({"detail": f"{label} deleted", "id": resource_id})
    except RuntimeError as e:
        # The AdminClient wraps HTTP errors as RuntimeError with a JSON body.
        # If it's a NOT_FOUND, ignore. Otherwise, print the error and continue.
        msg = str(e)
        try:
            # Try to parse the trailing JSON-ish part for structured detail
            detail_start = msg.find("{")
            detail = json.loads(msg[detail_start:]) if detail_start != -1 else {}
        except Exception:
            detail = {}

        error_code = (detail.get("detail") or {}).get("error_code")
        status = detail.get("status")

        if error_code in {"NOT_FOUND"} or status == 404:
            print({"detail": f"{label} not found (nothing to delete)", "id": resource_id})
        else:
            print({"warning": f"Best-effort delete failed but continuing", "id": resource_id, "error": msg})


def recreate_workspace(client: AdminClient, workspace_id: str, name: str) -> Dict[str, Any]:
    # Always try delete first (ignore not-found)
    _best_effort_delete(client.delete_workspace, workspace_id, "workspace")

    # Create fresh
    _print_title(f"Creating workspace '{workspace_id}'")
    ws = client.create_workspace(workspace_id, name=name)
    print(ws)
    return ws


def recreate_service(client: AdminClient, service_id: str, name: str, type_: str) -> Dict[str, Any]:
    # Always try delete first (ignore not-found)
    _best_effort_delete(client.delete_service, service_id, "service")

    # Create fresh
    _print_title(f"Creating service '{service_id}' (type={type_})")
    svc = client.create_service(service_id, name=name, type_=type_)
    print(svc)
    return svc


def ensure_link(
    client: AdminClient,
    workspace_id: str,
    issuer_id: str,
    audience_id: str,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    _print_title(f"Linking services: {issuer_id} ➜ {audience_id} in {workspace_id}")
    link = client.link_service(
        workspace_id=workspace_id,
        issuer_id=issuer_id,
        audience_id=audience_id,
        context=context or {},
    )
    print(link)
    return link


# ─────────────────────────── main ───────────────────────────

def main() -> None:
    base_url = os.getenv("AUTHBRIDGE_BASE_URL", "http://localhost:8000")
    client = AdminClient(base_url=base_url)

    # IDs (use prefixed examples to avoid clashes with real ones)
    workspace_id = "example-workspace-kladna"
    supertable_id = "example-service-supertable"
    reflection_id = "example-service-reflection"

    # 1) Recreate workspace (delete-if-exists, then create)
    ws = recreate_workspace(client, workspace_id, name="Kladna Soft Workspace")

    # 2) Recreate services (delete-if-exists, then create)
    #    Valid types enforced by server: [unknown, reflection, supertable, mirage, ai, bi, email_api]
    svc1 = recreate_service(client, supertable_id, name="SuperTable", type_="supertable")
    svc2 = recreate_service(client, reflection_id, name="Reflection", type_="reflection")

    # 3) Link services (Reflection ➜ SuperTable)
    ensure_link(
        client,
        workspace_id=workspace_id,
        issuer_id=reflection_id,     # who issues tokens
        audience_id=supertable_id,   # who receives tokens
        context={"db": "postgres://localhost:5432/mydb"},
    )

    # 4) Optional: system operation (rotate RSA keys)
    _print_title("Rotate RSA keys…")
    print(client.rotate_rsa_keys())

    # 5) Summary
    _print_title("Summary")
    print(
        {
            "workspace": {"id": _safe_get(ws, "id"), "name": _safe_get(ws, "name")},
            "supertable": {"id": _safe_get(svc1, "id"), "type": _safe_get(svc1, "type")},
            "reflection": {"id": _safe_get(svc2, "id"), "type": _safe_get(svc2, "type")},
            "link": f"{reflection_id} -> {supertable_id} @ {workspace_id}",
        }
    )


if __name__ == "__main__":
    main()
