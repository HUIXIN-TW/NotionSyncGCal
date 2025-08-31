from __future__ import annotations

import json
import logging
from typing import Any, Dict


import sys


def get_logger(name: str) -> logging.Logger:
    """Get a logger that always logs to stdout with a simple formatter (for Lambda/CloudWatch)."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def log_json(logger: logging.Logger, payload: Dict[str, Any], level: int = logging.INFO) -> None:
    """Emit a structured JSON log line."""
    logger.log(level, json.dumps(payload))


__all__ = ["get_logger", "log_json"]
