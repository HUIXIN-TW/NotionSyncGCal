import logging
import json
import sys
from datetime import datetime
from pathlib import Path
import emoji

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


def get_notion_task():
    try:
        logger.info(
            f"Reading Notion database with ID: {nt.DATABASE_ID} from {nt.DATE_NOTION_NAME}: {nt.AFTER_DATE} to {nt.BEFORE_DATE} (exclusive)"
        )
        return nt.NOTION.databases.query(
            database_id=nt.DATABASE_ID,
            filter={
                "and": [
                    {
                        "property": nt.DATE_NOTION_NAME,
                        "date": {"before": nt.BEFORE_DATE},
                    },
                    {
                        "property": nt.DATE_NOTION_NAME,
                        "date": {"on_or_after": nt.AFTER_DATE},
                    },
                ]
            },
        )["results"]
    except Exception as e:
        logging.error(f"Error reading Notion table: {e}")
        return None


# Update specific properties in notion
# Note: Never update Extra info from google cal to notion
# That action will lose rich notion information
def update_notion_task(page_id, gcal_event):
    summary_without_emojis = remove_emojis(gcal_event.get("summary", ""))
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
                        "start": gcal_event.get("start", {}).get("dateTime", ""),
                        "end": gcal_event.get("end", {}).get("dateTime", ""),
                    },
                },
                nt.LOCATION_NOTION_NAME: {
                    "type": "rich_text",
                    "rich_text": [
                        {"text": {"content": gcal_event.get("location", "")}}
                    ],
                },
                nt.GCAL_EVENTID_NOTION_NAME: {
                    "type": "rich_text",
                    "rich_text": [{"text": {"content": gcal_event.get("id", "")}}],
                },
                nt.CURRENT_CALENDAR_ID_NOTION_NAME: {
                    "type": "rich_text",
                    "rich_text": [
                        {
                            "text": {
                                "content": gcal_event.get("organizer", {}).get(
                                    "email", ""
                                )
                            }
                        }
                    ]
                },
                nt.CURRENT_CALENDAR_NAME_NOTION_NAME: {
                    "select": {
                        "name": gcal_event.get("organizer", {}).get("displayName", "")
                    },
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

# Create notion with google description as extra information
def create_notion_task(gcal_event):
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
                        "start": gcal_event.get("start", {}).get("dateTime", ""),
                        "end": gcal_event.get("end", {}).get("dateTime", ""),
                    },
                },
                nt.EXTRAINFO_NOTION_NAME: {
                    "type": "rich_text",
                    "rich_text": [
                        {"text": {"content": gcal_event.get("description", "")}}
                    ],
                },
                nt.LOCATION_NOTION_NAME: {
                    "type": "rich_text",
                    "rich_text": [
                        {"text": {"content": gcal_event.get("location", "")}}
                    ],
                },
                nt.GCAL_EVENTID_NOTION_NAME: {
                    "type": "rich_text",
                    "rich_text": [{"text": {"content": gcal_event.get("id", "")}}],
                },
                nt.CURRENT_CALENDAR_ID_NOTION_NAME: {
                    "type": "rich_text",
                    "rich_text": [
                        {
                            "text": {
                                "content": gcal_event.get("organizer", {}).get(
                                    "email", ""
                                )
                            }
                        }
                    ]
                },
                nt.CURRENT_CALENDAR_NAME_NOTION_NAME: {
                    "select": {
                        "name": gcal_event.get("organizer", {}).get("displayName", "")
                    },
                },
            },
        )
        logging.info(
            f"Event {gcal_event.get('summary', '')} created in Notion successfully."
        )
    except Exception as e:
        logging.error(
            f"Failed to sync event {gcal_event.get('summary', '')} to Notion: {e}"
        )
        return None


def delete_notion_task(page_id):
    try:
        nt.NOTION.pages.update(
            page_id=page_id, properties={nt.DELETE_NOTION_NAME: {"checkbox": True}}
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


def remove_emojis(text):
    return emoji.replace_emoji(text, replace="")


if __name__ == "__main__":
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
    print(f"Notion Task Num. {len(data)}, from {nt.AFTER_DATE} to {nt.BEFORE_DATE}")
