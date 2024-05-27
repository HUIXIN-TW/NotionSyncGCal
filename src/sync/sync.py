import os
import sys
import json
import logging
from datetime import datetime
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
            f"Timezones are different: Notion {notion_timezone} and Google Calendar {google_timezone}"
        )
        return False

    return True


def main():
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

    # Check if Notion Task is in Google Calendar
    for notion_task in notion_task_list:

        # Notion Task properties for comparison: Notion Page ID and Google Calendar Event ID
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

        # Notion Task properties for deletion
        notion_deletion = notion_task["properties"][notion_service.nt.DELETE_NOTION_NAME]["checkbox"]

        # Notion Task properties for debugging
        notion_task_name = notion_task["properties"][
            notion_service.nt.TASK_NOTION_NAME
        ]["title"][0]["plain_text"]

        # logger.info(
        #     f"Loop Notion Task {notion_task_name} with Notion Page ID: {notion_task_page_id} GCal Event ID: {notion_gcal_event_id}"
        # )

        # Notion Task without Google Calendar Event ID - Create a new event in Google Calendar
        if not notion_gcal_event_id:
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

        # Notion Task with deletion flag - Delete the event in Google Calendar
        if notion_deletion:
            logger.info(
                f"Notion: Deleting the event in Google Calendar for task '{notion_task_name}'"
            )
            gcal_service.delete_gcal_event(notion_gcal_cal_id, notion_gcal_event_id)
            continue

        # Notion Task with Google Calendar Event ID - Check if the event is in Google Calendar
        for gcal_event in gcal_event_list:

            # Google Calendar Event properties for comparison: Google Calendar Event ID
            gcal_event_summary = gcal_event.get("summary", "")
            gcal_event_id = gcal_event.get("id", "")

            # logger.info(
            #     f"Google Calendar Event {gcal_event_summary} with GCal Event ID: {gcal_event_id}"
            # )

            # Compare the Google Calendar Event ID with the Notion Task Google Calendar Event ID
            if notion_gcal_event_id == gcal_event_id:

                # Get the last edited time of the Notion Task and the updated time of the Google Calendar Event
                notion_task_last_edited_time = notion_task.get("last_edited_time")
                gcal_event_updated_time = gcal_event.get("updated")
                same_timezone = compare_timezones(
                    notion_task_last_edited_time, gcal_event_updated_time
                )

                if not notion_task_last_edited_time or not gcal_event_updated_time:
                    logger.warning(
                        "Notion Task or Google Calendar Event has no last edited time or updated time"
                    )
                    break

                # Compare timezones between Notion and Google Calendar
                if not same_timezone:
                    logger.warning("Timezones are different. Stopping the program.")
                    sys.exit(1)

                if notion_task_last_edited_time > gcal_event_updated_time:
                    logger.info(
                        f"Notion Task Edited Time: '{notion_task_last_edited_time}' vs Google Calendar Event Updated Time: '{gcal_event_updated_time}'"
                    )
                    logger.info(
                        f"Notion Task: Updating the event in Google Calendar for task '{notion_task_name}'"
                    )
                    gcal_service.update_gcal_event(
                        notion_task, notion_gcal_cal_id, notion_gcal_event_id
                    )
                elif notion_task_last_edited_time < gcal_event_updated_time:
                    logger.info(
                        f"Notion Task Edited Time: '{notion_task_last_edited_time}' vs Google Calendar Event Updated Time: '{gcal_event_updated_time}'"
                    )
                    logger.info(
                        f"Google Calendar: Updating the task in Notion for event '{gcal_event_summary}'"
                    )
                    notion_service.update_notion_task(notion_task_page_id, gcal_event)
                else:
                    logger.info(
                        f"Notion Task '{notion_task_name}' and Google Calendar Event '{gcal_event_summary}' are in sync"
                    )

                # Remove the processed Google Calendar event from the list
                gcal_event_list.remove(gcal_event)
                logger.info(
                    f"Google Calendar: Event '{gcal_event_summary}' removed from the list, {len(gcal_event_list)} events remaining\n"
                )
                break

    # Create new tasks in Notion for the remaining Google Calendar events
    if len(gcal_event_list) > 0:
        logger.info(
            f"Google Calendar: Creating new tasks in Notion for {len(gcal_event_list)} events"
        )
        for gcal_event in gcal_event_list:
            logger.info(
                f"Google Calendar: Creating a new task in Notion for event '{gcal_event.get('summary', '')}'"
            )
            notion_service.create_notion_task(gcal_event)


if __name__ == "__main__":
    main()
