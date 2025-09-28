import logging
import json
import sys
from datetime import timedelta
from dateutil.parser import isoparse
from googleapiclient.discovery import build
from google.auth.exceptions import RefreshError
from pathlib import Path


class SettingError(Exception):
    """Custom exception to handle setting errors in the Notion class."""

    def __init__(self, message):
        super().__init__(message)


class GoogleService:

    def __init__(self, user_setting, google_token, logger):
        self.logger = logger
        self.notion_setting = user_setting
        self.notion_page_property = user_setting["page_property"]
        try:
            self.service = build("calendar", "v3", credentials=google_token.credentials)
            self.logger.debug("Google Calendar service initialized successfully.")
        except Exception as e:
            self.logger.error(f"Error initializing Google service: {e}")
            raise

    def get_gcal_event(self):
        # Calculate the start and end dates for the event range
        try:
            events = []
            for cal_id in self.notion_setting["gcal_name_dict"].values():
                response = (
                    self.service.events()
                    .list(
                        calendarId=cal_id,
                        timeMin=self.notion_setting["google_timemin"],
                        timeMax=self.notion_setting["google_timemax"],
                    )
                    .execute()
                )

                if response.get("items"):
                    events.extend(response["items"])
                self.logger.debug(f"Retrieved {len(response.get('items', []))} events from calendar ID {cal_id}")

            self.logger.debug(f"Total events retrieved: {len(events)}")
            return events
        except RefreshError as e:
            self.logger.error(f"RefreshError: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Error retrieving Google Calendar events: {e}")
            raise

    def update_gcal_event(self, notion_task, existing_gcal_cal_id, existing_gcal_event_id):
        event = self.make_event_body(notion_task)
        self.service.events().update(
            calendarId=existing_gcal_cal_id, eventId=existing_gcal_event_id, body=event
        ).execute()

    def create_gcal_event(self, notion_task, new_gcal_calendar_id):
        if new_gcal_calendar_id is None:
            new_gcal_calendar_id = self.notion_setting["gcal_default_id"]
        event = self.make_event_body(notion_task)
        gcal_event = self.service.events().insert(calendarId=new_gcal_calendar_id, body=event).execute()
        # get the event id and update the notion task by query page id
        event_id = gcal_event.get("id")
        return event_id

    def move_and_update_gcal_event(
        self, notion_task, existing_gcal_event_id, new_gcal_calendar_id, existing_gcal_cal_id
    ):
        self.service.events().move(
            calendarId=existing_gcal_cal_id,
            eventId=existing_gcal_event_id,
            destination=new_gcal_calendar_id,
        ).execute()
        self.update_gcal_event(notion_task, new_gcal_calendar_id, existing_gcal_event_id)

    def delete_gcal_event(self, gcal_calendar_id, gcal_event_id):
        try:
            self.service.events().delete(calendarId=gcal_calendar_id, eventId=gcal_event_id).execute()
            self.logger.info(f"Successfully deleted event with ID: {gcal_event_id}")
        except Exception as e:
            self.logger.error(f"An error occurred while deleting event with ID: {gcal_event_id}: {e}")

    def make_event_body(self, notion_task):
        # set icone and task name
        event_icon = (
            notion_task.get("properties", {})
            .get(self.notion_page_property["CompleteIcon_Notion_Name"], {})
            .get("formula", {})
            .get("string", "❓")
        )
        event_name = (
            notion_task.get("properties", {})
            .get(self.notion_page_property["Task_Notion_Name"], {})
            .get("title", [{}])[0]
            .get("text", {})
            .get("content", "")
        )
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
        notion_task_start_date = (
            notion_task.get("properties", {})
            .get(self.notion_page_property["Date_Notion_Name"], {})
            .get("date", {})
            .get("start", "")
        )
        notion_task_end_date = (
            notion_task.get("properties", {})
            .get(self.notion_page_property["Date_Notion_Name"], {})
            .get("date", {})
            .get("end", "")
        )
        # Adjust and convert dates to UTC
        event_start_date, event_end_date = self.adjust_notion_dates(notion_task_start_date, notion_task_end_date)

        # set location
        try:
            event_location = (
                notion_task.get("properties", {})
                .get(self.notion_page_property["Location_Notion_Name"], {})
                .get("rich_text", [])[0]
                .get("text", {})
                .get("content", "")
            )
        except Exception as e:
            self.logger.info(f"Getting location: {e}. Using empty string.")
            event_location = ""

        # set description
        try:
            event_description = (
                notion_task.get("properties", {})
                .get(self.notion_page_property["ExtraInfo_Notion_Name"], {})
                .get("rich_text", [{}])[0]
                .get("text", {})
                .get("content", "")
            )
        except Exception as e:
            self.logger.info(f"Getting description: {e}. Using empty string.")
            event_description = ""

        # set url
        event_source_url = notion_task.get("url", "")

        timezone = self.notion_setting["timezone"]
        if "T" in event_start_date:
            event = {
                "summary": event_summary,
                "location": event_location,
                "description": event_description,
                "start": {
                    "dateTime": event_start_date,
                    "timeZone": timezone,
                },
                "end": {
                    "dateTime": event_end_date,
                    "timeZone": timezone,
                },
                "source": {
                    "title": "Notion Link",
                    "url": event_source_url,
                },
            }
        else:
            event = {
                "summary": event_summary,
                "location": event_location,
                "description": event_description,
                "start": {"date": event_start_date},
                "end": {"date": event_end_date},
                "source": {
                    "title": "Notion Link",
                    "url": event_source_url,
                },
            }
        return event

    def adjust_notion_dates(self, start_date_str, end_date_str=None):
        """
        TODO: Consider Different Timezones
        Adjust Notion date or datetime formats and convert them to UTC.
        """
        start_date = isoparse(start_date_str)
        if end_date_str:
            end_date = isoparse(end_date_str)
        else:
            end_date = start_date

        if "T" in start_date_str and end_date == start_date:  # datetime format
            end_date = start_date + timedelta(minutes=self.notion_setting["default_event_length"])
        elif "T" not in start_date_str and end_date == start_date:  # date format
            end_date = start_date + timedelta(days=1)

        if "T" in start_date_str:
            start_date_str = start_date.strftime("%Y-%m-%dT%H:%M:%S%z")
            end_date_str = end_date.strftime("%Y-%m-%dT%H:%M:%S%z")
        else:
            start_date_str = start_date.strftime("%Y-%m-%d")
            end_date_str = end_date.strftime("%Y-%m-%d")
        return start_date_str, end_date_str


# Example usage
if __name__ == "__main__":
    # python -m src.gcal.gcal_service
    logging.basicConfig(filename="google_services.log", level=logging.INFO)
    logger = logging.getLogger(__name__)
    # Ensure the directory exists
    Path("logs").mkdir(parents=True, exist_ok=True)

    # Check if the file exists and create it if not
    log_path = Path("logs/get_gcal_event.json")
    if not log_path.exists():
        log_path.touch()

    # Add the src directory to the Python path
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    from config.config import generate_uuid_config  # noqa: E402
    from notion.notion_config import NotionConfig  # noqa: E402
    from gcal.gcal_token import GoogleToken  # noqa: E402

    config = generate_uuid_config("huixinyang")
    nt = NotionConfig(config, logger)
    gt = GoogleToken(config, logger)
    user_setting = nt.user_setting
    gs = GoogleService(user_setting, gt, logger)
    # Open the file in write mode and dump JSON data
    with log_path.open("w") as output:
        json.dump(gs.get_gcal_event(), output, indent=4)

    from rich.console import Console
    from rich.pretty import pprint

    console = Console()
    console.rule("[bold blue]Google Calendar Events[/bold blue]")
    pprint(gs.get_gcal_event())
    pprint(nt.user_setting)
