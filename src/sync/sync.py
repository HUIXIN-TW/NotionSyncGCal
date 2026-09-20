import re
from datetime import datetime, timezone

from notion.notion_properties import get_checkbox
from sync.contracts import (
    StaleExecutionError,
    build_capacity_limited_result,
    build_sync_error,
    build_sync_result,
)
from sync.projection_identity import (
    ProjectionIdentityError,
    build_projection_identity,
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


def project_notion_to_google_calendar(
    user_setting: dict,
    notion_service,
    google_service,
):
    """Project authoritative Notion tasks into one explicitly mapped Calendar."""
    trigger_sync_time = get_current_time_in_iso_format()
    source_id = user_setting["source_id"]
    mapping_id = user_setting["mapping_id"]
    page_property = user_setting["page_property"]

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
        "mapping_id": mapping_id,
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
    for notion_task in notion_task_list:
        notion_task_page_id = notion_task.get("id")
        action = None
        projection = None
        try:
            projection = build_projection_identity(
                user_setting,
                notion_task_page_id,
            )

            if _task_is_marked_deleted(notion_task, page_property):
                action = "delete_gcal"
                google_service.delete_projection(projection)
                continue

            action = "upsert_gcal"
            google_service.upsert_projection(notion_task, projection)
        except StaleExecutionError as exc:
            sync_errors.append(
                build_sync_error(
                    action,
                    "stale_execution_snapshot",
                    error_message="Sync configuration changed before the provider write.",
                    notion_task_id=notion_task_page_id,
                    gcal_event_id=(projection or {}).get("event_id"),
                    retriable=False,
                    debug_detail=build_debug_exception_detail(exc),
                )
            )
            logger.warning(
                "Stopped stale sync execution before provider mutation: source_id=%s task_id=%s",
                source_id,
                notion_task_page_id,
            )
            break
        except ProjectionIdentityError as exc:
            sync_errors.append(
                build_sync_error(
                    action,
                    "projection_identity_mismatch",
                    error_message="Provider materialization ownership could not be verified.",
                    notion_task_id=notion_task_page_id,
                    gcal_event_id=(projection or {}).get("event_id"),
                    retriable=False,
                    debug_detail=build_debug_exception_detail(exc),
                )
            )
            logger.warning(
                "Projection identity verification failed: source_id=%s task_id=%s",
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
                "Provider projection failed action=%s source_id=%s notion_task_id=%s",
                action,
                source_id,
                notion_task_page_id,
            )

    return build_sync_result(
        200,
        "sync_success",
        {
            "summary": sync_summary,
            "trigger_time": trigger_sync_time,
            "errors": sync_errors,
        },
    )


def synchronize_notion_and_google_calendar(
    user_setting: dict,
    notion_service,
    google_service,
    compare_time=True,  # noqa: ARG001
    should_update_notion_tasks=False,  # noqa: ARG001
    should_update_google_events=True,
):
    """Compatibility wrapper. The implementation is intentionally one-way."""
    if not should_update_google_events:
        return build_sync_result(
            409,
            "sync_error",
            {
                "error_code": "google_to_notion_sync_not_supported",
                "retriable": False,
            },
        )
    return project_notion_to_google_calendar(
        user_setting=user_setting,
        notion_service=notion_service,
        google_service=google_service,
    )


def force_update_notion_tasks_by_google_event_and_ignore_time(
    user_setting,  # noqa: ARG001
    notion_service,  # noqa: ARG001
    google_service,  # noqa: ARG001
):
    """Legacy reverse-sync entry point retained only to fail closed."""
    return build_sync_result(
        409,
        "sync_error",
        {
            "error_code": "google_to_notion_sync_not_supported",
            "retriable": False,
        },
    )


def force_update_google_event_by_notion_task_and_ignore_time(
    user_setting,
    notion_service,
    google_service,
):
    return project_notion_to_google_calendar(
        user_setting=user_setting,
        notion_service=notion_service,
        google_service=google_service,
    )
