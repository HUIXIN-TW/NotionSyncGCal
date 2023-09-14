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
CURRENT_DIR = Path(__file__).parent

# Construct the absolute file paths within the container
NOTION_SETTINGS_PATH = CURRENT_DIR / "../token/notion_setting.json"
CLIENT_SECRET_PATH = CURRENT_DIR / "../token/client_secret.json"
CREDENTIALS_PATH = CURRENT_DIR / "../token/token.pkl"


class SettingError(Exception):
    """Custom exception to handle setting errors in the Notion class."""

    def __init__(self, message):
        super().__init__(message)


class Notion:
    # URLROOT = DATABASE_ID = TIMECODE = TIMEZONE = NOTION = None

    def __init__(self):
        self.filepath = NOTION_SETTINGS_PATH
        self.data = self.load_settings()
        self.setup_logging()
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

    def setup_logging(self):
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
            self.AFTER_DATE = (
                date.today() + timedelta(days=-self.data["goback_days"])
            ).strftime("%Y-%m-%d")
            self.BEFORE_DATE = (
                date.today() + timedelta(days=self.data["goforward_days"])
            ).strftime("%Y-%m-%d")
            self.GOOGLE_TIMEMIN = (
                date.today() + timedelta(days=-self.data["goback_days"])
            ).strftime(f"%Y-%m-%dT%H:%M:%S{self.TIMECODE}")
            self.GOOGLE_TIMEMAX = (
                date.today() + timedelta(days=self.data["goforward_days"])
            ).strftime(f"%Y-%m-%dT%H:%M:%S{self.TIMECODE}")

            # Other settings
            self.DELETE_OPTION = self.data["delete_option"]
            self.DEFAULT_EVENT_LENGTH = self.data["default_event_length"]
            self.DEFAULT_EVENT_START = self.data["default_start_time"]
            self.ALLDAY_OPTION = self.data["allday_option"]

            # Google calendar settings
            self.GCAL_DIC = self.data["gcal_dic"][0]
            self.GCAL_DIC_KEY_TO_VALUE = self.gcal_dic_key_to_value(
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
            self.ON_GCAL_NOTION_NAME = page_property["On_GCal_Notion_Name"]
            self.NEEDGCALUPDATE_NOTION_NAME = page_property[
                "NeedGCalUpdate_Notion_Name"
            ]
            self.GCALEVENTID_NOTION_NAME = page_property["GCalEventId_Notion_Name"]
            self.LASTUPDATEDTIME_NOTION_NAME = page_property[
                "LastUpdatedTime_Notion_Name"
            ]
            self.CALENDAR_NOTION_NAME = page_property["Calendar_Notion_Name"]
            self.CURRENT_CALENDAR_ID_NOTION_NAME = page_property[
                "Current_Calendar_Id_Notion_Name"
            ]
            self.DELETE_NOTION_NAME = page_property["Delete_Notion_Name"]
            self.STATUS_NOTION_NAME = page_property["Status_Notion_Name"]
            self.PAGE_ID_NOTION_NAME = page_property["Page_ID_Notion_Name"]
            self.COMPLETEICON_NOTION_NAME = page_property["CompleteIcon_Notion_Name"]

            # Description settings
            self.SKIP_DESCRIPTION_CONDITION = self.data["skip_description_condition"]
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

    def get_database_id(self, url):
        """Extracts the database ID from the Notion URL."""
        pattern = r"https://www.notion.so/[^/]+/([^?]+)"
        match = re.search(pattern, url)
        if match:
            return match.group(1)
        else:
            self.logger.error("Failed to extract database ID from URL")
            raise SettingError("Failed to extract database ID from URL")

    def gcal_dic_key_to_value(self, gcal_dic):
        key_to_value = {}
        for key in gcal_dic:
            key_to_value[gcal_dic[key]] = key
        return key_to_value

    def test_settings(self):
        """Tests if all settings were applied correctly."""
        # Implement tests for your settings here
        pass

    def get_string(self):
        print(f"Default calendar: {self.GCAL_DEFAULT_NAME}")
        logger.info("--- Token Notion Activated ---")


# Usage:
# filepath = "path/to/your/settings/file.json"
# notion = Notion(filepath)
# notion.validate_settings()
