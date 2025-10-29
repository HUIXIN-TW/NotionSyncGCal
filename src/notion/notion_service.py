from notion_client import Client
from notion_client.errors import APIResponseError
from datetime import datetime, timedelta
import emoji


class SettingError(Exception):
    """Custom exception to handle setting errors in the Notion class."""

    def __init__(self, message):
        super().__init__(message)


class NotionService:
    def __init__(self, token, user_setting, logger):
        self.logger = logger
        self.token = token
        self.setting = user_setting
        self.page_property = self.setting["page_property"]

        try:
            self.client = Client(auth=self.token)
            self.logger.debug("Notion client initialized successfully.")
        except Exception as e:
            self.logger.error(f"Failed to initialize Notion client: {e}")
            raise SettingError(f"Failed to initialize Notion client: {e}")

    def test_connection(self):
        try:
            self.client.users.me()
            self.logger.info("Notion connection passed.")
            return True
        except APIResponseError as e:
            self.logger.error(f"Notion API error: {e}. Please click 'view settings' and re-authorize the integration.")
            return False
        except Exception as e:
            self.logger.error(f"Notion Connection failed: {e}. Please check your network connection.")
            return False

    def get_notion_task(self):

        # TODO: Notion has no filter for start date and end date so add extra column: GCAL_END_DATE_NOTION_NAME
        before_date_with_time_zone = self.setting["before_date"] + "T00:00:00.000" + self.setting["timecode"]
        after_date_with_time_zone = self.setting["after_date"] + "T00:00:00.000" + self.setting["timecode"]
        notion_summary = f"Reading Notion database with ID: {self.setting['database_id']} from {self.page_property['GCal_End_Date_Notion_Name']}: {self.setting['after_date']} to {self.page_property['Date_Notion_Name']}: {self.setting['before_date']} (exclusive)"  # noqa: E501

        self.logger.debug(notion_summary)

        try:
            return (
                notion_summary,
                self.client.databases.query(
                    database_id=self.setting["database_id"],
                    filter={
                        "and": [
                            {
                                "property": self.page_property["Date_Notion_Name"],
                                "date": {"before": before_date_with_time_zone},
                            },
                            {
                                "property": self.page_property["GCal_End_Date_Notion_Name"],
                                "formula": {"date": {"on_or_after": after_date_with_time_zone}},
                            },
                        ]
                    },
                )["results"],
            )
        except Exception as e:
            self.logger.error(f"Error reading Notion table: {e}")
            return None

    def get_notion_task_by_gcal_event_id(self, gcal_event_id):
        try:
            self.logger.info(f"Reading Notion database by Google event ID: {gcal_event_id}")
            return self.client.databases.query(
                database_id=self.setting["database_id"],
                filter={
                    "property": self.page_property["GCal_EventId_Notion_Name"],
                    "rich_text": {"equals": gcal_event_id},
                },
            )["results"]
        except Exception as e:
            self.logger.error(f"Error reading Notion table: {e}")
            return None

    def update_notion_task(self, page_id, gcal_event, gcal_cal_name, new_gcal_sync_time):
        """
        Update a Notion task with Google Calendar event details.

        Notes:
            - The function updates the task's title, date, location, and Google Calendar event ID.
            - It also updates the current calendar name.
            - The function handles exceptions and logs errors if any occur.

        Limits:
            - The function does not update the task's extra information from Google Calendar.
        """
        summary_without_emojis = self.remove_emojis(gcal_event.get("summary", ""))
        gcal_event_start_datetime = self.get_event_time(gcal_event, "start")
        gcal_event_end_datetime = self.get_event_time(gcal_event, "end")

        # Adjust end date if it is in the date format. All day event will be the same day
        if "date" in gcal_event["end"]:
            gcal_event_end_datetime = self.adjust_end_date(gcal_event_end_datetime)

        try:
            self.client.pages.update(
                page_id=page_id,
                properties={
                    self.page_property["Task_Notion_Name"]: {
                        "type": "title",
                        "title": [{"type": "text", "text": {"content": summary_without_emojis}}],
                    },
                    self.page_property["Date_Notion_Name"]: {
                        "type": "date",
                        "date": {
                            "start": gcal_event_start_datetime,
                            "end": gcal_event_end_datetime,
                        },
                    },
                    self.page_property["ExtraInfo_Notion_Name"]: {
                        "type": "rich_text",
                        "rich_text": [{"text": {"content": gcal_event.get("description", "")}}],
                    },
                    self.page_property["Location_Notion_Name"]: {
                        "type": "rich_text",
                        "rich_text": [{"text": {"content": gcal_event.get("location", "")}}],
                    },
                    self.page_property["GCal_Sync_Time_Notion_Name"]: {
                        "type": "rich_text",
                        "rich_text": [{"text": {"content": new_gcal_sync_time}}],
                    },
                    self.page_property["GCal_EventId_Notion_Name"]: {
                        "type": "rich_text",
                        "rich_text": [{"text": {"content": gcal_event.get("id", "")}}],
                    },
                    self.page_property["GCal_Name_Notion_Name"]: {
                        "select": {"name": gcal_cal_name},
                    },
                },
            )
        except Exception as e:
            self.logger.error(f"Error updating Notion page when updating Notion Task: {e}")
            return None

    def update_notion_task_for_new_gcal_event_id(self, page_id, new_gcal_event_id):
        try:
            self.client.pages.update(
                page_id=page_id,
                properties={
                    self.page_property["GCal_EventId_Notion_Name"]: {
                        "type": "rich_text",
                        "rich_text": [{"text": {"content": new_gcal_event_id}}],
                    },
                },
            )
        except Exception as e:
            self.logger.error(f"Error updating Notion page when updating for new GCal Event ID: {e}")
            return None

    def update_notion_task_for_new_gcal_sync_time(self, page_id, new_gcal_sync_time):
        try:
            self.client.pages.update(
                page_id=page_id,
                properties={
                    self.page_property["GCal_Sync_Time_Notion_Name"]: {
                        "type": "rich_text",
                        "rich_text": [{"text": {"content": new_gcal_sync_time}}],
                    },
                },
            )
        except Exception as e:
            self.logger.error(f"Error updating Notion page when updating for new GCal sync time: {e}")
            return None

    def update_notion_task_for_default_calendar(self, page_id, default_calendar_name):
        """Update the Notion task for the default calendar."""
        try:
            self.client.pages.update(
                page_id=page_id,
                properties={
                    self.page_property["GCal_Name_Notion_Name"]: {
                        "select": {"name": default_calendar_name},
                    },
                },
            )
        except Exception as e:
            self.logger.error(f"Error updating Notion page when updating for default calendar: {e}")
            return None

    def create_notion_task(self, gcal_event, gcal_cal_name):
        """Create a Notion task using Google Calendar event details."""

        gcal_event_start_datetime = self.get_event_time(gcal_event, "start")
        gcal_event_end_datetime = self.get_event_time(gcal_event, "end")

        # Adjust end date if it is in the date format. All day event will be the same day
        if "date" in gcal_event["end"]:
            gcal_event_end_datetime = self.adjust_end_date(gcal_event_end_datetime)

        try:
            self.client.pages.create(
                parent={"database_id": self.setting["database_id"]},
                properties={
                    self.page_property["Task_Notion_Name"]: {
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
                    self.page_property["Date_Notion_Name"]: {
                        "type": "date",
                        "date": {
                            "start": gcal_event_start_datetime,
                            "end": gcal_event_end_datetime,
                        },
                    },
                    self.page_property["ExtraInfo_Notion_Name"]: {
                        "type": "rich_text",
                        "rich_text": [{"text": {"content": gcal_event.get("description", "")}}],
                    },
                    self.page_property["Location_Notion_Name"]: {
                        "type": "rich_text",
                        "rich_text": [{"text": {"content": gcal_event.get("location", "")}}],
                    },
                    self.page_property["GCal_EventId_Notion_Name"]: {
                        "type": "rich_text",
                        "rich_text": [{"text": {"content": gcal_event.get("id")}}],
                    },
                    self.page_property["GCal_Name_Notion_Name"]: {
                        "select": {"name": gcal_cal_name},
                    },
                },
            )
            self.logger.info(f"Event {gcal_event.get('summary', '')} created in Notion successfully.")
        except Exception as e:
            self.logger.error(f"Failed to sync event {gcal_event.get('summary', '')} to Notion: {e}")
            return None

    def delete_notion_task(self, page_id):
        try:
            self.client.pages.update(
                page_id=page_id,
                properties={
                    self.page_property["Delete_Notion_Name"]: {"checkbox": True},
                    self.page_property["GCal_Sync_Time_Notion_Name"]: {
                        "type": "rich_text",
                        "rich_text": [{"text": {"content": ""}}],
                    },
                    self.page_property["GCal_EventId_Notion_Name"]: {
                        "type": "rich_text",
                        "rich_text": [{"text": {"content": ""}}],
                    },
                },
            )
            self.logger.info(f"Event {page_id} marked as deletion in Notion successfully.")
        except Exception as e:
            self.logger.error(f"Failed to marked as deletion {page_id} to Notion: {e}")
            return None

    def parse_date_in_notion_format(self, date_obj):
        """Helper function to notion format dates."""
        try:
            formatted_date = date_obj.strftime(f"%Y-%m-%dT%H:%M:%S{self.setting['timecode']}")
        except Exception as e:
            self.logger.error(f"Error formatting date: {e}")
            formatted_date = None
        return formatted_date

    def get_current_time(self):
        """Helper function to get the current time in the Notion format."""
        return self.parse_date_in_notion_format(datetime.now())

    def get_event_time(self, event, key):
        return event.get(key, {}).get("dateTime") or event.get(key, {}).get("date", "")

    def adjust_end_date(self, end_date):
        try:
            end_date_obj = datetime.strptime(end_date, "%Y-%m-%d")
            adjusted_end_date_obj = end_date_obj - timedelta(days=1)
            return adjusted_end_date_obj.strftime("%Y-%m-%d")
        except ValueError:
            # If the end_date is not in "YYYY-MM-DD" format, return it as is
            return end_date

    def remove_emojis(self, text):
        return emoji.replace_emoji(text, replace="")

    def get_calendar_id(self, name: str) -> str:
        return self.setting["gcal_name_dict"].get(name)

    def get_calendar_name(self, id_: str) -> str:
        return self.setting["gcal_id_dict"].get(id_)

    def get_page_property(self, key: str) -> str:
        return self.setting["page_property"].get(key)


if __name__ == "__main__":
    import sys
    import logging
    import json
    from pathlib import Path

    # python -m src.notion.notion_service
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    from rich.console import Console  # noqa: E402
    from .notion_config import NotionConfig  # noqa: E402
    from .notion_token import NotionToken  # noqa: E402

    # Add the src directory to the Python path
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    from config.config import generate_config  # noqa: E402

    console = Console()
    Path("logs").mkdir(parents=True, exist_ok=True)
    log_path = Path("logs/get_notion_task.json")
    if not log_path.exists():
        log_path.touch()

    config = generate_config("huixinyang")
    nc = NotionConfig(config, logger)
    token = NotionToken(config, logger).token
    user_setting = nc.user_setting
    logger.info(f"Notion User Setting: {user_setting}")
    ns = NotionService(token, user_setting, logger)

    with log_path.open("w") as output:
        data = ns.get_notion_task()
        json.dump(data, output, indent=4)
    logging.info(
        f"Notion Task Count. {len(data)}, from {ns.page_property['GCal_End_Date_Notion_Name']}: {ns.setting['after_date']} "  # noqa: E501
        f"to {ns.page_property['Date_Notion_Name']}: {ns.setting['before_date']} (exclusive)"
    )

    event_id = "4qajal4vgpl92lsl3mnuv76od8"
    result = ns.get_notion_task_by_gcal_event_id(event_id)
    console.print(f"[bold cyan]Notion Task from GCal Event ID:[/] [green]{event_id}[/]")
    console.print(result)
