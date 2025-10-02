from __future__ import annotations

import logging
import sys
from typing import Optional


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if root.handlers:
        for h in list(root.handlers):
            root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    fmt = (
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s "
        "[%(filename)s:%(lineno)d]"
    )
    handler.setFormatter(logging.Formatter(fmt))
    root.addHandler(handler)

    root.setLevel(level.upper())
    logging.getLogger("uvicorn").setLevel(level.upper())
    logging.getLogger("uvicorn.access").setLevel(level.upper())
    logging.getLogger("uvicorn.error").setLevel(level.upper())


def get_logger(name: Optional[str] = None) -> logging.Logger:
    return logging.getLogger(name or "auth-bridge")
