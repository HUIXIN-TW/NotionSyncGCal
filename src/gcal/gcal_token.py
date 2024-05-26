import json
import logging
import os
import pickle
import sys
from datetime import timedelta, date, datetime
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
CURRENT_DIR = Path(__file__).parent.resolve()
logger.info(f"Current directory: {CURRENT_DIR}")

# Construct the absolute file paths within the container
NOTION_SETTINGS_PATH = (CURRENT_DIR / "../../token/notion_setting.json").resolve()
CLIENT_SECRET_PATH = (CURRENT_DIR / "../../token/client_secret.json").resolve()
CREDENTIALS_PATH = (CURRENT_DIR / "../../token/token.pkl").resolve()

# google API setting
class Google:

    def __init__(self):
        try:
            with open(NOTION_SETTINGS_PATH, encoding="utf-8") as f:
                data = json.load(f)
            self.DOCKER = data.get("docker", False)
        except FileNotFoundError as e:
            logger.error(f"Notion settings file not found: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON from Notion settings: {e}")
        except Exception as e:
            logger.error(f"Unexpected error loading Notion settings: {e}")

        self.service = self.init_google_service()

    def init_google_service(self):
        try:
            credentials = self.load_credentials()

            # Check if the token is expired or invalid
            if not credentials or not credentials.valid:
                if credentials and credentials.expired and credentials.refresh_token:
                    logger.info("Token has expired. Refreshing tokens...")
                    credentials = self.refresh_tokens()
                else:
                    logger.error("Token is invalid and cannot be refreshed.")
                    sys.exit()
            self.service = build("calendar", "v3", credentials=credentials)

        except Exception as e:
            logger.error(f"Error initializing Google service: {e}")
            sys.exit()

        except Exception as e:
            logger.error(e)
            sys.exit()

    def load_credentials(self):
        """Load credentials from the file."""
        if CREDENTIALS_PATH.exists():
            try:
                with CREDENTIALS_PATH.open("rb") as f:
                    return pickle.load(f)
                logger.info("Successfully loaded credentials.")
            except (pickle.PickleError, FileNotFoundError) as e:
                logger.error(f"Error loading credentials: {e}")
        logger.info("No credentials found.")
        return None

    def refresh_tokens(self):
        """Refresh Google API tokens."""
        scopes = ["https://www.googleapis.com/auth/calendar"]
        credentials = self.load_credentials()

        if credentials and (credentials.expired or credentials.refresh_token):
            try:
                credentials.refresh(Request())
                logger.info("Successfully refreshed tokens.")
            except Exception as e:
                logger.error(f"Error refreshing token: {e}")
                sys.exit()

        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRET_PATH), scopes)
            try:
                credentials = flow.run_console(
                ) if self.DOCKER else flow.run_local_server(port=0)
            except Exception as e:
                logger.error(f"Error during OAuth flow: {e}")
                auth_url, _ = flow.authorization_url(prompt='consent')
                print(
                    "Please go to this URL and finish the authentication process:",
                    auth_url)
                auth_code = input("Enter the authentication code: ")
                try:
                    flow.fetch_token(code=auth_code)
                    credentials = flow.credentials
                except Exception as e:
                    logger.error(f"Error fetching token with auth code: {e}")
                    sys.exit()

        if CREDENTIALS_PATH.exists():
            os.remove(CREDENTIALS_PATH)
        with CREDENTIALS_PATH.open("wb") as token:
            logger.info("Saving the credentials for the next run")
            pickle.dump(credentials, token)
        return credentials

if __name__ == "__main__":
    # Debug check if it works
    google_instance = Google()
    google_instance.refresh_tokens()
