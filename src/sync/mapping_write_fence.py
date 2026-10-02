from decimal import Decimal

from utils.dynamodb_utils import (
    get_mapping_domain_calendar_mapping,
    get_mapping_domain_task_source,
)


class MappingWriteFenceError(RuntimeError):
    """Raised when the loaded route is no longer safe for a Google provider write."""

    def __init__(self, reason: str):
        super().__init__("Google provider write blocked by stale mapping-domain state.")
        self.reason = reason


def _require_non_empty_string(value, reason):
    if not isinstance(value, str) or not value.strip():
        raise MappingWriteFenceError(reason)
    return value.strip()


def _require_version(value, reason):
    if isinstance(value, bool):
        raise MappingWriteFenceError(reason)
    if isinstance(value, Decimal):
        if value != value.to_integral_value():
            raise MappingWriteFenceError(reason)
        value = int(value)
    if not isinstance(value, int) or value < 1:
        raise MappingWriteFenceError(reason)
    return value


def _route_snapshot(user_setting, calendar_name):
    routes = user_setting.get("gcal_route_by_name")
    if not isinstance(routes, dict):
        raise MappingWriteFenceError("route_snapshot_missing")

    route = routes.get(calendar_name)
    if not isinstance(route, dict):
        raise MappingWriteFenceError("mapping_snapshot_missing")

    return {
        "mapping_id": _require_non_empty_string(
            route.get("mapping_id"),
            "mapping_snapshot_invalid",
        ),
        "mapping_version": _require_version(
            route.get("mapping_version"),
            "mapping_snapshot_invalid",
        ),
        "calendar_id": _require_non_empty_string(
            route.get("calendar_id"),
            "mapping_snapshot_invalid",
        ),
    }


def assert_current_google_write_route(user_setting, calendar_name, calendar_id):
    """Fail closed when a cloud mapping route changed after the sync snapshot was loaded."""

    if user_setting.get("mapping_domain_mode") != "cloud":
        return

    owner_user_uuid = _require_non_empty_string(
        user_setting.get("owner_user_uuid"),
        "owner_snapshot_invalid",
    )
    source_id = _require_non_empty_string(
        user_setting.get("source_id"),
        "source_snapshot_invalid",
    )
    source_version = _require_version(
        user_setting.get("source_version"),
        "source_snapshot_invalid",
    )
    calendar_name = _require_non_empty_string(
        calendar_name,
        "mapping_snapshot_invalid",
    )
    calendar_id = _require_non_empty_string(
        calendar_id,
        "calendar_target_invalid",
    )
    route = _route_snapshot(user_setting, calendar_name)

    if route["calendar_id"] != calendar_id:
        raise MappingWriteFenceError("calendar_target_changed")

    try:
        source = get_mapping_domain_task_source(owner_user_uuid, source_id)
    except ValueError as exc:
        raise MappingWriteFenceError("source_missing") from exc

    if source.get("ownerUserUuid") != owner_user_uuid:
        raise MappingWriteFenceError("source_owner_mismatch")
    if source.get("id") != source_id:
        raise MappingWriteFenceError("source_identity_mismatch")
    if source.get("lifecycle") != "active":
        raise MappingWriteFenceError("source_inactive")
    if _require_version(source.get("version"), "source_version_invalid") != source_version:
        raise MappingWriteFenceError("source_version_changed")

    try:
        mapping = get_mapping_domain_calendar_mapping(
            owner_user_uuid,
            route["mapping_id"],
        )
    except ValueError as exc:
        raise MappingWriteFenceError("mapping_missing") from exc

    if mapping.get("ownerUserUuid") != owner_user_uuid:
        raise MappingWriteFenceError("mapping_owner_mismatch")
    if mapping.get("id") != route["mapping_id"]:
        raise MappingWriteFenceError("mapping_identity_mismatch")
    if mapping.get("sourceId") != source_id:
        raise MappingWriteFenceError("mapping_source_changed")
    if mapping.get("lifecycle") != "active":
        raise MappingWriteFenceError("mapping_inactive")
    if _require_version(mapping.get("version"), "mapping_version_invalid") != route["mapping_version"]:
        raise MappingWriteFenceError("mapping_version_changed")
    if mapping.get("calendarId") != calendar_id:
        raise MappingWriteFenceError("calendar_target_changed")
