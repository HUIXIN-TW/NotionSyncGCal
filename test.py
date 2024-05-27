import sys
import logging
from datetime import datetime, timezone
from dateutil.parser import isoparse

from gcal import gcal_service
from notion import notion_service

# Configure logging
logging.basicConfig(filename="sync.log", level=logging.INFO)
logger = logging.getLogger(__name__)

def compare_timezones(notion_time_str, google_time_str):
    # Parse the time strings into datetime objects
    notion_time = isoparse(notion_time_str)
    google_time = isoparse(google_time_str)

    notion_timezone = notion_time.tzinfo
    google_timezone = google_time.tzinfo

    if notion_timezone != google_timezone:
        logger.warning(
            f"Timezones are different: Notion {notion_timezone} and Google Calendar {google_timezone}\nStopping the program."
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

def remove_gcal_event_from_list(gcal_event_list, gcal_event, gcal_event_summary):
    gcal_event_list.remove(gcal_event)
    logger.info(f"Google Calendar: Event '{gcal_event_summary}' removed from the list, {len(gcal_event_list)} events remaining\n")

def synchronize_notion_and_google_calendar(compare_time=True, should_update_notion_tasks=True, should_update_google_events=True):
    # Get the Google Calendar and Notion events
    try:
        gcal_event_list = gcal_service.get_gcal_event()
        notion_task_list = notion_service.get_notion_task()
    except Exception as e:
        logger.error(f"Error retrieving events or tasks: {e}")
        sys.exit(1)

    logger.info(
        "\n\n        -------------------------------Sync------------------------------        \n\n"
    )

    for notion_task in notion_task_list:
        notion_task_page_id = notion_task.get("id")
        notion_gcal_cal_name = notion_task["properties"][
            notion_service.nt.CURRENT_CALENDAR_NAME_NOTION_NAME
        ]["select"]["name"]
        notion_gcal_cal_id = notion_service.nt.get_cal_id(notion_gcal_cal_name)

        try:
            notion_gcal_event_id = notion_task["properties"][
                notion_service.nt.GCAL_EVENTID_NOTION_NAME
            ]["rich_text"][0]["plain_text"]
        except:
            notion_gcal_event_id = None

        notion_deletion = notion_task["properties"][
            notion_service.nt.DELETE_NOTION_NAME
        ]["checkbox"]

        notion_task_name = notion_task["properties"][
            notion_service.nt.TASK_NOTION_NAME
        ]["title"][0]["plain_text"]

        try:
            notion_gcal_sync_time = notion_task["properties"][
                notion_service.nt.GCAL_SYNC_TIME_NOTION_NAME
            ]["rich_text"][0]["plain_text"]
        except:
            notion_gcal_sync_time = None

        notion_task_last_edited_time = notion_task.get("last_edited_time")

        if not notion_gcal_event_id and should_update_google_events:
            logger.info(
                f"Notion Task: Creating a new event in Google Calendar for task '{notion_task_name}'/n"
            )
            new_gcal_event_id = gcal_service.create_gcal_event(
                notion_task, notion_gcal_cal_id
            )
            notion_service.update_notion_task_for_new_gcal_event_id(
                notion_task_page_id, new_gcal_event_id
            )
            continue

        if notion_deletion and should_update_google_events:
            logger.info(
                f"Notion: Deleting the event in Google Calendar for task '{notion_task_name}'"
            )
            gcal_service.delete_gcal_event(notion_gcal_cal_id, notion_gcal_event_id)
            continue

        for gcal_event in gcal_event_list:
            gcal_event_summary = gcal_event.get("summary", "")
            gcal_event_id = gcal_event.get("id", "")
            gcal_event_updated_time = gcal_event.get("updated")

            if notion_gcal_event_id == gcal_event_id:
                if compare_time:
                    compare_timezones(notion_task_last_edited_time, gcal_event_updated_time)

                    if not notion_task_last_edited_time or not gcal_event_updated_time:
                        logger.warning(
                            "Notion Task or Google Calendar Event has no last edited time or updated time. Stopping the program."
                        )
                        sys.exit(1)

                current_gcal_sync_time = get_current_time_in_iso_format()

                # Update Google Calendar if Notion is newer or force update
                if not compare_time or (should_update_google_events and notion_task_last_edited_time > gcal_event_updated_time):
                    logger.info(
                        f"Notion Task Edited Time: '{notion_task_last_edited_time}' vs Google Calendar Event Updated Time: '{gcal_event_updated_time}'"
                    )
                    logger.info(
                        f"🟠Notion Task: Updating the event in Google Calendar for task '{notion_task_name}'"
                    )
                    gcal_service.update_gcal_event(
                        notion_task, notion_gcal_cal_id, notion_gcal_event_id
                    )
                    notion_service.update_notion_task_for_new_gcal_sync_time(
                        notion_task_page_id, current_gcal_sync_time
                    )

                # Update Notion if Google Calendar is newer or force update
                elif compare_time and (should_update_notion_tasks and notion_task_last_edited_time < gcal_event_updated_time):
                    logger.info(
                        f"Google Calendar Event Updated Time: '{gcal_event_updated_time}' vs Notion Task Edited Time: '{notion_task_last_edited_time}'"
                    )
                    logger.info(
                        f"🟠Google Calendar: Updating the task in Notion for event '{gcal_event_summary}'"
                    )
                    notion_service.update_notion_task(
                        notion_task_page_id, gcal_event, current_gcal_sync_time
                    )

                else:
                    logger.info(
                        f"Notion Task '{notion_task_name}' and Google Calendar Event '{gcal_event_summary}' are in sync"
                    )

                remove_gcal_event_from_list(gcal_event_list, gcal_event, gcal_event_summary)
                break

    if len(gcal_event_list) > 0 and should_update_notion_tasks:
        logger.info(
            f"Google Calendar: Creating new tasks in Notion for {len(gcal_event_list)} events"
        )
        for gcal_event in gcal_event_list:
            logger.info(
                f"Google Calendar: Creating a new task in Notion for event '{gcal_event.get('summary', '')}'"
            )
            notion_service.create_notion_task(gcal_event)

def force_sync_notion_tasks_ignore_time():
    synchronize_notion_and_google_calendar(compare_time=False, should_update_google_events=False)

def force_sync_google_events_ignore_time():
    synchronize_notion_and_google_calendar(compare_time=False, should_update_notion_tasks=False)

if __name__ == "__main__":
    synchronize_notion_and_google_calendar()
    force_sync_notion_tasks_ignore_time()
    force_sync_google_events_ignore_time()
