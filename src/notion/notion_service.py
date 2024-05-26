import logging
import json
import sys
from datetime import datetime
from pathlib import Path

# Ensure the project root is in sys.path
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
if PROJECT_ROOT not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from . import notion_token

# Configure logging
logging.basicConfig(filename="notion_services.log", level=logging.INFO)
logger = logging.getLogger(__name__)

# Get the absolute path to the current directory
logger.info(f"Current directory: {CURRENT_DIR}")

# Initialize the Notion token
nt = notion_token.Notion()

def read_notion_database():
    logging.info("Get all Notion event")
    try:
        return nt.NOTION.databases.query(
            database_id=nt.DATABASE_ID,
            filter={
                "and": [
                    {
                        "property": nt.DATE_NOTION_NAME,
                        "date": {"on_or_before": nt.BEFORE_DATE},
                    },
                    {
                        "property": nt.DATE_NOTION_NAME,
                        "date": {"on_or_after": nt.AFTER_DATE},
                    },
                ]
            },
        )
    except Exception as e:
        logging.error(f"Error reading Notion table: {e}")
        return None


# Update specific properties in notion
# Note: Never update Extra info from google cal to notion
# That action will lose rich notion information
def update_notion_page(page_id, gcal_event):
    try:
        nt.NOTION.pages.update(
            page_id=page_id,
            properties={
                nt.TASK_NOTION_NAME: {
                    "type": "title",
                    "title": [
                        {
                            "type": "text",
                            "text": {
                                "content": event_name,
                            },
                        },
                    ],
                },
                nt.DATE_NOTION_NAME: {
                    "type": "date",
                    "date": {
                        "start": event_startdate,
                        "end": event_enddate,
                    },
                },
                nt.LASTUPDATEDTIME_NOTION_NAME: {
                    "type": "date",
                    "date": {
                        "start": get_current_time(),
                        "end": None,
                    },
                },
                nt.LOCATION_NOTION_NAME: {
                    "type": "rich_text",
                    "rich_text": [{"text": {"content": event_location}}],
                },
                nt.GCALEVENTID_NOTION_NAME: {
                    "type": "rich_text",
                    "rich_text": [{"text": {"content": event_id}}],
                },
                nt.CURRENT_CALENDAR_ID_NOTION_NAME: {
                    "rich_text": [{"text": {"content": gcal_id}}]
                },
                nt.CURRENT_CALENDAR_NAME_NOTION_NAME: {
                    "select": {"name": gcal_name},
                },
            },
        )
    except Exception as e:
        logging.error(f"Error updating Notion page: {e}")
        return None


# Create notion with google description as extra information
def create_notion_page(gcal_event):
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
                                "content": event_name,
                            },
                        },
                    ],
                },
                nt.DATE_NOTION_NAME: {
                    "type": "date",
                    "date": {
                        "start": event_startdate,
                        "end": event_enddate,
                    },
                },
                nt.LASTUPDATEDTIME_NOTION_NAME: {
                    "type": "date",
                    "date": {
                        "start": get_current_time(),
                        "end": None,
                    },
                },
                nt.EXTRAINFO_NOTION_NAME: {
                    "type": "rich_text",
                    "rich_text": [{"text": {"content": event_description}}],
                },
                nt.LOCATION_NOTION_NAME: {
                    "type": "rich_text",
                    "rich_text": [{"text": {"content": event_location}}],
                },
                nt.GCALEVENTID_NOTION_NAME: {
                    "type": "rich_text",
                    "rich_text": [{"text": {"content": event_id}}],
                },
                nt.CURRENT_CALENDAR_ID_NOTION_NAME: {
                    "rich_text": [{"text": {"content": gcal_id}}]
                },
                nt.CURRENT_CALENDAR_NAME_NOTION_NAME: {
                    "select": {"name": gcal_name},
                },
            },
        )
        logging.info(f"Event '{title}' created in Notion successfully.")
    except Exception as e:
        logging.error(f"Failed to sync event '{title}' to Notion: {e}")
        return None


def parse_date_in_notion_format(date_obj):
    """Helper function to notion format dates."""
    try:
        formatted_date = date_obj.strftime(f"%Y-%m-%dT%H:%M:%S{nt.TIMECODE}")
    except Exception as e:
        logging.error(f"Error formatting date: {e}")
        formatted_date = None
    return formatted_date

def get_current_time():
    """Helper function to get the current time in the Notion format."""
    return parse_date_in_notion_format(datetime.now())


if __name__ == "__main__":
    # Ensure the directory exists
    Path("logs").mkdir(parents=True, exist_ok=True)

    # Check if the file exists and create it if not
    log_path = Path("logs/read_notion_database.json")
    if not log_path.exists():
        log_path.touch()

    # Open the file in write mode and dump JSON data
    with log_path.open("w") as output:
        json.dump(read_notion_database(), output, indent=4)
