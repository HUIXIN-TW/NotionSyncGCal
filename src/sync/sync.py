import sys
import re
from pathlib import Path
from datetime import datetime, timezone
from dateutil.parser import isoparse
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


def _exception_error_code(exc: Exception) -> str:
    name = type(exc).__name__
    code = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    return code or "unexpected_sync_error"


def _build_sync_error(
    action: str | None,
    error_code: str,
    *,
    error_message: str | None = None,
    error: str | None = None,
    notion_task_id: str | None = None,
    notion_task_name: str | None = None,
    gcal_event_id: str | None = None,
    gcal_event_title: str | None = None,
    gcal_event_start: str | None = None,
    retriable: bool | None = None,
    debug_detail: str | None = None,
):
    message = error_message if error_message is not None else error
    payload = {
        "action": action,
        "error_code": error_code,
        "error_message": message,
        "error": error,
        "notion_task_id": notion_task_id,
        "notion_task_name": notion_task_name,
        "gcal_event_id": gcal_event_id,
        "gcal_event_title": gcal_event_title,
        "gcal_event_start": gcal_event_start,
        "retriable": retriable,
    }
    if debug_detail is not None:
        payload["debug_detail"] = debug_detail
    return payload


def synchronize_notion_and_google_calendar(
    user_setting: dict,
    notion_service,
    google_service,
    compare_time=True,
    should_update_notion_tasks=True,
    should_update_google_events=True,
):
    try:
        # notion page property
        notion_page_property = user_setting["page_property"]
        gcal_id_dict = user_setting["gcal_id_dict"]
        gcal_name_dict = user_setting["gcal_name_dict"]

        # freeze the datetime of the gcal event and notion task status
        current_gcal_sync_time = get_current_time_in_iso_format()
        trigger_sync_time = get_current_time_in_iso_format()

        # Get the Google Calendar and Notion events
        try:
            gcal_event_list = google_service.get_gcal_event()
            notion_config, notion_task_list = notion_service.get_notion_task()
            event_count = len(gcal_event_list)
            task_count = len(notion_task_list)

            # Create a summary of the sync process
            sync_summary = {
                "google_event_count": event_count,
                "notion_task_count": task_count,
                "notion_config": notion_config,
            }

            logger.debug(f"Sync Summary: {sync_summary}")
            # Stop early if either side exceeds the supported sync cap.
            if task_count > SYNC_TASK_LIMIT or event_count > SYNC_TASK_LIMIT:
                warning_message = f"Task count exceeds {SYNC_TASK_LIMIT} when triggering sync at {trigger_sync_time}. Sync process stopped to avoid overloading the sync job."  # noqa: E501
                logger.warning(warning_message)
                return {
                    "statusCode": 200,
                    "body": {
                        "status": "sync_error",
                        "message": warning_message,
                    },
                }
            # No Notion tasks found and no Google Calendar events found
            if task_count == 0 and event_count == 0:
                logger.debug("No Notion tasks found and no Google Calendar events found.")
                return {
                    "statusCode": 200,
                    "body": {
                        "status": "sync_success",
                        "message": "No Notion tasks found and no Google Calendar events found.",
                    },
                }
        except Exception:
            logger.exception("Failed to load sync inputs")
            return {
                "statusCode": 500,
                "body": {
                    "status": "sync_error",
                    "message": {"error_code": "sync_input_load_failed", "error_message": SAFE_SYNC_FAILURE_MESSAGE},
                },
            }

        # Check if Notion Task is in Google Calendar
        sync_errors = []
        for notion_task in notion_task_list:
            notion_task_page_id = notion_task.get("id")
            notion_gcal_event_id = None
            action = None
            try:
                notion_gcal_cal_name = get_select(
                    notion_task["properties"], notion_page_property["GCal_Name_Notion_Name"]
                )
                if not notion_gcal_cal_name:
                    notion_gcal_cal_name = user_setting["gcal_default_name"]
                    notion_gcal_cal_id = user_setting["gcal_default_id"]
                    logger.warning(f"Calendar name not found. Use the default calendar: {notion_gcal_cal_name}")
                    logger.debug(f"Calendar id not found. Use the default calendar id: {notion_gcal_cal_id}")
                    logger.info("Update Notion Task for default calendar id and calendar name")
                    notion_service.update_notion_task_for_default_calendar(notion_task_page_id, notion_gcal_cal_name)
                else:
                    notion_gcal_cal_id = gcal_name_dict.get(notion_gcal_cal_name)
                    if not notion_gcal_cal_id:
                        logger.warning(
                            f"Calendar '{notion_gcal_cal_name}' not found in gcal_name_dict, "
                            f"skipping task '{notion_task_page_id}'"
                        )
                        continue

                notion_gcal_event_id = get_rich_text(
                    notion_task["properties"], notion_page_property["GCal_EventId_Notion_Name"]
                )
                notion_deletion = get_checkbox(notion_task["properties"], notion_page_property["Delete_Notion_Name"])
                notion_task_name = get_title(notion_task["properties"], notion_page_property["Task_Notion_Name"]) or ""
                notion_gcal_sync_time = get_rich_text(
                    notion_task["properties"], notion_page_property["GCal_Sync_Time_Notion_Name"]
                )
                notion_task_last_edited_time = notion_task.get("last_edited_time")

                # Notion Task without Google Calendar Event ID - Create a new event in Google Calendar
                if not notion_gcal_event_id and should_update_google_events:
                    if notion_deletion:
                        logger.debug("Skipping Google Calendar create for task marked deleted.")
                        continue
                    action = "create_gcal"
                    logger.debug("Creating a new event in Google Calendar for a Notion task.")
                    new_gcal_event_id = google_service.create_gcal_event(notion_task, notion_gcal_cal_id)
                    notion_service.update_notion_task_for_new_gcal_event_id(notion_task_page_id, new_gcal_event_id)
                    continue

                # Notion Task with deletion flag - Delete the event in Google Calendar
                if notion_deletion and notion_gcal_event_id is not None:
                    action = "delete_gcal"
                    logger.debug("Deleting a Google Calendar event for a Notion task.")
                    google_service.delete_gcal_event(notion_gcal_cal_id, notion_gcal_event_id)
                    notion_service.delete_notion_task(notion_task_page_id)

                    duplicate_notion_task_list = notion_service.get_notion_task_by_gcal_event_id(notion_gcal_event_id)
                    if duplicate_notion_task_list is not None:
                        for duplicate_notion_task in duplicate_notion_task_list:
                            duplicate_notion_task_page_id = duplicate_notion_task["id"]
                            logger.debug(f"Duplicate Notion Task Page ID: {duplicate_notion_task_page_id}")
                            notion_service.delete_notion_task(duplicate_notion_task_page_id)

                    deleted_gcal_event = get_gcal_event_from_list(gcal_event_list, notion_gcal_event_id)
                    if deleted_gcal_event is not None:
                        remove_gcal_event_from_list(gcal_event_list, deleted_gcal_event, notion_gcal_event_id)
                    continue

                # Notion Task with Google Calendar Event ID - Check if the event is in Google Calendar
                for gcal_event in gcal_event_list:
                    gcal_event_summary = gcal_event.get("summary", "")
                    gcal_event_id = gcal_event.get("id", "")
                    gcal_event_updated_time = gcal_event.get("updated")
                    gcal_cal_id = gcal_event.get("organizer", {}).get("email")
                    gcal_cal_name = gcal_id_dict.get(gcal_cal_id)

                    if notion_gcal_event_id == gcal_event_id:
                        if compare_time:
                            if not notion_task_last_edited_time or not gcal_event_updated_time:
                                logger.warning(
                                    "Missing last edited or updated time. Skipping sync for task_id=%s event_id=%s",
                                    notion_task_page_id,
                                    gcal_event_id,
                                )
                                continue

                            compare_timezones(notion_task_last_edited_time, gcal_event_updated_time)

                            if (
                                notion_gcal_sync_time
                                and notion_gcal_sync_time > gcal_event_updated_time
                                and notion_gcal_sync_time > notion_task_last_edited_time
                            ):
                                logger.debug(
                                    "Skipping already-synced task_id=%s event_id=%s",
                                    notion_task_page_id,
                                    gcal_event_id,
                                )
                                remove_gcal_event_from_list(gcal_event_list, gcal_event, gcal_event_summary)
                                break

                        # Update Google Calendar if Notion is newer or force update
                        if should_update_google_events and (
                            not compare_time or (notion_task_last_edited_time > gcal_event_updated_time)
                        ):
                            action = "update_gcal"
                            logger.debug(
                                "Notion task is newer than Google event for task_id=%s event_id=%s",
                                notion_task_page_id,
                                gcal_event_id,
                            )
                            logger.debug("Updating the Google Calendar event from Notion.")
                            if notion_gcal_cal_id == gcal_cal_id:
                                google_service.update_gcal_event(notion_task, notion_gcal_cal_id, notion_gcal_event_id)
                            else:
                                logger.debug(
                                    "Moving Google Calendar event_id=%s to the configured calendar.",
                                    gcal_event_id,
                                )
                                google_service.move_and_update_gcal_event(
                                    notion_task,
                                    notion_gcal_event_id,
                                    notion_gcal_cal_id,
                                    gcal_cal_id,
                                )
                            notion_service.update_notion_task_for_new_gcal_sync_time(
                                notion_task_page_id, current_gcal_sync_time
                            )
                        # Update Notion if Google Calendar is newer or force update
                        elif should_update_notion_tasks and (
                            not compare_time or (notion_task_last_edited_time < gcal_event_updated_time)
                        ):
                            action = "update_notion"
                            description = gcal_event.get("description") or ""
                            if len(description) > 2000:
                                sync_errors.append(
                                    _build_sync_error(
                                        action,
                                        "gcal_description_too_long",
                                        error=(
                                            f"Skipped: GCal event description exceeds Notion's 2000-character "
                                            f"rich_text limit ({len(description)} chars). "
                                            "Syncing this event would corrupt data integrity."
                                        ),
                                        notion_task_id=notion_task_page_id,
                                        notion_task_name=notion_task_name,
                                        gcal_event_id=gcal_event_id,
                                        gcal_event_title=gcal_event_summary,
                                        gcal_event_start=gcal_event.get("start", {}).get("dateTime")
                                        or gcal_event.get("start", {}).get("date"),
                                        retriable=False,
                                    )
                                )
                                logger.warning(
                                    "Skipped update_notion for event_id=%s because the description exceeds "
                                    "the Notion limit.",
                                    gcal_event_id,
                                )
                            else:
                                logger.debug(
                                    "Google event is newer than the Notion task for task_id=%s event_id=%s",
                                    notion_task_page_id,
                                    gcal_event_id,
                                )
                                logger.debug("Updating the Notion task from Google Calendar.")
                                notion_service.update_notion_task(
                                    notion_task_page_id,
                                    gcal_event,
                                    gcal_cal_name,
                                    current_gcal_sync_time,
                                )
                        else:
                            logger.debug("Notion task and Google event are already in sync.")

                        remove_gcal_event_from_list(gcal_event_list, gcal_event, gcal_event_summary)
                        break

            except SyncAbortError:
                raise
            except Exception as e:
                sync_errors.append(
                    _build_sync_error(
                        action,
                        _exception_error_code(e),
                        error_message=SAFE_SYNC_FAILURE_MESSAGE,
                        error=None,
                        debug_detail=build_debug_exception_detail(e),
                        notion_task_id=notion_task_page_id,
                        notion_task_name=notion_task_name,
                        gcal_event_id=notion_gcal_event_id,
                        gcal_event_title=gcal_event_summary if "gcal_event_summary" in locals() else None,
                        gcal_event_start=(
                            gcal_event.get("start", {}).get("dateTime") or gcal_event.get("start", {}).get("date")
                        )
                        if "gcal_event" in locals()
                        else None,
                        retriable=True,
                    )
                )
                logger.exception("Error during sync action=%s notion_task_id=%s", action, notion_task_page_id)

        # Create new tasks in Notion for the remaining Google Calendar events
        if len(gcal_event_list) > 0 and should_update_notion_tasks:
            logger.debug(f"🟢Google Calendar: Creating new tasks in Notion for {len(gcal_event_list)} events")
            for gcal_event in gcal_event_list:
                gcal_event_id = gcal_event.get("id")
                logger.debug(
                    f"Google Calendar: Creating a new task in Notion for event '{gcal_event.get('summary', '')}'"
                )
                try:
                    organizer_email = (gcal_event.get("organizer") or {}).get("email")
                    gcal_cal_name = gcal_id_dict.get(organizer_email)
                    if not gcal_cal_name:
                        sync_errors.append(
                            _build_sync_error(
                                "create_notion",
                                "gcal_event_not_owned",
                                error=(
                                    "Skipped: You are not the owner of this Google Calendar event, "
                                    "so it was not synced."
                                ),
                                gcal_event_id=gcal_event_id,
                                gcal_event_title=gcal_event.get("summary", ""),
                                gcal_event_start=gcal_event.get("start", {}).get("dateTime")
                                or gcal_event.get("start", {}).get("date"),
                                retriable=False,
                            )
                        )
                        logger.warning(
                            "Skipped create_notion for non-owned/invited Google Calendar event_id=%s",
                            gcal_event_id,
                        )
                        continue
                    description = gcal_event.get("description") or ""
                    if len(description) > 2000:
                        sync_errors.append(
                            _build_sync_error(
                                "create_notion",
                                "gcal_description_too_long",
                                error=(
                                    f"Skipped: GCal event description exceeds Notion's 2000-character "
                                    f"rich_text limit ({len(description)} chars). "
                                    "Syncing this event would corrupt data integrity."
                                ),
                                gcal_event_id=gcal_event_id,
                                gcal_event_title=gcal_event.get("summary", ""),
                                gcal_event_start=gcal_event.get("start", {}).get("dateTime")
                                or gcal_event.get("start", {}).get("date"),
                                retriable=False,
                            )
                        )
                        logger.warning(
                            "Skipped create_notion for event_id=%s because the description exceeds the Notion limit.",
                            gcal_event_id,
                        )
                    else:
                        notion_service.create_notion_task(gcal_event, gcal_cal_name)
                except Exception as e:
                    sync_errors.append(
                        _build_sync_error(
                            "create_notion",
                            _exception_error_code(e),
                            error_message=SAFE_SYNC_FAILURE_MESSAGE,
                            error=None,
                            debug_detail=build_debug_exception_detail(e),
                            gcal_event_id=gcal_event_id,
                            gcal_event_title=gcal_event.get("summary", ""),
                            gcal_event_start=gcal_event.get("start", {}).get("dateTime")
                            or gcal_event.get("start", {}).get("date"),
                            retriable=True,
                        )
                    )
                    logger.exception("Error during create_notion for event_id=%s", gcal_event_id)

    except Exception as e:
        logger.exception("Error during synchronization")
        return {
            "statusCode": 500,
            "body": {
                "status": "sync_error",
                "message": {
                    "error_code": _exception_error_code(e),
                    "error_message": SAFE_SYNC_FAILURE_MESSAGE,
                },
            },
        }

    message = {
        "summary": sync_summary,
        "trigger_time": trigger_sync_time,
        "errors": sync_errors,
    }
    return {"statusCode": 200, "body": {"status": "sync_success", "message": message}}


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


