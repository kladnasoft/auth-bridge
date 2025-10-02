import json
import os
from enum import Enum
from pathlib import Path


def load_service_types() -> list[str]:
    """
    Load service types dynamically from ENV, JSON file, or fallback.

    Priority:
      1. ENV variable AUTHBRIDGE_SERVICE_TYPES (comma-separated)
      2. JSON file `service_types.json` in project root
      3. Fallback default list
    """
    # --- check ENV ---
    env_val = os.getenv("AUTHBRIDGE_SERVICE_TYPES")
    if env_val:
        return [v.strip().lower() for v in env_val.split(",") if v.strip()]

    # --- check JSON file ---
    json_file = Path(__file__).resolve().parent.parent / "service_types.json"
    if json_file.exists():
        with open(json_file, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                if isinstance(data, list):
                    return [str(v).lower() for v in data if v]
            except Exception:
                pass  # fall back if file invalid

    # --- fallback ---
    return ["unknown", "reflection", "supertable", "mirage", "ai", "bi", "email_api"]


def build_service_type_enum() -> Enum:
    """
    Dynamically build the ServiceType Enum.
    """
    types = load_service_types()
    return Enum("ServiceType", {t.upper(): t for t in types})
