import sys
import logging
from datetime import datetime, timezone
from dateutil.parser import isoparse

from gcal import gcal_service
from notion import notion_service

# Configure logging
logging.basicConfig(filename="sync.log", level=logging.INFO)
logger = logging.getLogger(__name__)

# Notion API Task Limit
NOTION_TASK_LIMIT = 100


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
    logger.info(
        f"Google Calendar: Event '{gcal_event_summary}' removed from the list, {len(gcal_event_list)} events remaining\n"
    )


def get_gcal_event_from_list(gcal_event_list, gcal_event_id):
    for gcal_event in gcal_event_list:
        if gcal_event.get("id") == gcal_event_id:
            return gcal_event
    return f"{gcal_event_id} Can't be found in {gcal_event}"


def synchronize_notion_and_google_calendar(
    compare_time=True, should_update_notion_tasks=True, should_update_google_events=True
):
    # freeze the datetime of the gcal event and notion task status
    current_gcal_sync_time = get_current_time_in_iso_format()

    # Get the Google Calendar and Notion events
    try:
        gcal_event_list = gcal_service.get_gcal_event()
        notion_task_list = notion_service.get_notion_task()
        task_count = len(notion_task_list)
        logging.info(f"Notion Task Count: {task_count}")
        # Check if task count exceeds the limit
        if task_count > NOTION_TASK_LIMIT:
            logging.warning(f"Task count exceeds {NOTION_TASK_LIMIT}. Sync process stopped to avoid overloading the Notion database.")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Error retrieving events or tasks: {e}")
        sys.exit(1)

    # Check if Notion Task is in Google Calendar
    for notion_task in notion_task_list:
        """
        Notion Task properties & Google Calendar Event properties
        """
        # Notion Task properties for comparison: Notion Page ID and Google Calendar Event ID
        notion_task_page_id = notion_task.get("id")

        try:
            notion_gcal_cal_name = notion_task["properties"][
                notion_service.nt.CURRENT_CALENDAR_NAME_NOTION_NAME
            ]["select"]["name"]
            notion_gcal_cal_id = notion_service.nt.get_cal_id(notion_gcal_cal_name)
        except:
            logger.warning(
                f"Calendar name not found. Use the default calendar: {notion_service.nt.GCAL_DEFAULT_NAME}"
            )
            notion_gcal_cal_name = notion_service.nt.GCAL_DEFAULT_NAME
            notion_gcal_cal_id = notion_service.nt.GCAL_DEFAULT_ID
            logger.info("Update Notion Task for default calendar id and calendar name")
            notion_service.update_notion_task_for_default_calendar(
                notion_task_page_id, notion_gcal_cal_id, notion_gcal_cal_name
            )

        try:
            notion_gcal_event_id = notion_task["properties"][
                notion_service.nt.GCAL_EVENTID_NOTION_NAME
            ]["rich_text"][0]["plain_text"]
        except:
            notion_gcal_event_id = None

        # Notion Task properties for deletion
        notion_deletion = notion_task["properties"][
            notion_service.nt.DELETE_NOTION_NAME
        ]["checkbox"]

        # Notion Task properties for debugging
        notion_task_name = notion_task["properties"][
            notion_service.nt.TASK_NOTION_NAME
        ]["title"][0]["plain_text"]

        # Notion Task properties for sync status - the last time the task was synced between Notion and Google Calendar
        try:
            notion_gcal_sync_time = notion_task["properties"][
                notion_service.nt.GCAL_SYNC_TIME_NOTION_NAME
            ]["rich_text"][0]["plain_text"]
        except:
            notion_gcal_sync_time = None

        notion_task_last_edited_time = notion_task.get("last_edited_time")

        """
        Sync Logic: Notion Actions or Google Calendar Actions
        """

        # Notion Task without Google Calendar Event ID - Create a new event in Google Calendar
        if not notion_gcal_event_id and should_update_google_events:
            if notion_deletion:
                logger.info(
                    f"⚪️Deleted Flag & Not Creating in Google Calendar '{notion_task_name}'\n"
                )
                continue
            logger.info(
                f"Notion Task: 🟢Creating a new event in Google Calendar for task '{notion_task_name}'\n"
            )
            new_gcal_event_id = gcal_service.create_gcal_event(
                notion_task, notion_gcal_cal_id
            )
            notion_service.update_notion_task_for_new_gcal_event_id(
                notion_task_page_id, new_gcal_event_id, notion_gcal_cal_id
            )
            continue

        # Notion Task with deletion flag - Delete the event in Google Calendar
        if notion_deletion and notion_gcal_event_id != None:
            logger.info(
                f"Notion: 🔴Deleting the event in Google Calendar for task '{notion_task_name}'"
            )
            try:
                gcal_service.delete_gcal_event(notion_gcal_cal_id, notion_gcal_event_id)
                notion_service.delete_notion_task(notion_task_page_id)
                deleted_gcal_event = get_gcal_event_from_list(
                    gcal_event_list, notion_gcal_event_id
                )
                remove_gcal_event_from_list(
                    gcal_event_list, deleted_gcal_event, notion_task_name
                )
            except Exception as e:
                logger.error(
                    f"Error deleting google calendar event. ID: {notion_gcal_event_id} on {notion_gcal_cal_name}: {e}"
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
            gcal_cal_name = notion_service.nt.get_cal_name(gcal_cal_id)

            # Compare the Google Calendar Event ID with the Notion Task Google Calendar Event ID
            if notion_gcal_event_id == gcal_event_id:
                if compare_time:
                    # Get the last edited time of the Notion Task and the updated time of the Google Calendar Event
                    compare_timezones(
                        notion_task_last_edited_time, gcal_event_updated_time
                    )

                    if not notion_task_last_edited_time or not gcal_event_updated_time:
                        logger.warning(
                            "Notion Task or Google Calendar Event has no last edited time or updated time. Stopping the program."
                        )
                        sys.exit(1)

                    if (
                        notion_gcal_sync_time
                        and notion_gcal_sync_time > gcal_event_updated_time
                        and notion_gcal_sync_time > notion_task_last_edited_time
                    ):
                        logger.info(
                            f"⚪️Already Done. Sync Time: {notion_gcal_sync_time}\nNotion '{notion_task_name}-{notion_task_last_edited_time}' vs Event '{gcal_event_summary}-{gcal_event_updated_time}'"
                        )
                        # Remove the processed Google Calendar event from the list
                        remove_gcal_event_from_list(
                            gcal_event_list, gcal_event, gcal_event_summary
                        )
                        break

                # Update Google Calendar if Notion is newer or force update
                # synchronize_notion_and_google_calendar(compare_time=False, should_update_notion_tasks=False)
                # True and (True or ______) = True the logic will update the google event no matter time
                if should_update_google_events and (
                    not compare_time
                    or (notion_task_last_edited_time > gcal_event_updated_time)
                ):
                    logger.info(
                        f"Notion Task Edited Time: '{notion_task_last_edited_time}' vs Google Calendar Event Updated Time: '{gcal_event_updated_time}'"
                    )
                    logger.info(
                        f"🥐 Notion Task: Updating the event in Google Calendar for task '{notion_task_name}'"
                    )

                    if notion_gcal_cal_id == gcal_cal_id:
                        gcal_service.update_gcal_event(
                            notion_task, notion_gcal_cal_id, notion_gcal_event_id
                        )
                    else:
                        gcal_service.move_and_update_gcal_event(
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
                    not compare_time
                    or (notion_task_last_edited_time < gcal_event_updated_time)
                ):
                    logger.info(
                        f"Google Calendar Event Updated Time: '{gcal_event_updated_time}' vs Notion Task Edited Time: '{notion_task_last_edited_time}'"
                    )
                    logger.info(
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
                    logger.info(
                        f"Already Sync: Notion Task '{notion_task_name}' and Google Calendar Event '{gcal_event_summary}'"
                    )

                # Remove the processed Google Calendar event from the list
                remove_gcal_event_from_list(
                    gcal_event_list, gcal_event, gcal_event_summary
                )
                break

    # Create new tasks in Notion for the remaining Google Calendar events
    if len(gcal_event_list) > 0 and should_update_notion_tasks:
        logger.info(
            f"🟢Google Calendar: Creating new tasks in Notion for {len(gcal_event_list)} events"
        )
        for gcal_event in gcal_event_list:
            logger.info(
                f"Google Calendar: Creating a new task in Notion for event '{gcal_event.get('summary', '')}'"
            )

            # Google Calendar Display Name
            gcal_cal_name = notion_service.nt.get_cal_name(
                gcal_event.get("organizer", {}).get("email")
            )
            notion_service.create_notion_task(gcal_event, gcal_cal_name)


def force_update_notion_tasks_by_google_event_and_ignore_time():
    # -ga
    # Only update notion tasks
    # Do not update google events (Keep the google events as it is)
    synchronize_notion_and_google_calendar(
        compare_time=False, should_update_google_events=False
    )


def force_update_google_event_by_notion_task_and_ignore_time():
    # -na
    # Only update google events
    # Do not update notion tasks (Keep the notion tasks as it is)
    synchronize_notion_and_google_calendar(
        compare_time=False, should_update_notion_tasks=False
    )


if __name__ == "__main__":
    synchronize_notion_and_google_calendar()
    # force_update_notion_tasks_by_google_event_and_ignore_time()
    # force_update_google_event_by_notion_task_and_ignore_time()
