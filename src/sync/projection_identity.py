"""Stable Google Calendar materialization identity for Notica projections."""

from __future__ import annotations

import hashlib
import json
import uuid


PROJECTION_CONTRACT_VERSION = "1"
_EVENT_NAMESPACE = uuid.UUID("64c2406d-28b8-4a1b-8ac0-0dcb0f86af7d")

_PRIVATE_CONTRACT = "noticaContract"
_PRIVATE_OWNER = "noticaOwner"
_PRIVATE_SOURCE = "noticaSource"
_PRIVATE_MAPPING = "noticaMapping"
_PRIVATE_TASK = "noticaTask"
_PRIVATE_TARGET = "noticaTarget"


class ProjectionIdentityError(ValueError):
    """Raised when a provider event cannot be proven to belong to a projection."""


def _require_non_blank(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProjectionIdentityError(f"{label} must be a non-empty string.")
    return value.strip()


def _opaque_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


def normalize_notion_page_id(page_id: object) -> str:
    raw = _require_non_blank(page_id, "Notion page id")
    try:
        return uuid.UUID(raw).hex
    except ValueError as exc:
        raise ProjectionIdentityError("Notion page id must be a UUID.") from exc


def build_projection_identity(user_setting: dict, notion_page_id: object) -> dict:
    owner = _require_non_blank(user_setting.get("owner_user_uuid"), "owner_user_uuid")
    source_id = _require_non_blank(user_setting.get("source_id"), "source_id")
    mapping_id = _require_non_blank(user_setting.get("mapping_id"), "mapping_id")
    calendar_id = _require_non_blank(user_setting.get("calendar_id"), "calendar_id")
    task_id = normalize_notion_page_id(notion_page_id)

    canonical = json.dumps(
        [owner, source_id, mapping_id, task_id, calendar_id],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    # Hex characters are a valid subset of Calendar's base32hex event-ID alphabet.
    event_id = "n" + uuid.uuid5(_EVENT_NAMESPACE, canonical).hex

    private = {
        _PRIVATE_CONTRACT: PROJECTION_CONTRACT_VERSION,
        _PRIVATE_OWNER: _opaque_key(owner),
        _PRIVATE_SOURCE: source_id,
        _PRIVATE_MAPPING: mapping_id,
        _PRIVATE_TASK: task_id,
        _PRIVATE_TARGET: _opaque_key(calendar_id),
    }
    return {
        "event_id": event_id,
        "task_id": task_id,
        "calendar_id": calendar_id,
        "private": private,
    }


def assert_projection_ownership(event: dict, projection: dict) -> None:
    if not isinstance(event, dict):
        raise ProjectionIdentityError("Google Calendar event payload is invalid.")

    expected_event_id = _require_non_blank(projection.get("event_id"), "projection.event_id")
    if event.get("id") != expected_event_id:
        raise ProjectionIdentityError("Google Calendar event ID does not match the expected projection.")

    extended = event.get("extendedProperties")
    private = extended.get("private") if isinstance(extended, dict) else None
    if not isinstance(private, dict):
        raise ProjectionIdentityError("Google Calendar event has no Notica ownership metadata.")

    expected_private = projection.get("private")
    if not isinstance(expected_private, dict):
        raise ProjectionIdentityError("Projection ownership metadata is invalid.")

    for key, expected_value in expected_private.items():
        if private.get(key) != expected_value:
            raise ProjectionIdentityError(
                f"Google Calendar event ownership metadata mismatch for {key}."
            )


__all__ = [
    "PROJECTION_CONTRACT_VERSION",
    "ProjectionIdentityError",
    "assert_projection_ownership",
    "build_projection_identity",
    "normalize_notion_page_id",
]
