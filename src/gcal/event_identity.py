import base64
import hashlib
import struct


_EVENT_ID_DOMAIN = b"notica:gcal:event:v1"
_PRIVATE_SOURCE_ID_KEY = "noticaSourceId"
_PRIVATE_MAPPING_ID_KEY = "noticaMappingId"
_PRIVATE_MAPPING_VERSION_KEY = "noticaMappingVersion"


def _require_non_empty_string(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string.")
    return value.strip()


def _frame_component(value, label):
    encoded = _require_non_empty_string(value, label).encode("utf-8")
    return struct.pack(">I", len(encoded)) + encoded


def deterministic_google_event_id(source_id, notion_page_id):
    """Return a stable Google-compatible event ID for one Notion task."""
    framed = b"".join(
        (
            _EVENT_ID_DOMAIN,
            b"\x00",
            _frame_component(source_id, "source_id"),
            _frame_component(notion_page_id, "notion_page_id"),
        )
    )
    digest = hashlib.sha256(framed).digest()
    return base64.b32hexencode(digest).decode("ascii").lower().rstrip("=")


def build_google_private_metadata(source_id, mapping_id, mapping_version):
    """Build the minimum non-sensitive routing metadata stored on a Google event."""
    source_id = _require_non_empty_string(source_id, "source_id")
    mapping_id = _require_non_empty_string(mapping_id, "mapping_id")
    if isinstance(mapping_version, bool) or not isinstance(mapping_version, int) or mapping_version < 1:
        raise ValueError("mapping_version must be a positive integer.")

    return {
        _PRIVATE_SOURCE_ID_KEY: source_id,
        _PRIVATE_MAPPING_ID_KEY: mapping_id,
        _PRIVATE_MAPPING_VERSION_KEY: str(mapping_version),
    }
