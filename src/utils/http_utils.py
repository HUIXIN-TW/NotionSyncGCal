from typing import Dict, Optional


def get_header(headers: Optional[Dict[str, str]], key: str, default: Optional[str] = None) -> Optional[str]:
    """Case-insensitive header lookup. Returns default when headers is falsy."""
    if not headers:
        return default
    lower = {k.lower(): v for k, v in headers.items()}
    return lower.get(key.lower(), default)


__all__ = ["get_header"]
