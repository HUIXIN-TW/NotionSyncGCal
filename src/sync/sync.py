import sys
import logging
from pathlib import Path
from datetime import datetime, timezone
from dateutil.parser import isoparse
import pytz
from utils.logging_utils import get_logger  # noqa: E402

# Configure logging
logger = get_logger(__name__, log_file="tmp/sync_activity.log")

# Notion API Task Limit
NOTION_TASK_LIMIT = 100


def compare_timezones(notion_time_str, google_time_str):
    # Parse the time strings into datetime objects
    notion_time = isoparse(notion_time_str)
    google_time = isoparse(google_time_str)

    notion_timezone = notion_time.tzinfo
    google_timezone = google_time.tzinfo
    logger.debug(f"Notion Timezone: {notion_timezone}, Google Calendar Timezone: {google_timezone}")
    if notion_timezone != google_timezone:
        logger.error(
            f"Timezones are different: Notion {notion_timezone} and Google Calendar {google_timezone}\nStopping the program."  # noqa: E501
        )
        sys.exit(1)


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


def get_perth_time():
    """
    Returns current time in UTC
    """
    perth_tz = pytz.timezone("Australia/Perth")
    current_time = datetime.now(perth_tz)
    return current_time.strftime("Date: %Y-%m-%d Time: %H:%M:%S")


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
        trigger_sync_time = get_perth_time()

        # Get the Google Calendar and Notion events
        try:
            gcal_event_list = google_service.get_gcal_event()
            notion_task_summary, notion_task_list = notion_service.get_notion_task()
            event_count = len(gcal_event_list)
            task_count = len(notion_task_list)
            logging.info(f"Notion Task Count: {task_count}")
            # Check if task count exceeds the limit
            if task_count > NOTION_TASK_LIMIT or event_count > NOTION_TASK_LIMIT:
                warning_message = f"Task count exceeds {NOTION_TASK_LIMIT}. Sync process stopped to avoid overloading the Notion database."  # noqa: E501
                logging.warning(warning_message)
                sys.exit(1)  # Exit the script
            if task_count == 0:
                logger.debug("No Notion tasks found.")
                return {"statusCode": 200, "body": {"status": "sync success", "message": "No Notion tasks found."}}
            if event_count == 0:
                logger.debug("No Google Calendar events found.")
                return {
                    "statusCode": 200,
                    "body": {"status": "sync success", "message": "No Google Calendar events found."},
                }
        except Exception as e:
            return {"statusCode": 500, "body": {"status": "sync error", "message": str(e)}}

        # Check if Notion Task is in Google Calendar
        for notion_task in notion_task_list:
            """
            Notion Task properties & Google Calendar Event properties
            """
            # Notion Task properties for comparison: Notion Page ID and Google Calendar Event ID
            notion_task_page_id = notion_task.get("id")

            try:
                gcal_name_column_name_in_notion = notion_page_property["GCal_Name_Notion_Name"]
                notion_gcal_cal_name = notion_task["properties"][gcal_name_column_name_in_notion]["select"]["name"]
                notion_gcal_cal_id = gcal_name_dict.get(notion_gcal_cal_name)
            except Exception as e:
                notion_gcal_cal_name = user_setting["gcal_default_name"]
                logger.warning(f"Calendar name not found. Use the default calendar: {notion_gcal_cal_name}\n{e}")
                logger.debug("Update Notion Task for default calendar id and calendar name")
                notion_service.update_notion_task_for_default_calendar(notion_task_page_id, notion_gcal_cal_name)

            try:
                gcal_event_id_column_name_in_notion = notion_page_property["GCal_EventId_Notion_Name"]
                notion_gcal_event_id = notion_task["properties"][gcal_event_id_column_name_in_notion]["rich_text"][0][
                    "plain_text"
                ]
            except Exception as e:
                logger.warning(f"Failed to retrieve Google Calendar Event ID: {e}")
                notion_gcal_event_id = None

            # Notion Task properties for deletion
            delete_column_name_in_notion = notion_page_property["Delete_Notion_Name"]
            notion_deletion = notion_task["properties"][delete_column_name_in_notion]["checkbox"]

            # Notion Task properties for debugging
            task_column_name_in_notion = notion_page_property["Task_Notion_Name"]
            notion_task_name = notion_task["properties"][task_column_name_in_notion]["title"][0]["plain_text"]

            # Notion Task properties for sync status
            # the last time the task was synced between Notion and Google Calendar
            notion_gcal_sync_time = None
            try:
                gcal_sync_time_column_name_in_notion = notion_page_property["GCal_Sync_Time_Notion_Name"]
                notion_gcal_sync_time = (
                    notion_task["properties"]
                    .get(gcal_sync_time_column_name_in_notion, {})
                    .get("rich_text", [{}])[0]
                    .get("plain_text")
                )
            except Exception as e:
                logger.warning(f"Failed to retrieve Google Calendar Sync Time: {e}")

            notion_task_last_edited_time = notion_task.get("last_edited_time")

            """
            Sync Logic: Notion Actions or Google Calendar Actions
            """

            # Notion Task without Google Calendar Event ID - Create a new event in Google Calendar
            if not notion_gcal_event_id and should_update_google_events:
                if notion_deletion:
                    logger.debug(f"⚪️Deleted Flag & Not Creating in Google Calendar '{notion_task_name}'")
                    continue
                logger.debug(f"Notion Task: 🟢Creating a new event in Google Calendar for task '{notion_task_name}'")
                new_gcal_event_id = google_service.create_gcal_event(notion_task, notion_gcal_cal_id)
                notion_service.update_notion_task_for_new_gcal_event_id(notion_task_page_id, new_gcal_event_id)
                continue

            # Notion Task with deletion flag - Delete the event in Google Calendar
            if notion_deletion and notion_gcal_event_id is not None:
                logger.debug(f"Notion: 🔴Deleting the event in Google Calendar for task '{notion_task_name}'")
                try:
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
                        remove_gcal_event_from_list(gcal_event_list, deleted_gcal_event, notion_task_name)
                except Exception as e:
                    logger.warning(
                        f"Error deleting google calendar event ID: {notion_gcal_event_id} "
                        f"on {notion_gcal_cal_name}: {e}"
                    )

                continue

            # Notion Task with Google Calendar Event ID - Check if the event is in Google Calendar
            for gcal_event in gcal_event_list:
                # Google Calendar Event properties for comparison: Google Calendar Event ID
                gcal_event_summary = gcal_event.get("summary", "")
                gcal_event_id = gcal_event.get("id", "")

                # Google Calendar Event Updated Time
                gcal_event_updated_time = gcal_event.get("updated")

                # Google Calendar Current ID
                gcal_cal_id = gcal_event.get("organizer", {}).get("email")

                # Google Calendar Display Name
                gcal_cal_name = gcal_id_dict.get(gcal_cal_id)

                # Compare the Google Calendar Event ID with the Notion Task Google Calendar Event ID
                if notion_gcal_event_id == gcal_event_id:
                    if compare_time:
                        # Get the last edited time of the Notion Task and the updated time of the Google Calendar Event
                        compare_timezones(notion_task_last_edited_time, gcal_event_updated_time)

                        if not notion_task_last_edited_time or not gcal_event_updated_time:
                            logger.warning(
                                f"Missing last edited or updated time. Skipping task '{notion_task_name}' "
                                f"Notion: {notion_task_last_edited_time}, Google: {gcal_event_updated_time}"
                            )
                            continue

                        if (
                            notion_gcal_sync_time
                            and notion_gcal_sync_time > gcal_event_updated_time
                            and notion_gcal_sync_time > notion_task_last_edited_time
                        ):
                            logger.debug(
                                f"⚪️Already Done. Sync Time: {notion_gcal_sync_time}\nNotion '{notion_task_name}-{notion_task_last_edited_time}' vs Event '{gcal_event_summary}-{gcal_event_updated_time}'"  # noqa: E501
                            )
                            # Remove the processed Google Calendar event from the list
                            remove_gcal_event_from_list(gcal_event_list, gcal_event, gcal_event_summary)
                            break

                    # Update Google Calendar if Notion is newer or force update
                    # synchronize_notion_and_google_calendar(compare_time=False, should_update_notion_tasks=False)
                    # True and (True or ______) = True the logic will update the google event no matter time
                    if should_update_google_events and (
                        not compare_time or (notion_task_last_edited_time > gcal_event_updated_time)
                    ):
                        logger.debug(
                            f"Notion Task Edited Time: '{notion_task_last_edited_time}' vs Google Calendar Event Updated Time: '{gcal_event_updated_time}'"  # noqa: E501
                        )
                        logger.debug(
                            f"🥐 Notion Task: Updating the event in Google Calendar for task '{notion_task_name}'"
                        )

                        if notion_gcal_cal_id == gcal_cal_id:
                            google_service.update_gcal_event(notion_task, notion_gcal_cal_id, notion_gcal_event_id)
                        else:
                            logger.debug(
                                f"📅 Google Calendar: Moving event '{gcal_event_summary}' "
                                f"from '{notion_gcal_cal_id}' to '{gcal_cal_id}'"
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
                    # synchronize_notion_and_google_calendar(compare_time=False, should_update_google_events=False)
                    # True and (True or ______) = True the logic will update the notion task no matter time
                    elif should_update_notion_tasks and (
                        not compare_time or (notion_task_last_edited_time < gcal_event_updated_time)
                    ):
                        logger.debug(
                            f"Google Calendar Event Updated Time: '{gcal_event_updated_time}' vs Notion Task Edited Time: '{notion_task_last_edited_time}'"  # noqa: E501
                        )
                        logger.debug(
                            f"📅 Google Calendar: Updating the task in Notion for event '{gcal_event_summary}'"
                        )
                        notion_service.update_notion_task(
                            notion_task_page_id,
                            gcal_event,
                            gcal_cal_name,
                            current_gcal_sync_time,
                        )
                    else:
                        # Cause of notion has less time precision than google calendar, so this is impossible to happen
                        logger.debug(
                            f"Already Sync: Notion Task '{notion_task_name}' and Google Calendar Event '{gcal_event_summary}'"  # noqa: E501
                        )

                    # Remove the processed Google Calendar event from the list
                    remove_gcal_event_from_list(gcal_event_list, gcal_event, gcal_event_summary)
                    break

        # Create new tasks in Notion for the remaining Google Calendar events
        if len(gcal_event_list) > 0 and should_update_notion_tasks:
            logger.debug(f"🟢Google Calendar: Creating new tasks in Notion for {len(gcal_event_list)} events")
            for gcal_event in gcal_event_list:
                logger.debug(
                    f"Google Calendar: Creating a new task in Notion for event '{gcal_event.get('summary', '')}'"
                )

                # Google Calendar Display Name
                gcal_cal_name = gcal_id_dict.get(gcal_event.get("organizer", {}).get("email"))
                notion_service.create_notion_task(gcal_event, gcal_cal_name)
    except Exception as e:
        logger.error(f"Error during synchronization: {e}", exc_info=True)
        return {"statusCode": 500, "body": {"status": "sync error", "message": str(e)}}

    message = f"{notion_task_summary}. Synchronization completed successfully at {trigger_sync_time}, notion task count: {len(notion_task_list)}"  # noqa: E501
    return {"statusCode": 200, "body": {"status": "sync success", "message": message}}


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
