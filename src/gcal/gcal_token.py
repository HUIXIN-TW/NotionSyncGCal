import json
import logging
import os
import pickle
import sys
from datetime import datetime, timedelta
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
CLIENT_SECRET_PATH = (CURRENT_DIR / "../../token/client_secret.json").resolve()
CREDENTIALS_PATH = (CURRENT_DIR / "../../token/token.pkl").resolve()


class Google:
    def __init__(self):
        self.service = None
        self.init_google_service()

    def init_google_service(self):
        credentials = self.load_credentials()
        if credentials:
            if credentials.expired and credentials.refresh_token:
                logger.info("Token has expired. Refreshing tokens...")
                credentials = self.refresh_tokens(credentials)
            elif not credentials.valid:
                logger.error("Token is invalid and cannot be refreshed.")
                sys.exit()
        else:
            logger.error("No credentials available. Exiting.")
            sys.exit()

        try:
            self.service = build("calendar", "v3", credentials=credentials)
            logger.info("Google Calendar service initialized successfully.")
        except Exception as e:
            logger.error(f"Error initializing Google service: {e}")
            sys.exit()

    def load_credentials(self):
        if CREDENTIALS_PATH.exists():
            try:
                with CREDENTIALS_PATH.open("rb") as f:
                    credentials = pickle.load(f)
                logger.info("Successfully loaded credentials.")
                return credentials
            except (pickle.PickleError, FileNotFoundError) as e:
                logger.error(f"Error loading credentials: {e}")
        logger.info("No credentials found.")
        return None

    def refresh_tokens(self, credentials):
        try:
            credentials.refresh(Request())
            self.save_credentials(credentials)
            logger.info("Successfully refreshed tokens.")
        except Exception as e:
            logger.error(f"Error refreshing token: {e}")
            credentials = self.perform_oauth_flow()
        return credentials

    def perform_oauth_flow(self):
        scopes = ["https://www.googleapis.com/auth/calendar"]
        flow = InstalledAppFlow.from_client_secrets_file(
            str(CLIENT_SECRET_PATH), scopes
        )
        try:
            logger.info("Running OAuth flow...")
            credentials = (
                flow.run_console() if self.DOCKER else flow.run_local_server(port=0)
            )
            logger.info("Successfully fetched new tokens.")
        except Exception as e:
            logger.error(f"Error during OAuth flow: {e}")
            sys.exit()
        self.save_credentials(credentials)
        return credentials

    def save_credentials(self, credentials):
        try:
            if CREDENTIALS_PATH.exists():
                os.remove(CREDENTIALS_PATH)
                logger.info("Removed existing credentials file.")
            with CREDENTIALS_PATH.open("wb") as token:
                pickle.dump(credentials, token)
                logger.info("Saved credentials to file.")
        except Exception as e:
            logger.error(f"Error saving credentials to file: {e}")


if __name__ == "__main__":
    google_instance = Google()
    if google_instance.service:
        logger.info("Google Calendar service is ready to use.")
    else:
        logger.error("Failed to initialize Google Calendar service.")
