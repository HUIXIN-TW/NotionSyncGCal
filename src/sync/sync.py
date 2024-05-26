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

try:
    gcal_event_list = gcal_service.get_gcal_event()
    notion_task_list = notion_service.get_notion_task()
except Exception as e:
    logger.error(f"Error retrieving events or tasks: {e}")
    sys.exit(1)


def main():
    for notion_task in notion_task_list:
        notion_task_name = notion_task["properties"]["Task Name"]["title"][0][
            "plain_text"]
        notion_gcal_event_id = notion_task["properties"]["GCal Event Id"][
            "rich_text"]
        notion_gcal_event_id = notion_gcal_event_id[0][
            "plain_text"] if notion_gcal_event_id else None

        logger.info(
            f"Notion Loop: Checking task '{notion_task_name}' with GCal Event ID: {notion_gcal_event_id}"
        )

        if not notion_gcal_event_id:
            logger.info(
                f"Notion: Creating a new event in Google Calendar for task '{notion_task_name}'"
            )
            gcal_service.create_gcal_event(notion_task)
            continue

        for gcal_event in gcal_event_list:
            gcal_event_summary = gcal_event.get("summary", "")
            gcal_event_id = gcal_event.get("id", "")

            logger.info(
                f"Google Calendar: Checking event '{gcal_event_summary}' with ID: {gcal_event_id}"
            )

            if notion_gcal_event_id == gcal_event_id:
                notion_task_last_edited_time = notion_task["properties"][
                    "Last Updated Time"]["date"]["start"]
                gcal_event_updated_time = gcal_event.get("updated")

                logger.info(
                    f"Same Event ID - Notion time: {notion_task_last_edited_time} | Google time: {gcal_event_updated_time}"
                )
                if not notion_task_last_edited_time or not gcal_event_updated_time:
                    logger.warning(
                        "Notion Task or Google Calendar Event has no last edited time or updated time"
                    )
                    break

                # Convert the last edited time to ISO format
                notion_task_last_edited_time_iso = isoparse(
                    notion_task_last_edited_time)
                gcal_event_updated_time_iso = isoparse(gcal_event_updated_time)

                if notion_task_last_edited_time_iso > gcal_event_updated_time_iso:
                    logger.info(
                        f"Notion: Updating the event in Google Calendar for task '{notion_task_name}'"
                    )
                    gcal_service.update_gcal_event(gcal_event, notion_task)
                elif notion_task_last_edited_time_iso < gcal_event_updated_time_iso:
                    logger.info(
                        f"Google Calendar: Updating the task in Notion for event '{gcal_event_summary}'"
                    )
                    notion_service.update_notion_task(notion_task["id"], gcal_event)
                # Remove the processed Google Calendar event from the list
                gcal_event_list.remove(gcal_event)
                break

    # Create new tasks in Notion for the remaining Google Calendar events
    for gcal_event in gcal_event_list:
        gcal_event_id = gcal_event.get("id", "")
        if not any(notion_task["properties"]["GCal Event Id"]["rich_text"]
                   and notion_task["properties"]["GCal Event Id"]["rich_text"]
                   [0]["plain_text"] == gcal_event_id
                   for notion_task in notion_task_list):
            logger.info(
                f"Google Calendar: Creating a new task in Notion for event '{gcal_event.get('summary', '')}'"
            )
            notion_service.create_notion_task(gcal_event)

if __name__ == "__main__":
    main()
