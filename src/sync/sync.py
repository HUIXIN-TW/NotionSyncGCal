import re
from datetime import datetime, timezone

from notion.notion_properties import get_checkbox, get_select
from sync.contracts import (
    StaleExecutionError,
    build_capacity_limited_result,
    build_sync_error,
    build_sync_result,
)
from sync.projection_identity import (
    ProjectionIdentityError,
    build_projection_identity,
    normalize_notion_page_id,
)
from utils.logging_utils import build_debug_exception_detail, get_logger


logger = get_logger(__name__)

SYNC_TASK_LIMIT = 250
SAFE_SYNC_FAILURE_MESSAGE = "Sync failed. See Lambda logs with aws_request_id for details."


def get_current_time_in_iso_format():
    current_time = datetime.now(timezone.utc)
    formatted_current_time = current_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return formatted_current_time[:-3] + "Z"


def _exception_error_code(exc: Exception) -> str:
    name = type(exc).__name__
    code = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    return code or "unexpected_sync_error"


def _task_is_marked_deleted(notion_task: dict, page_property: dict) -> bool:
    delete_property_id = page_property.get("Delete_Notion_Name")
    if not delete_property_id:
        return False
    return bool(
        get_checkbox(
            notion_task.get("properties", {}),
            delete_property_id,
        )
    )


def _mapping_setting(source_setting: dict, mapping: dict) -> dict:
    return {
        **source_setting,
        "mapping_id": mapping["mapping_id"],
        "mapping_version": mapping["mapping_version"],
        "calendar_id": mapping["calendar_id"],
        "routing": mapping["routing"],
    }


def _resolve_task_mapping(notion_task: dict, source_setting: dict) -> dict | None:
    mappings = source_setting["calendar_mappings"]
    mode = mappings[0]["routing"]["mode"]
    if mode == "all":
        return mappings[0]

    calendar_property_id = source_setting["page_property"].get(
        "GCal_Name_Notion_Name"
    )
    if not calendar_property_id:
        return None

    route_value = get_select(
        notion_task.get("properties", {}),
        calendar_property_id,
    )
    if not route_value:
        return None

    for mapping in mappings:
        if mapping["routing"]["value"] == route_value:
            return mapping
    return None


def _route_value(notion_task: dict, source_setting: dict) -> str | None:
    calendar_property_id = source_setting["page_property"].get(
        "GCal_Name_Notion_Name"
    )
    if not calendar_property_id:
        return None
    return get_select(
        notion_task.get("properties", {}),
        calendar_property_id,
    )


