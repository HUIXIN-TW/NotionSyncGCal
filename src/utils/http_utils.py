from __future__ import annotations

import json
from typing import Any, Dict, Optional


def get_header(headers: Optional[Dict[str, str]], key: str, default: Optional[str] = None) -> Optional[str]:
    """Case-insensitive header lookup. Returns default when headers is falsy."""
    if not headers:
        return default
    lower = {k.lower(): v for k, v in headers.items()}
    return lower.get(key.lower(), default)


def format_json_response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    """Standard API Gateway style JSON response."""
    return {"statusCode": status_code, "body": json.dumps(body)}


__all__ = ["get_header", "format_json_response"]