if __name__ == "__main__":
    # python -m src.sync.sync
    from rich.pretty import pprint

    sys.path.append(str(Path(__file__).resolve().parent.parent))
    from config.config import generate_uuid_config  # noqa: E402
    from notion.notion_service import NotionService  # noqa: E402
    from notion.notion_config import NotionConfig  # noqa: E402
    from gcal.gcal_token import GoogleToken  # noqa: E402
    from gcal.gcal_service import GoogleService  # noqa: E402

    config = generate_uuid_config("huixinyang")
    notion_config = NotionConfig(config, logger)
    notion_token = notion_config.token
    notion_user_setting = notion_config.user_setting
    notion_service = NotionService(notion_token, notion_user_setting, logger)
    google_token = GoogleToken(config, logger)
    google_service = GoogleService(notion_user_setting, google_token, logger)
    pprint(notion_config.user_setting)
    synchronize_notion_and_google_calendar(
        user_setting=notion_config.user_setting,
        notion_service=notion_service,
        google_service=google_service,
        compare_time=True,
        should_update_notion_tasks=True,
        should_update_google_events=True,
    )
    # force_update_notion_tasks_by_google_event_and_ignore_time(
    #     user_setting=notion_config.user_setting,
    #     notion_service=notion_service,
    #     google_service=google_service,
    # )
    # force_update_google_event_by_notion_task_and_ignore_time(
    #     user_setting=notion_config.user_setting,
    #     notion_service=notion_service,
    #     google_service=google_service,
    # )