def project_notion_to_google_calendar(
    user_setting: dict,
    notion_service,
    google_services: dict,
):
    """Project one authoritative Notion source through its explicit Calendar routes."""
    trigger_sync_time = get_current_time_in_iso_format()
    source_id = user_setting["source_id"]
    page_property = user_setting["page_property"]
    mappings = user_setting["calendar_mappings"]

    try:
        notion_config, notion_task_list = notion_service.get_notion_task()
    except Exception:
        logger.exception("Failed to load authoritative Notion tasks")
        return build_sync_result(
            500,
            "sync_error",
            {
                "error_code": "notion_task_load_failed",
                "error_message": SAFE_SYNC_FAILURE_MESSAGE,
            },
        )

    task_count = len(notion_task_list)
    sync_summary = {
        "source_id": source_id,
        "mapping_count": len(mappings),
        "mapping_ids": [mapping["mapping_id"] for mapping in mappings],
        "notion_task_count": task_count,
        "notion_config": notion_config,
    }

    if task_count > SYNC_TASK_LIMIT:
        logger.warning(
            "Sync input volume exceeds limit=%s; source_id=%s task_count=%s. "
            "Skipping run intentionally to avoid an oversized sync job.",
            SYNC_TASK_LIMIT,
            source_id,
            task_count,
        )
        return build_capacity_limited_result(
            sync_task_limit=SYNC_TASK_LIMIT,
            trigger_sync_time=trigger_sync_time,
            event_count=0,
            task_count=task_count,
        )

    sync_errors = []
    current_task_ids_by_mapping = {
        mapping["mapping_id"]: set() for mapping in mappings
    }
    unresolved_task_ids = set()
    stale_execution = False

    for notion_task in notion_task_list:
        notion_task_page_id = notion_task.get("id")
        action = None
        projection = None

        try:
            normalized_task_id = normalize_notion_page_id(
                notion_task_page_id
            )

            if _task_is_marked_deleted(notion_task, page_property):
                action = "delete_gcal"
                for mapping in mappings:
                    mapping_setting = _mapping_setting(
                        user_setting,
                        mapping,
                    )
                    projection = build_projection_identity(
                        mapping_setting,
                        notion_task_page_id,
                    )
                    google_services[
                        mapping["mapping_id"]
                    ].delete_projection(projection)
                continue

            mapping = _resolve_task_mapping(notion_task, user_setting)
            if mapping is None:
                unresolved_task_ids.add(normalized_task_id)
                route_value = _route_value(
                    notion_task,
                    user_setting,
                )
                sync_errors.append(
                    build_sync_error(
                        "route_gcal",
                        "calendar_route_unresolved",
                        error_message=(
                            "Notion task Calendar routing is blank or does not "
                            "match an active Calendar mapping."
                        ),
                        notion_task_id=notion_task_page_id,
                        retriable=False,
                    )
                )
                logger.warning(
                    "Skipped unresolved Calendar route: source_id=%s task_id=%s route=%r",
                    source_id,
                    notion_task_page_id,
                    route_value,
                )
                continue

            mapping_id = mapping["mapping_id"]
            mapping_setting = _mapping_setting(
                user_setting,
                mapping,
            )
            projection = build_projection_identity(
                mapping_setting,
                notion_task_page_id,
            )
            current_task_ids_by_mapping[mapping_id].add(
                projection["task_id"]
            )

            action = "upsert_gcal"
            google_services[mapping_id].upsert_projection(
                notion_task,
                projection,
            )
        except StaleExecutionError as exc:
            sync_errors.append(
                build_sync_error(
                    action,
                    "stale_execution_snapshot",
                    error_message=(
                        "Sync configuration changed before the provider write."
                    ),
                    notion_task_id=notion_task_page_id,
                    gcal_event_id=(projection or {}).get("event_id"),
                    retriable=False,
                    debug_detail=build_debug_exception_detail(exc),
                )
            )
            logger.warning(
                "Stopped stale sync execution before provider mutation: "
                "source_id=%s task_id=%s",
                source_id,
                notion_task_page_id,
            )
            stale_execution = True
            break
        except ProjectionIdentityError as exc:
            sync_errors.append(
                build_sync_error(
                    action,
                    "projection_identity_mismatch",
                    error_message=(
                        "Provider materialization ownership could not be verified."
                    ),
                    notion_task_id=notion_task_page_id,
                    gcal_event_id=(projection or {}).get("event_id"),
                    retriable=False,
                    debug_detail=build_debug_exception_detail(exc),
                )
            )
            logger.warning(
                "Projection identity verification failed: "
                "source_id=%s task_id=%s",
                source_id,
                notion_task_page_id,
            )
        except Exception as exc:
            sync_errors.append(
                build_sync_error(
                    action,
                    _exception_error_code(exc),
                    error_message=SAFE_SYNC_FAILURE_MESSAGE,
                    notion_task_id=notion_task_page_id,
                    gcal_event_id=(projection or {}).get("event_id"),
                    retriable=True,
                    debug_detail=build_debug_exception_detail(exc),
                )
            )
            logger.exception(
                "Provider projection failed action=%s source_id=%s "
                "notion_task_id=%s",
                action,
                source_id,
                notion_task_page_id,
            )

    if not stale_execution:
        owned_event_count = 0
        for mapping in mappings:
            mapping_id = mapping["mapping_id"]
            google_service = google_services[mapping_id]
            mapping_setting = _mapping_setting(
                user_setting,
                mapping,
            )
            try:
                owned_events = google_service.get_gcal_event()
                owned_event_count += len(owned_events)
                for event in owned_events:
                    private = (
                        event.get("extendedProperties") or {}
                    ).get("private")
                    provider_task_id = (
                        private.get("noticaTask")
                        if isinstance(private, dict)
                        else None
                    )
                    if not provider_task_id:
                        sync_errors.append(
                            build_sync_error(
                                "inspect_gcal_projection",
                                "projection_identity_mismatch",
                                error_message=(
                                    "Tagged provider event is missing complete "
                                    "Notica ownership metadata."
                                ),
                                gcal_event_id=event.get("id"),
                                retriable=False,
                            )
                        )
                        continue

                    try:
                        normalized_task_id = normalize_notion_page_id(
                            provider_task_id
                        )
                        if (
                            normalized_task_id
                            in current_task_ids_by_mapping[mapping_id]
                            or normalized_task_id in unresolved_task_ids
                        ):
                            continue

                        orphan_projection = build_projection_identity(
                            mapping_setting,
                            normalized_task_id,
                        )
                        google_service.delete_projection(
                            orphan_projection
                        )
                    except StaleExecutionError as exc:
                        sync_errors.append(
                            build_sync_error(
                                "delete_orphan_gcal",
                                "stale_execution_snapshot",
                                error_message=(
                                    "Sync configuration changed before orphan "
                                    "reconciliation."
                                ),
                                notion_task_id=provider_task_id,
                                gcal_event_id=event.get("id"),
                                retriable=False,
                                debug_detail=(
                                    build_debug_exception_detail(exc)
                                ),
                            )
                        )
                        stale_execution = True
                        break
                    except ProjectionIdentityError as exc:
                        sync_errors.append(
                            build_sync_error(
                                "delete_orphan_gcal",
                                "projection_identity_mismatch",
                                error_message=(
                                    "Provider materialization ownership could "
                                    "not be verified."
                                ),
                                notion_task_id=provider_task_id,
                                gcal_event_id=event.get("id"),
                                retriable=False,
                                debug_detail=(
                                    build_debug_exception_detail(exc)
                                ),
                            )
                        )
                    except Exception as exc:
                        sync_errors.append(
                            build_sync_error(
                                "delete_orphan_gcal",
                                _exception_error_code(exc),
                                error_message=SAFE_SYNC_FAILURE_MESSAGE,
                                notion_task_id=provider_task_id,
                                gcal_event_id=event.get("id"),
                                retriable=True,
                                debug_detail=(
                                    build_debug_exception_detail(exc)
                                ),
                            )
                        )
                if stale_execution:
                    break
            except Exception as exc:
                sync_errors.append(
                    build_sync_error(
                        "list_gcal_projections",
                        _exception_error_code(exc),
                        error_message=SAFE_SYNC_FAILURE_MESSAGE,
                        retriable=True,
                        debug_detail=build_debug_exception_detail(exc),
                    )
                )

        sync_summary["owned_google_event_count"] = owned_event_count

    return build_sync_result(
        200,
        "sync_success",
        {
            "summary": sync_summary,
            "trigger_time": trigger_sync_time,
            "errors": sync_errors,
        },
    )
