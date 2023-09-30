import json
import logging
import os
import pickle
import sys
from datetime import timedelta, date
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)

# Get the absolute path to the current directory
CURRENT_DIR = Path(__file__).parent

# Construct the absolute file paths within the container
NOTION_SETTINGS_PATH = CURRENT_DIR / "../token/notion_setting.json"
CLIENT_SECRET_PATH = CURRENT_DIR / "../token/client_secret.json"
CREDENTIALS_PATH = CURRENT_DIR / "../token/token.pkl"


# google API setting
class Google:
    def __init__(self):
        try:
            with open(NOTION_SETTINGS_PATH, encoding="utf-8") as f:
                data = json.load(f)
            self.DOCKER = data.get("docker", False)
            self.GCAL_DIC_KEY_TO_VALUE = self.gcal_dic_key_to_value(data["gcal_dic"][0])
            self.GCAL_DEFAULT_ID = list(self.GCAL_DIC_KEY_TO_VALUE)[0]
        except Exception as e:
            logger.error(e)

        self.service = self.init_google_service()

    def init_google_service(self):
        try:
            credentials = None

            # check if token.pkl exists
            if CREDENTIALS_PATH.exists():
                with CREDENTIALS_PATH.open("rb") as f:
                    credentials = pickle.load(f)
            
                # Check if the token is expired or invalid
                if not credentials.valid:
                    if credentials.expired and credentials.refresh_token:
                        logger.info("Token has expired. Refreshing tokens...")
                        self.refresh_tokens()
                        with CREDENTIALS_PATH.open("rb") as f:
                            credentials = pickle.load(f)
                    else:
                        logger.error("Token is invalid and cannot be refreshed.")
                        sys.exit()
            else:
                logger.info("No existing token found. Refreshing tokens...")
                self.refresh_tokens()
                with CREDENTIALS_PATH.open("rb") as f:
                    credentials = pickle.load(f)

            service = build("calendar", "v3", credentials=credentials)
            return service
            
        except Exception as e:
            logger.error(e)
            sys.exit()

    def refresh_tokens(self):
        """Method to refresh Google API tokens."""
        scopes = ["https://www.googleapis.com/auth/calendar"]
        creds = None
        if CREDENTIALS_PATH.exists():
            try:
                creds = Credentials.from_authorized_user_file(
                    str(CREDENTIALS_PATH), scopes
                )
            except:
                CREDENTIALS_PATH.unlink()

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(CLIENT_SECRET_PATH), scopes
                )
                creds = (
                    flow.run_console() if self.DOCKER else flow.run_local_server(port=0)
                )
            logger.info("------------------Refresh tokens------------------")
            with CREDENTIALS_PATH.open("wb") as token:
                logger.info("Save the credentials for the next run")
                pickle.dump(creds, token)

    def gcal_dic_key_to_value(self, gcal_dic):
        return {value: key for key, value in gcal_dic.items()}

    def get_string(self):
        logger.info("--- Token Google Activated ---")

    def test_settings(self):
        """Tests if all settings were applied correctly."""
        # Implement tests for your settings here
        pass


if __name__ == "__main__":
    g = Google()
    g.refresh_tokens()
