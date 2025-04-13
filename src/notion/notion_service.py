import logging
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
import emoji

# Ensure the project root is in sys.path
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
if PROJECT_ROOT not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from . import notion_token  # noqa: E402

# Configure logging
logging.basicConfig(filename="notion_services.log", level=logging.INFO)
logger = logging.getLogger(__name__)

# Get the absolute path to the current directory
logger.info(f"Current directory: {CURRENT_DIR}")

# Initialize the Notion token
nt = notion_token.Notion()


def get_notion_task():

    # TODO: Notion has no filter for start date and end date
    # so add extra column: GCAL_END_DATE_NOTION_NAME

    before_date_with_time_zone = nt.BEFORE_DATE + "T00:00:00.000" + nt.TIMECODE
    after_date_with_time_zone = nt.AFTER_DATE + "T00:00:00.000" + nt.TIMECODE

    try:
        logger.info(
            f"Reading Notion database with ID: {nt.DATABASE_ID} from {nt.GCAL_END_DATE_NOTION_NAME}: {nt.AFTER_DATE} to {nt.DATE_NOTION_NAME}: {nt.BEFORE_DATE} (exclusive)"  # noqa: E501
        )
        return nt.NOTION.databases.query(
            database_id=nt.DATABASE_ID,
            filter={
                "and": [
                    {
                        "property": nt.DATE_NOTION_NAME,
                        "date": {"before": before_date_with_time_zone},
                    },
                    {
                        "property": nt.GCAL_END_DATE_NOTION_NAME,
                        "formula": {"date": {"on_or_after": after_date_with_time_zone}},
                    },
                ]
            },
        )["results"]
    except Exception as e:
        logging.error(f"Error reading Notion table: {e}")
        return None


def get_notion_task_by_gcal_event_id(gcal_event_id):
    try:
        logger.info(f"Reading Notion database by Google event ID: {gcal_event_id}")
        return nt.NOTION.databases.query(
            database_id=nt.DATABASE_ID,
            filter={
                "property": nt.GCAL_EVENTID_NOTION_NAME,
                "rich_text": {"equals": gcal_event_id},
            },
        )["results"]
    except Exception as e:
        logger.error(f"Error reading Notion table: {e}")
        return None


# Update specific properties in notion
# Note: Never update Extra info from google cal to notion
# That action will lose rich notion information
def update_notion_task(page_id, gcal_event, gcal_cal_name, new_gcal_sync_time):
    summary_without_emojis = remove_emojis(gcal_event.get("summary", ""))

    gcal_event_start_datetime = get_event_time(gcal_event, "start")
    gcal_event_end_datetime = get_event_time(gcal_event, "end")

    # Adjust end date if it is in the date format. All day event will be the same day
    if "date" in gcal_event["end"]:
        gcal_event_end_datetime = adjust_end_date_if_needed(gcal_event_end_datetime)

    try:
        nt.NOTION.pages.update(
            page_id=page_id,
            properties={
                nt.TASK_NOTION_NAME: {
                    "type": "title",
                    "title": [
                        {
                            "type": "text",
                            "text": {"content": summary_without_emojis},
                        },
                    ],
                },
                nt.DATE_NOTION_NAME: {
                    "type": "date",
                    "date": {
                        "start": gcal_event_start_datetime,
                        "end": gcal_event_end_datetime,
                    },
                },
                nt.LOCATION_NOTION_NAME: {
                    "type": "rich_text",
                    "rich_text": [{"text": {"content": gcal_event.get("location", "")}}],
                },
                nt.GCAL_SYNC_TIME_NOTION_NAME: {
                    "type": "rich_text",
                    "rich_text": [{"text": {"content": new_gcal_sync_time}}],
                },
                nt.GCAL_EVENTID_NOTION_NAME: {
                    "type": "rich_text",
                    "rich_text": [{"text": {"content": gcal_event.get("id", "")}}],
                },
                nt.CURRENT_CALENDAR_NAME_NOTION_NAME: {
                    "select": {"name": gcal_cal_name},
                },
            },
        )
    except Exception as e:
        logging.error(f"Error updating Notion page when updating Notion Task: {e}")
        return None


def update_notion_task_for_new_gcal_event_id(page_id, new_gcal_event_id):
    try:
        nt.NOTION.pages.update(
            page_id=page_id,
            properties={
                nt.GCAL_EVENTID_NOTION_NAME: {
                    "type": "rich_text",
                    "rich_text": [{"text": {"content": new_gcal_event_id}}],
                },
            },
        )
    except Exception as e:
        logging.error(f"Error updating Notion page when updating for new GCal Event ID: {e}")
        return None


def update_notion_task_for_new_gcal_sync_time(page_id, new_gcal_sync_time):
    try:
        nt.NOTION.pages.update(
            page_id=page_id,
            properties={
                nt.GCAL_SYNC_TIME_NOTION_NAME: {
                    "type": "rich_text",
                    "rich_text": [{"text": {"content": new_gcal_sync_time}}],
                },
            },
        )
    except Exception as e:
        logging.error(f"Error updating Notion page when updating for new GCal sync time: {e}")
        return None


