import logging
import json
import os
import sys
import time
import pytz
from datetime import datetime, timedelta, date, timezone
from dateutil.parser import isoparse
from pathlib import Path

# Ensure the project root is in sys.path
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
if PROJECT_ROOT not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

# Local application/library specific imports
from notion import notion_token
from . import gcal_token

# Configure logging
logging.basicConfig(filename="google_services.log", level=logging.INFO)
logger = logging.getLogger(__name__)

# Get the absolute path to the current directory
logger.info(f"Current directory: {CURRENT_DIR}")

# Construct the absolute file paths within the container
NOTION_SETTINGS_PATH = (CURRENT_DIR / "../../token/notion_setting.json").resolve()
CLIENT_SECRET_PATH = (CURRENT_DIR / "../../token/client_secret.json").resolve()
CREDENTIALS_PATH = (CURRENT_DIR / "../../token/token.pkl").resolve()

# Initialize Notion and Google tokens
nt = notion_token.Notion()
gt = gcal_token.Google()


def get_gcal_event():
    # Calculate the start and end dates for the event range
    try:
        events = []
        for cal_id in nt.GCAL_DIC.values():
            response = (
                gt.service.events()
                .list(
                    calendarId=cal_id,
                    timeMin=nt.GOOGLE_TIMEMIN,
                    timeMax=nt.GOOGLE_TIMEMAX,
                )
                .execute()
            )

            if response.get("items"):
                events.extend(response["items"])
            logger.info(
                f"Retrieved {len(response.get('items', []))} events from calendar ID {cal_id}"
            )

        logger.info(f"Total events retrieved: {len(events)}")
        return events
    except Exception as e:
        logger.error(f"Error retrieving Google Calendar events: {e}", exc_info=True)
        return []


def update_gcal_event(notion_task, existing_gcal_cal_id,
                      existing_gcal_event_id):
    event = make_event_body(notion_task)
    gt.service.events().update(calendarId=existing_gcal_cal_id,
                               eventId=existing_gcal_event_id,
                               body=event).execute()


def create_gcal_event(notion_task, new_gcal_calendar_id=nt.GCAL_DEFAULT_ID):
    event = make_event_body(notion_task)
    gt.service.events().insert(calendarId=new_gcal_calendar_id, body=event).execute()
    # get the event id and update the notion task by query page id
    return event_id


def move_gcal_event(gcal_event_id, new_gcal_calendar_id, existing_gcal_cal_id):
    gt.service.events().move(calendarId=existing_gcal_cal_id, eventId=exist_eventId, destination=new_gcal_calendar_id).execute()


def delete_gcal_event(gcal_calendar_id, gcal_event_id):
    try:
        gt.service.events().delete(calendarId=calendar_id,
                                   eventId=event_id).execute()
        logger.info(f"Successfully deleted event with ID: {event_id}")
    except Exception as e:
        logger.error(
            f"An error occurred while deleting event with ID: {event_id}: {e}")
        sys.exit(1)


def make_event_body(notion_task):
    # set icone and task name
    event_icon = notion_task.get("properties",
                                 {}).get(nt.COMPLETEICON_NOTION_NAME,
                                         {}).get("formula",
                                                 {}).get("string", "❓")
    event_name = notion_task.get("properties",
                                 {}).get(nt.TASK_NOTION_NAME,
                                         {}).get("title", [{}])[0].get(
                                             "text", {}).get("content", "")
    event_summary = event_icon + event_name

    # set start and end date
    # notion datetime format is "2024-05-27T19:00:00.000+08:00":
    #   case1: with end datetime (using) or
    #   case2: without end datetime (use start datetime + 1 hour)
    # notion date format is "2024-05-26"
    #   case1: with end date (using end date + 1 day) or
    #   case2: without end date (use start date + 1 day)
    # to_utc(event_start_date).strftime("%Y-%m-%dT%H:%M:%S")
    # to_utc(event_start_date).strftime("%Y-%m-%d")
    event_start_date = notion_task.get("properties",
                                       {}).get(nt.DATE_NOTION_NAME,
                                               {}).get("date",
                                                       {}).get("start", "")
    event_end_date = notion_task.get("properties",
                                     {}).get(nt.DATE_NOTION_NAME,
                                             {}).get("date",
                                                     {}).get("end", "")
    # Adjust and convert dates to UTC
    start_dt_utc, end_dt_utc = adjust_notion_dates(event_start_date, event_end_date)

    logger.info(f"Adjusted start datetime: {start_dt_utc.strftime('%Y-%m-%dT%H:%M:%S%z')}")
    logger.info(f"Adjusted end datetime: {end_dt_utc.strftime('%Y-%m-%dT%H:%M:%S%z')}")

    # set location
    event_location = notion_task.get("properties", {}).get(
        nt.LOCATION_NOTION_NAME,
        {}).get("rich_text", [{}])[0].get("text", {}).get("content", "")

    # set description
    event_description = notion_task.get("properties", {}).get(
        nt.DESCRIPTION_NOTION_NAME,
        {}).get("rich_text", [{}])[0].get("text", {}).get("content", "")

    # set url
    event_source_url = notion_task.get("url", "")

    event = {
        "summary": event_summary,
        "location": event_location,
        "description": event_description,
        "start": {
            "dateTime": event_start_date,
            "timeZone": nt.TIMEZONE,
        },
        "end": {
            "dateTime": event_end_date,
            "timeZone": nt.TIMEZONE,
        },
        "source": {
            "title": "Notion Link",
            "url": event_source_url,
        },
    }
    return event


def adjust_notion_dates(start_date, end_date=None):
    """
    Adjust Notion date or datetime formats and convert them to UTC.
    """
    if "T" in start_date:
        # It's a datetime format
        notion_start_dt = isoparse(start_date)
        notion_start_dt_utc = to_utc(notion_start_dt)
        if end_date:
            notion_end_dt = isoparse(end_date)
            notion_end_dt_utc = to_utc(notion_end_dt)
        else:
            notion_end_dt_utc = notion_start_dt_utc + timedelta(minutes=nt.DEFAULT_EVENT_LENGTH)
    else:
        # It's a date format
        notion_start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        if end_date:
            notion_end_date = datetime.strptime(end_date, "%Y-%m-%d").date() + timedelta(days=1)
        else:
            notion_end_date = notion_start_date + timedelta(days=1)

        notion_start_dt = datetime.combine(notion_start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        notion_end_dt = datetime.combine(notion_end_date, datetime.min.time()).replace(tzinfo=timezone.utc)

        notion_start_dt_utc = to_utc(notion_start_dt)
        notion_end_dt_utc = to_utc(notion_end_dt)

    return notion_start_dt_utc, notion_end_dt_utc

def to_utc(datetime_obj):
    return datetime_obj.astimezone(timezone.utc)

# Example usage
if __name__ == "__main__":
    # Ensure the directory exists
    Path("logs").mkdir(parents=True, exist_ok=True)

    # Check if the file exists and create it if not
    log_path = Path("logs/get_gcal_event.json")
    if not log_path.exists():
        log_path.touch()

    # Open the file in write mode and dump JSON data
    with log_path.open("w") as output:
        json.dump(get_gcal_event(), output, indent=4)
