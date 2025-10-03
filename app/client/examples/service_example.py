#!/usr/bin/env python3
# service_issue_token.py
"""
Auth-Bridge — Minimal token issuer (service role)

Goal:
  - Optionally discover the AUDIENCE service (to confirm the link exists)
  - Issue a token AS the ISSUER service for the AUDIENCE in WORKSPACE

IMPORTANT:
  The process *must authenticate as the ISSUER service*.
  => .env SERVICE_KEY MUST be the API key of ISSUER_ID.

.env required:
  AUTHBRIDGE_BASE_URL=http://localhost:8000
  SERVICE_KEY=<API key of the ISSUER service>

  # IDs (override as needed)
  ISSUER_ID=example-service-supertable
  AUDIENCE_ID=example-service-reflection
  WORKSPACE_ID=example-workspace-kladna

Run:
  python service_issue_token.py
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict

from dotenv import load_dotenv

load_dotenv()

from app.client.service_client import ServiceClient


def _title(s: str) -> None:
    bar = "─" * max(10, len(s))
    print(f"\n{bar}\n{s}\n{bar}")


def main() -> None:
    base_url = os.getenv("AUTHBRIDGE_BASE_URL", "http://localhost:8000")
    issuer_id = os.getenv("ISSUER_ID", "example-service-reflection")
    audience_id = os.getenv("AUDIENCE_ID", "example-service-supertable")
    workspace_id = os.getenv("WORKSPACE_ID", "example-workspace-kladna")

    if not os.getenv("SERVICE_KEY"):
        print("ERROR: SERVICE_KEY is not set. It must be the API key of ISSUER_ID.", file=sys.stderr)
        sys.exit(2)

    client = ServiceClient(base_url=base_url)

    # Optional: discover the audience (helps confirm linkage exists)
    _title(f"Discovery (issuer): {issuer_id}")
    try:
        disc: Dict[str, Any] = client.discovery(issuer_id)
        print(disc)
    except Exception as e:
        print(f"Discovery failed (non-fatal for issuing): {e}")

    # Issue token: iss=ISSUER_ID, aud=AUDIENCE_ID, sub=WORKSPACE_ID
    _title(f"Issue token ➜ iss={issuer_id} aud={audience_id} sub={workspace_id}")
    try:
        token: str = client.issue_token(service_id=issuer_id, aud=audience_id, sub=workspace_id)
        print("Access token (truncated):", token[:64] + "…")

        # Verify
        _title("Verify token")
        verification = client.verify_token(token)
        print(verification)
    except Exception as e:
        print(f"Issue/verify failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
