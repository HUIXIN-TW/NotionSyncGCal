import logging
import os
import pickle
import sys
from datetime import datetime, timezone
import boto3
from io import BytesIO
from google.auth.transport.requests import Request
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

# --- ENV Setup ---
S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME")
S3_CLIENT_SECRET_PATH = os.environ.get("S3_CLIENT_SECRET_PATH")
S3_CREDENTIALS_PATH = os.environ.get("S3_CREDENTIALS_PATH")
USE_S3 = bool(S3_BUCKET_NAME and S3_CLIENT_SECRET_PATH and S3_CREDENTIALS_PATH)

# Construct the absolute file paths within the container
CLIENT_SECRET_PATH = Path(os.environ.get("CLIENT_SECRET_PATH", CURRENT_DIR / "../../token/client_secret.json"))
CREDENTIALS_PATH = Path(os.environ.get("CREDENTIALS_PATH", CURRENT_DIR / "../../token/token.pkl"))


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
        if USE_S3:
            try:
                s3 = boto3.client("s3")
                response = s3.get_object(Bucket=S3_BUCKET_NAME, Key=S3_CREDENTIALS_PATH)
                credentials = pickle.load(BytesIO(response["Body"].read()))
                logger.info("Loaded credentials from S3.")
                return credentials
            except Exception as e:
                logger.error(f"Failed to load credentials from S3: {e}")

        if CREDENTIALS_PATH.exists():
            try:
                with CREDENTIALS_PATH.open("rb") as f:
                    credentials = pickle.load(f)
                logger.info("Loaded credentials from local file.")
                return credentials
            except Exception as e:
                logger.error(f"Failed to load credentials from local file: {e}")

        logger.warning("No valid credentials found.")
        return None

    def refresh_tokens(self, credentials):
        try:
            credentials.refresh(Request())
            self.save_credentials(credentials)
            logger.info("Successfully refreshed tokens.")
        except Exception as e:
            logger.error(f"Error refreshing token: {e}")
            if USE_S3:
                logger.error("Running on Lambda/S3 — cannot re-auth. Exiting.")
                logger.error("Please trigger a manual re-authentication from a local machine.")
                # TODO: Handle re-auth flow for Lambda/S3 by sending an email.
                # raise RuntimeError("Refresh token expired and cannot prompt user for auth")
                sys.exit(1)
            else:
                credentials = self.perform_oauth_flow()
        return credentials

    def perform_oauth_flow(self):
        scopes = ["https://www.googleapis.com/auth/calendar"]
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_PATH), scopes)
        try:
            logger.info("Running OAuth flow...")
            credentials = flow.run_local_server(
                port=0
            )  # flow.run_console() is also an option if running in a non-GUI environment
            logger.info("Successfully fetched new tokens.")
        except Exception as e:
            logger.error(f"Error during OAuth flow: {e}")
            sys.exit()
        self.save_credentials(credentials)
        return credentials

    def save_credentials(self, credentials):
        buffer = BytesIO()
        pickle.dump(credentials, buffer)
        buffer.seek(0)

        if USE_S3:
            try:
                s3 = boto3.client("s3")
                s3.put_object(
                    Bucket=S3_BUCKET_NAME,
                    Key=S3_CREDENTIALS_PATH,
                    Body=buffer.getvalue(),
                )
                logger.info("Saved credentials to S3.")
                return
            except Exception as e:
                logger.error(f"Failed to save credentials to S3: {e}")

        try:
            if CREDENTIALS_PATH.exists():
                os.remove(CREDENTIALS_PATH)
                logger.info("Removed existing credentials file.")
            with CREDENTIALS_PATH.open("wb") as token:
                pickle.dump(credentials, token)
                logger.info("Saved credentials to local file.")
        except Exception as e:
            logger.error(f"Error saving credentials to local file: {e}")


if __name__ == "__main__":
    google_instance = Google()
    if google_instance.service:
        logger.info("Google Calendar service is ready to use.")
    else:
        logger.error("Failed to initialize Google Calendar service.")
    events_result = (
        google_instance.service.events()
        .list(
            calendarId="primary",
            maxResults=1,
            timeMin=datetime.now(timezone.utc).isoformat(),
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    events = events_result.get("items", [])
    if not events:
        logger.info("No upcoming events found.")
    else:
        logger.info(f"Next event: {events[0]['summary']}")
