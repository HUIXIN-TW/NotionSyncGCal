import re
from datetime import datetime, timezone
from dateutil.parser import isoparse
from gcal.event_identity import (
    build_google_private_metadata,
    deterministic_google_event_id,
)
from sync.contracts import (
    build_capacity_limited_result,
    build_sync_error,
    build_sync_result,
)
from sync.mapping_write_fence import (
    MappingWriteFenceError,
    assert_current_google_write_route,
)
from utils.logging_utils import build_debug_exception_detail, get_logger  # noqa: E402
from notion.notion_properties import get_checkbox, get_rich_text, get_select, get_title

# Configure logging
logger = get_logger(__name__)

# Cap sync volume to avoid unbounded processing for large datasets.
SYNC_TASK_LIMIT = 250
SAFE_SYNC_FAILURE_MESSAGE = "Sync failed. See Lambda logs with aws_request_id for details."


class SyncAbortError(Exception):
    """Raised when a fatal condition requires the entire sync to stop immediately."""

    pass


def compare_timezones(notion_time_str, google_time_str):
    # Parse the time strings into datetime objects
    notion_time = isoparse(notion_time_str)
    google_time = isoparse(google_time_str)

    notion_timezone = notion_time.tzinfo
    google_timezone = google_time.tzinfo
    logger.debug(f"Notion Timezone: {notion_timezone}, Google Calendar Timezone: {google_timezone}")
    if notion_timezone != google_timezone:
        raise SyncAbortError(f"Timezones are different: Notion {notion_timezone} and Google Calendar {google_timezone}")


def get_current_time_in_iso_format():
    """
    Returns the current UTC time in ISO 8601 format with milliseconds.
    Format: YYYY-MM-DDTHH:MM:SS.SSSZ
    """
    current_time = datetime.now(timezone.utc)
    formatted_current_time = current_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    # Trim the microseconds to milliseconds (3 decimal places)
    formatted_current_time = formatted_current_time[:-3] + "Z"
    return formatted_current_time


def remove_gcal_event_from_list(gcal_event_list, gcal_event, gcal_event_summary):
    if gcal_event not in gcal_event_list:
        return
    gcal_event_list.remove(gcal_event)
    logger.debug(
        f"Google Calendar: Event '{gcal_event_summary}' removed from the list, {len(gcal_event_list)} events remaining\n"  # noqa: E501
    )


def get_gcal_event_from_list(gcal_event_list, gcal_event_id):
    """Return the Google Calendar event with the given ID from the list."""
    for gcal_event in gcal_event_list:
        if gcal_event.get("id") == gcal_event_id:
            return gcal_event

    logger.debug(f"Google Calendar event '{gcal_event_id}' not found in the provided list")
    return None


def _configured_google_calendar_ids(user_setting):
    gcal_name_dict = user_setting.get("gcal_name_dict")
    if not isinstance(gcal_name_dict, dict):
        raise ValueError("gcal_name_dict must be available for provider identity resolution.")

    calendar_ids = []
    for calendar_id in gcal_name_dict.values():
        if not isinstance(calendar_id, str) or not calendar_id.strip():
            raise ValueError("Configured Google calendar IDs must be non-empty strings.")
        calendar_id = calendar_id.strip()
        if calendar_id not in calendar_ids:
            calendar_ids.append(calendar_id)

    if not calendar_ids:
        raise ValueError("At least one configured Google calendar is required.")
    return calendar_ids


def _resolve_google_event_location(user_setting, google_service, gcal_event_list, gcal_event_id):
    """Resolve one deterministic event to its actual configured Google calendar."""
    configured_calendar_ids = _configured_google_calendar_ids(user_setting)
    listed_matches = [event for event in gcal_event_list if event.get("id") == gcal_event_id]

    if len(listed_matches) > 1:
        raise SyncAbortError("Deterministic Google event identity resolves to multiple listed events.")

    if listed_matches:
        event = listed_matches[0]
        calendar_id = event.get("_notica_calendar_id") or (event.get("organizer") or {}).get("email")
        if calendar_id in configured_calendar_ids:
            return event, calendar_id

    lookup = getattr(google_service, "get_gcal_event_by_id", None)
    if not callable(lookup):
        return None, None

    provider_matches = []
    for calendar_id in configured_calendar_ids:
        event = lookup(calendar_id, gcal_event_id)
        if isinstance(event, dict):
            provider_matches.append((event, calendar_id))

    if len(provider_matches) > 1:
        raise SyncAbortError("Deterministic Google event identity resolves to multiple configured calendars.")
    if provider_matches:
        return provider_matches[0]
    return None, None