def update_notion_task_for_default_calendar(page_id, default_calendar_id, default_calendar_name):
    try:
        nt.NOTION.pages.update(
            page_id=page_id,
            properties={
                nt.CURRENT_CALENDAR_NAME_NOTION_NAME: {
                    "select": {"name": default_calendar_name},
                },
            },
        )
    except Exception as e:
        logging.error(f"Error updating Notion page when updating for default calendar: {e}")
        return None


# Create notion with google description as extra information
def create_notion_task(gcal_event, gcal_cal_name):

    gcal_event_start_datetime = get_event_time(gcal_event, "start")
    gcal_event_end_datetime = get_event_time(gcal_event, "end")

    # Adjust end date if it is in the date format. All day event will be the same day
    if "date" in gcal_event["end"]:
        gcal_event_end_datetime = adjust_end_date_if_needed(gcal_event_end_datetime)

    try:
        nt.NOTION.pages.create(
            parent={"database_id": nt.DATABASE_ID},
            properties={
                nt.TASK_NOTION_NAME: {
                    "type": "title",
                    "title": [
                        {
                            "type": "text",
                            "text": {
                                "content": gcal_event.get("summary", ""),
                            },
                        },
                    ],
                },
                nt.DATE_NOTION_NAME: {
                    "type": "date",
                    "date": {
                        "start": gcal_event_start_datetime,
                        "end": gcal_event_end_datetime,
                    },
                },
                nt.EXTRAINFO_NOTION_NAME: {
                    "type": "rich_text",
                    "rich_text": [{"text": {"content": gcal_event.get("description", "")}}],
                },
                nt.LOCATION_NOTION_NAME: {
                    "type": "rich_text",
                    "rich_text": [{"text": {"content": gcal_event.get("location", "")}}],
                },
                nt.GCAL_EVENTID_NOTION_NAME: {
                    "type": "rich_text",
                    "rich_text": [{"text": {"content": gcal_event.get("id")}}],
                },
                nt.CURRENT_CALENDAR_NAME_NOTION_NAME: {
                    "select": {"name": gcal_cal_name},
                },
            },
        )
        logging.info(f"Event {gcal_event.get('summary', '')} created in Notion successfully.")
    except Exception as e:
        logging.error(f"Failed to sync event {gcal_event.get('summary', '')} to Notion: {e}")
        return None


def delete_notion_task(page_id):
    try:
        nt.NOTION.pages.update(
            page_id=page_id,
            properties={
                nt.DELETE_NOTION_NAME: {"checkbox": True},
                nt.GCAL_SYNC_TIME_NOTION_NAME: {
                    "type": "rich_text",
                    "rich_text": [{"text": {"content": ""}}],
                },
                nt.GCAL_EVENTID_NOTION_NAME: {
                    "type": "rich_text",
                    "rich_text": [{"text": {"content": ""}}],
                },
            },
        )
        logging.info(f"Event {page_id} marked as deletion in Notion successfully.")
    except Exception as e:
        logging.error(f"Failed to marked as deletion {page_id} to Notion: {e}")
        return None


def parse_date_in_notion_format(date_obj):
    """Helper function to notion format dates."""
    try:
        formatted_date = date_obj.strftime(f"%Y-%m-%dT%H:%M:%S{nt.TIMECODE}")
    except Exception as e:
        logging.error(f"Error formatting date: {e}")
        formatted_date = None
    return formatted_date


def get_notion_setting_data():
    return nt


def get_current_time():
    """Helper function to get the current time in the Notion format."""
    return parse_date_in_notion_format(datetime.now())


def get_event_time(event, key):
    return event.get(key, {}).get("dateTime") or event.get(key, {}).get("date", "")


def adjust_end_date_if_needed(end_date):
    try:
        end_date_obj = datetime.strptime(end_date, "%Y-%m-%d")
        adjusted_end_date_obj = end_date_obj - timedelta(days=1)
        return adjusted_end_date_obj.strftime("%Y-%m-%d")
    except ValueError:
        # If the end_date is not in "YYYY-MM-DD" format, return it as is
        return end_date


def remove_emojis(text):
    return emoji.replace_emoji(text, replace="")


if __name__ == "__main__":
    # Run python -m src.notion.notion_service
    # Ensure the directory exists
    Path("logs").mkdir(parents=True, exist_ok=True)

    # Check if the file exists and create it if not
    log_path = Path("logs/get_notion_task.json")
    if not log_path.exists():
        log_path.touch()

    # Open the file in write mode and dump JSON data
    with log_path.open("w") as output:
        data = get_notion_task()
        json.dump(data, output, indent=4)
    logging.info(
        f"Notion Task Count. {len(data)}, from {nt.GCAL_END_DATE_NOTION_NAME}: {nt.AFTER_DATE} to {nt.DATE_NOTION_NAME}: {nt.BEFORE_DATE} (exclusive)"  # noqa: E501
    )

    from rich.console import Console

    console = Console()
    event_id = "YOUR_EVENT_ID_HERE"
    result = get_notion_task_by_gcal_event_id(event_id)
    console.print(f"[bold cyan]Notion Task from GCal Event ID:[/] [green]{event_id}[/]")
    console.print(result)
