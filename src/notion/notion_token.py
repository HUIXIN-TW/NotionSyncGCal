import os
import re
import json
import logging
from notion_client import Client
from datetime import timedelta, date
from pathlib import Path


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Get the absolute path to the current directory
CURRENT_DIR = Path(__file__).parent.resolve()
logger.info(f"Current directory: {CURRENT_DIR}")

# Construct the absolute file paths within the container
NOTION_SETTINGS_PATH = (CURRENT_DIR / "../../token/notion_setting.json").resolve()


class SettingError(Exception):
    """Custom exception to handle setting errors in the Notion class."""

    def __init__(self, message):
        super().__init__(message)


class Notion:

    def __init__(self):
        self.filepath = NOTION_SETTINGS_PATH
        self.data = self.load_settings()
        self.set_logging()
        self.apply_settings()
        self.init_notion_client()

    def load_settings(self):
        """Load settings from a JSON file."""
        try:
            with open(self.filepath, encoding="utf-8") as f:
                data = json.load(f)
                return data
        except Exception as e:
            raise SettingError(f"Error loading settings file: {e}")

    def set_logging(self):
        """Sets up logging for the Notion class."""
        self.logger = logging.getLogger("Notion")
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)

    def apply_settings(self):
        """Applies settings from the data dictionary to attributes of the Notion class."""
        try:
            self.URLROOT = self.data["urlroot"]
            self.DATABASE_ID = self.get_database_id(self.data["urlroot"])
            self.TIMECODE = self.data["timecode"]
            self.TIMEZONE = self.data["timezone"]

            # Date range settings
            # ISO format for Notion API
            self.AFTER_DATE = (
                date.today() + timedelta(days=-self.data["goback_days"])
            ).strftime("%Y-%m-%d")
            self.BEFORE_DATE = (
                date.today() + timedelta(days=self.data["goforward_days"])
            ).strftime("%Y-%m-%d")

            # ISO format for Google Calendar API
            self.GOOGLE_TIMEMIN = (
                date.today() + timedelta(days=-self.data["goback_days"])
            ).strftime(f"%Y-%m-%dT%H:%M:%S{self.TIMECODE}")
            self.GOOGLE_TIMEMAX = (
                date.today() + timedelta(days=self.data["goforward_days"])
            ).strftime(f"%Y-%m-%dT%H:%M:%S{self.TIMECODE}")

            # Event default settings
            self.DEFAULT_EVENT_LENGTH = self.data["default_event_length"]
            self.DEFAULT_EVENT_START = self.data["default_start_time"]

            # Google calendar settings
            self.GCAL_DIC = self.data["gcal_dic"][0]
            self.GCAL_DIC_KEY_TO_VALUE = self.convert_key_to_value(
                self.data["gcal_dic"][0]
            )
            self.GCAL_DEFAULT_NAME = list(self.GCAL_DIC)[0]
            self.GCAL_DEFAULT_ID = list(self.GCAL_DIC_KEY_TO_VALUE)[0]

            # Database specific settings
            page_property = self.data["page_property"][0]
            self.TASK_NOTION_NAME = page_property["Task_Notion_Name"]
            self.DATE_NOTION_NAME = page_property["Date_Notion_Name"]
            self.INITIATIVE_NOTION_NAME = page_property["Initiative_Notion_Name"]
            self.EXTRAINFO_NOTION_NAME = page_property["ExtraInfo_Notion_Name"]
            self.LOCATION_NOTION_NAME = page_property["Location_Notion_Name"]
            self.GCAL_EVENTID_NOTION_NAME = page_property["GCal_EventId_Notion_Name"]
            self.CURRENT_CALENDAR_NAME_NOTION_NAME = page_property[
                "GCal_Name_Notion_Name"
            ]
            self.CURRENT_CALENDAR_ID_NOTION_NAME = page_property["GCal_Id_Notion_Name"]
            self.DELETE_NOTION_NAME = page_property["Delete_Notion_Name"]
            self.STATUS_NOTION_NAME = page_property["Status_Notion_Name"]
            self.GCAL_SYNC_TIME_NOTION_NAME = page_property["GCal_Sync_Time_Notion_Name"]
            self.COMPLETEICON_NOTION_NAME = page_property["CompleteIcon_Notion_Name"]
        except KeyError as e:
            self.logger.error(f"Failed to apply setting: {e}")
            raise SettingError(f"Failed to apply setting: {e}")

    def init_notion_client(self):
        """Initializes the Notion client using the token from the data dictionary."""
        try:
            self.NOTION = Client(auth=self.data["notion_token"])
        except Exception as e:
            self.logger.error(f"Failed to initialize Notion client: {e}")
            raise SettingError(f"Failed to initialize Notion client: {e}")

    def convert_key_to_value(self, gcal_dic):
        return {value: key for key, value in gcal_dic.items()}

    def get_cal_name(self, cal_id):
        return self.GCAL_DIC_KEY_TO_VALUE.get(cal_id)

    def get_cal_id(self, cal_name):
        return self.GCAL_DIC.get(cal_name)

    def get_database_id(self, url):
        """Extracts the database ID from the Notion URL."""
        pattern = r"https://www.notion.so/[^/]+/([^?]+)"
        match = re.search(pattern, url)
        if match:
            return match.group(1)
        else:
            self.logger.error("Failed to extract database ID from URL")
            raise SettingError("Failed to extract database ID from URL")

    def get_auth_status(self):
        list_users_response = self.NOTION.users.list()
        print(list_users_response)

    def get_string(self):
        # print all apply_settings() variables
        print(f"URLROOT: {self.URLROOT}")
        print(f"DATABASE_ID: {self.DATABASE_ID}")
        print(f"TIMECODE: {self.TIMECODE}")
        print(f"TIMEZONE: {self.TIMEZONE}")

        # Date range settings
        print(f"AFTER_DATE: {self.AFTER_DATE}")
        print(f"BEFORE_DATE: {self.BEFORE_DATE}")
        print(f"GOOGLE_TIMEMIN: {self.GOOGLE_TIMEMIN}")
        print(f"GOOGLE_TIMEMAX: {self.GOOGLE_TIMEMAX}")

        # Event default settings
        print(f"DEFAULT_EVENT_LENGTH: {self.DEFAULT_EVENT_LENGTH}")
        print(f"DEFAULT_EVENT_START: {self.DEFAULT_EVENT_START}")
        print(f"GCAL_DIC: {self.GCAL_DIC}")
        print(f"GCAL_DIC_KEY_TO_VALUE: {self.GCAL_DIC_KEY_TO_VALUE}")
        print(f"GCAL_DEFAULT_NAME: {self.GCAL_DEFAULT_NAME}")
        print(f"GCAL_DEFAULT_ID: {self.GCAL_DEFAULT_ID}")

        # Database specific settings
        print(f"TASK_NOTION_NAME: {self.TASK_NOTION_NAME}")
        print(f"DATE_NOTION_NAME: {self.DATE_NOTION_NAME}")
        print(f"INITIATIVE_NOTION_NAME: {self.INITIATIVE_NOTION_NAME}")
        print(f"EXTRAINFO_NOTION_NAME: {self.EXTRAINFO_NOTION_NAME}")
        print(f"LOCATION_NOTION_NAME: {self.LOCATION_NOTION_NAME}")
        print(f"GCAL_EVENTID_NOTION_NAME: {self.GCAL_EVENTID_NOTION_NAME}")
        print(
            f"CURRENT_CALENDAR_NAME_NOTION_NAME: {self.CURRENT_CALENDAR_NAME_NOTION_NAME}"
        )
        print(
            f"CURRENT_CALENDAR_ID_NOTION_NAME: {self.CURRENT_CALENDAR_ID_NOTION_NAME}"
        )
        print(f"DELETE_NOTION_NAME: {self.DELETE_NOTION_NAME}")
        print(f"STATUS_NOTION_NAME: {self.STATUS_NOTION_NAME}")
        print(f"GCAL_SYNC_TIME_NOTION_NAME: {self.GCAL_SYNC_TIME_NOTION_NAME}")
        print(f"COMPLETEICON_NOTION_NAME: {self.COMPLETEICON_NOTION_NAME}")
        logger.info("--- Token Notion Activated ---")


if __name__ == "__main__":
    # Initialize the Notion class
    notion = Notion()
    notion.get_auth_status()
    notion.get_string()