def _exception_error_code(exc: Exception) -> str:
    name = type(exc).__name__
    code = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    return code or "unexpected_sync_error"


def _google_private_metadata_for_route(user_setting, calendar_name):
    routes = user_setting.get("gcal_route_by_name")
    if not isinstance(routes, dict):
        raise ValueError("gcal_route_by_name must be available for provider metadata.")

    route = routes.get(calendar_name)
    if not isinstance(route, dict):
        raise ValueError(f"Calendar route is missing for '{calendar_name}'.")

    return build_google_private_metadata(
        user_setting.get("source_id"),
        route.get("mapping_id"),
        route.get("mapping_version"),
    )


def synchronize_notion_and_google_calendar(
    user_setting: dict,
    notion_service,
    google_service,
    compare_time=True,
    should_update_notion_tasks=True,
    should_update_google_events=True,
):
    try:
        notion_page_property = user_setting["page_property"]
        gcal_id_dict = user_setting["gcal_id_dict"]
        gcal_name_dict = user_setting["gcal_name_dict"]

        current_gcal_sync_time = get_current_time_in_iso_format()
        trigger_sync_time = get_current_time_in_iso_format()

        try:
            gcal_event_list = google_service.get_gcal_event()
            notion_config, notion_task_list = notion_service.get_notion_task()
            event_count = len(gcal_event_list)
            task_count = len(notion_task_list)

            sync_summary = {
                "google_event_count": event_count,
                "notion_task_count": task_count,
                "notion_config": notion_config,
            }

            logger.debug(f"Sync Summary: {sync_summary}")
            if task_count > SYNC_TASK_LIMIT or event_count > SYNC_TASK_LIMIT:
                logger.warning(
                    "Sync input volume exceeds limit=%s; task_count=%s event_count=%s. "
                    "Skipping run intentionally to avoid an oversized sync job.",
                    SYNC_TASK_LIMIT,
                    task_count,
                    event_count,
                )
                return build_capacity_limited_result(
                    sync_task_limit=SYNC_TASK_LIMIT,
                    trigger_sync_time=trigger_sync_time,
                    event_count=event_count,
                    task_count=task_count,
                )
            if task_count == 0 and event_count == 0:
                logger.debug("No Notion tasks found and no Google Calendar events found.")
                return build_sync_result(
                    200,
                    "sync_success",
                    "No Notion tasks found and no Google Calendar events found.",
                )
        except Exception:
            logger.exception("Failed to load sync inputs")
            return build_sync_result(
                500,
                "sync_error",
                {
                    "error_code": "sync_input_load_failed",
                    "error_message": SAFE_SYNC_FAILURE_MESSAGE,
                },
            )

        sync_errors = []
        for notion_task in notion_task_list:
            notion_task_page_id = notion_task.get("id")
            notion_gcal_event_id = None
            gcal_event = None
            action = None
            try:
                notion_gcal_event_id = deterministic_google_event_id(
                    user_setting.get("source_id"),
                    notion_task_page_id,
                )
                notion_gcal_cal_name = get_select(
                    notion_task["properties"],
                    notion_page_property["GCal_Name_Notion_Name"],
                )
                if not notion_gcal_cal_name:
                    notion_gcal_cal_name = user_setting["gcal_default_name"]
                    notion_gcal_cal_id = user_setting["gcal_default_id"]
                    logger.warning(f"Calendar name not found. Use the default calendar: {notion_gcal_cal_name}")
                    logger.debug(f"Calendar id not found. Use the default calendar id: {notion_gcal_cal_id}")
                    logger.info("Update Notion Task for default calendar id and calendar name")
                    notion_service.update_notion_task_for_default_calendar(
                        notion_task_page_id,
                        notion_gcal_cal_name,
                    )
                else:
                    notion_gcal_cal_id = gcal_name_dict.get(notion_gcal_cal_name)
                    if not notion_gcal_cal_id:
                        logger.warning(
                            f"Calendar '{notion_gcal_cal_name}' not found in gcal_name_dict, "
                            f"skipping task '{notion_task_page_id}'"
                        )
                        continue

                notion_deletion = get_checkbox(
                    notion_task["properties"],
                    notion_page_property["Delete_Notion_Name"],
                )
                notion_gcal_sync_time = get_rich_text(
                    notion_task["properties"],
                    notion_page_property["GCal_Sync_Time_Notion_Name"],
                )
                notion_task_last_edited_time = notion_task.get("last_edited_time")
                gcal_event, gcal_event_calendar_id = _resolve_google_event_location(
                    user_setting,
                    google_service,
                    gcal_event_list,
                    notion_gcal_event_id,
                )

                if notion_deletion:
                    if not should_update_google_events:
                        logger.debug(
                            "Skipping deletion for task_id=%s because Google writes are disabled.",
                            notion_task_page_id,
                        )
                        continue

                    action = "delete_gcal"
                    logger.debug(
                        "Deleting deterministic Google Calendar event_id=%s for task_id=%s.",
                        notion_gcal_event_id,
                        notion_task_page_id,
                    )
                    if gcal_event is not None:
                        gcal_event_calendar_name = gcal_id_dict.get(gcal_event_calendar_id)
                        if not gcal_event_calendar_name:
                            raise SyncAbortError(
                                "Deterministic Google event resolved outside the configured calendar routes."
                            )
                        assert_current_google_write_route(
                            user_setting,
                            gcal_event_calendar_name,
                            gcal_event_calendar_id,
                        )
                        google_service.delete_gcal_event(
                            gcal_event_calendar_id,
                            notion_gcal_event_id,
                        )
                    notion_service.delete_notion_task(notion_task_page_id)
                    if gcal_event is not None:
                        remove_gcal_event_from_list(
                            gcal_event_list,
                            gcal_event,
                            notion_gcal_event_id,
                        )
                    continue

                if gcal_event is None:
                    if should_update_google_events:
                        action = "create_gcal"
                        logger.debug(
                            "Creating deterministic Google Calendar event_id=%s for task_id=%s.",
                            notion_gcal_event_id,
                            notion_task_page_id,
                        )
                        assert_current_google_write_route(
                            user_setting,
                            notion_gcal_cal_name,
                            notion_gcal_cal_id,
                        )
                        private_metadata = _google_private_metadata_for_route(
                            user_setting,
                            notion_gcal_cal_name,
                        )
                        google_service.create_gcal_event(
                            notion_task,
                            notion_gcal_cal_id,
                            notion_gcal_event_id,
                            private_metadata,
                        )
                    continue

                gcal_event_summary = gcal_event.get("summary", "")
                gcal_event_updated_time = gcal_event.get("updated")
                gcal_cal_id = gcal_event_calendar_id
                gcal_cal_name = gcal_id_dict.get(gcal_cal_id)
                if not gcal_cal_name:
                    raise SyncAbortError("Deterministic Google event resolved outside the configured calendar routes.")

                if compare_time:
                    if not notion_task_last_edited_time or not gcal_event_updated_time:
                        logger.warning(
                            "Missing last edited or updated time. Skipping sync for task_id=%s event_id=%s",
                            notion_task_page_id,
                            notion_gcal_event_id,
                        )
                        continue

                    compare_timezones(
                        notion_task_last_edited_time,
                        gcal_event_updated_time,
                    )

                    if (
                        notion_gcal_sync_time
                        and notion_gcal_sync_time > gcal_event_updated_time
                        and notion_gcal_sync_time > notion_task_last_edited_time
                    ):
                        logger.debug(
                            "Skipping already-synced task_id=%s event_id=%s",
                            notion_task_page_id,
                            notion_gcal_event_id,
                        )
                        remove_gcal_event_from_list(
                            gcal_event_list,
                            gcal_event,
                            gcal_event_summary,
                        )
                        continue

                if should_update_google_events and (
                    not compare_time or (notion_task_last_edited_time > gcal_event_updated_time)
                ):
                    action = "update_gcal"
                    logger.debug(
                        "Updating deterministic Google event_id=%s from Notion task_id=%s.",
                        notion_gcal_event_id,
                        notion_task_page_id,
                    )
                    private_metadata = _google_private_metadata_for_route(
                        user_setting,
                        notion_gcal_cal_name,
                    )
                    if notion_gcal_cal_id == gcal_cal_id:
                        assert_current_google_write_route(
                            user_setting,
                            notion_gcal_cal_name,
                            notion_gcal_cal_id,
                        )
                        google_service.update_gcal_event(
                            notion_task,
                            notion_gcal_cal_id,
                            notion_gcal_event_id,
                            private_metadata,
                        )
                    else:
                        logger.debug(
                            "Moving deterministic Google event_id=%s to the configured calendar.",
                            notion_gcal_event_id,
                        )
                        assert_current_google_write_route(
                            user_setting,
                            gcal_cal_name,
                            gcal_cal_id,
                        )
                        assert_current_google_write_route(
                            user_setting,
                            notion_gcal_cal_name,
                            notion_gcal_cal_id,
                        )
                        google_service.move_gcal_event(
                            notion_gcal_event_id,
                            notion_gcal_cal_id,
                            gcal_cal_id,
                        )
                        assert_current_google_write_route(
                            user_setting,
                            notion_gcal_cal_name,
                            notion_gcal_cal_id,
                        )
                        google_service.update_gcal_event(
                            notion_task,
                            notion_gcal_cal_id,
                            notion_gcal_event_id,
                            private_metadata,
                        )
                    notion_service.update_notion_task_for_new_gcal_sync_time(
                        notion_task_page_id,
                        current_gcal_sync_time,
                    )
                elif should_update_notion_tasks and (
                    not compare_time or (notion_task_last_edited_time < gcal_event_updated_time)
                ):
                    action = "update_notion"
                    description = gcal_event.get("description") or ""
                    if len(description) > 2000:
                        sync_errors.append(
                            build_sync_error(
                                action,
                                "gcal_description_too_long",
                                error=(
                                    f"Skipped: GCal event description exceeds Notion's 2000-character "
                                    f"rich_text limit ({len(description)} chars). "
                                    "Syncing this event would corrupt data integrity."
                                ),
                                notion_task_id=notion_task_page_id,
                                gcal_event_id=notion_gcal_event_id,
                                gcal_event_start=gcal_event.get("start", {}).get("dateTime")
                                or gcal_event.get("start", {}).get("date"),
                                retriable=False,
                            )
                        )
                        logger.warning(
                            "Skipped update_notion for event_id=%s because the description exceeds "
                            "the Notion limit.",
                            notion_gcal_event_id,
                        )
                    else:
                        logger.debug(
                            "Google event is newer than the Notion task for task_id=%s event_id=%s",
                            notion_task_page_id,
                            notion_gcal_event_id,
                        )
                        notion_service.update_notion_task(
                            notion_task_page_id,
                            gcal_event,
                            gcal_cal_name,
                            current_gcal_sync_time,
                        )
                else:
                    logger.debug("Notion task and Google event are already in sync.")

                remove_gcal_event_from_list(
                    gcal_event_list,
                    gcal_event,
                    gcal_event_summary,
                )

            except MappingWriteFenceError as exc:
                logger.warning(
                    "Blocked stale Google provider write: action=%s reason=%s",
                    action,
                    exc.reason,
                )
                return build_sync_result(
                    409,
                    "sync_error",
                    {
                        "error_code": "mapping_write_fence_blocked",
                        "reason": exc.reason,
                        "retriable": False,
                    },
                )
            except SyncAbortError:
                raise
            except Exception as e:
                sync_errors.append(
                    build_sync_error(
                        action,
                        _exception_error_code(e),
                        error_message=SAFE_SYNC_FAILURE_MESSAGE,
                        error=None,
                        debug_detail=build_debug_exception_detail(e),
                        notion_task_id=notion_task_page_id,
                        gcal_event_id=notion_gcal_event_id,
                        gcal_event_start=(
                            gcal_event.get("start", {}).get("dateTime") or gcal_event.get("start", {}).get("date")
                            if gcal_event is not None
                            else None
                        ),
                        retriable=True,
                    )
                )
                logger.exception(
                    "Error during sync action=%s notion_task_id=%s",
                    action,
                    notion_task_page_id,
                )

        if gcal_event_list:
            logger.debug(
                "Ignoring %s Google Calendar events without deterministic Notica task identity.",
                len(gcal_event_list),
            )

    except Exception as e:
        logger.exception("Error during synchronization")
        return build_sync_result(
            500,
            "sync_error",
            {
                "error_code": _exception_error_code(e),
                "error_message": SAFE_SYNC_FAILURE_MESSAGE,
            },
        )

    message = {
        "summary": sync_summary,
        "trigger_time": trigger_sync_time,
        "errors": sync_errors,
    }
    return build_sync_result(200, "sync_success", message)


def force_update_notion_tasks_by_google_event_and_ignore_time(user_setting, notion_service, google_service):
    # -ga
    # Only update notion tasks
    # Do not update google events (Keep the google events as it is)
    result = synchronize_notion_and_google_calendar(
        user_setting=user_setting,
        notion_service=notion_service,
        google_service=google_service,
        compare_time=False,
        should_update_notion_tasks=True,
        should_update_google_events=False,
    )
    return result


def force_update_google_event_by_notion_task_and_ignore_time(user_setting, notion_service, google_service):
    # -na
    # Only update google events
    # Do not update notion tasks (Keep the notion tasks as it is)
    result = synchronize_notion_and_google_calendar(
        user_setting=user_setting,
        notion_service=notion_service,
        google_service=google_service,
        compare_time=False,
        should_update_notion_tasks=False,
        should_update_google_events=True,
    )
    return result
