from __future__ import annotations

import json
import logging
from typing import Any, Dict


def get_logger(name: str) -> logging.Logger:
    """Get a logger pre-configured to INFO level if no handlers exist."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logging.basicConfig(level=logging.INFO)
    return logger


def log_json(logger: logging.Logger, payload: Dict[str, Any], level: int = logging.INFO) -> None:
    """Emit a structured JSON log line."""
    logger.log(level, json.dumps(payload))


__all__ = ["get_logger", "log_json"]
