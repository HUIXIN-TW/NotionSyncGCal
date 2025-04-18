import logging
import os
import pickle
import sys
from datetime import datetime, timezone
import boto3
from io import BytesIO
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from pathlib import Path


class SettingError(Exception):
    """Custom exception to handle setting errors in the Notion class."""

    def __init__(self, message):
        super().__init__(message)


class GoogleToken:
    def __init__(self, config, logger):
        self.credentials = None
        self.config = config
        self.has_s3_google = config.get("has_s3_google")
        self.local_client_secret_path = config.get("local_client_secret_path")
        self.logger = logger
        self.activate_token()

    def activate_token(self):
        credentials = self.load_credentials()
        if credentials:
            if credentials.expired and credentials.refresh_token:
                self.logger.info("Token has expired. Refreshing tokens...")
                credentials = self.refresh_tokens(credentials)
            elif not credentials.valid:
                self.logger.error("Token is invalid and cannot be refreshed.")
                sys.exit()
        else:
            self.logger.error("No credentials available. Exiting.")
            sys.exit()

        self.credentials = credentials

    @property
    def token(self):
        return self.credentials

    def load_credentials(self):
        if not self.config:
            raise SettingError("Configuration is required to load settings.")
        if self.has_s3_google:
            try:
                s3 = boto3.client("s3")
                response = s3.get_object(Bucket=self.config.get("s3_bucket_name"), Key=self.config.get("s3_key_google"))
                credentials = pickle.load(BytesIO(response["Body"].read()))
                self.logger.info("Loaded credentials from S3.")
                return credentials
            except Exception as e:
                self.logger.error(f"Failed to load credentials from S3: {e}")

        local_credentials_path = self.config.get("local_credentials_path")
        if local_credentials_path.exists():
            try:
                with local_credentials_path.open("rb") as f:
                    credentials = pickle.load(f)
                self.logger.info("Loaded credentials from local file.")
                return credentials
            except Exception as e:
                self.logger.error(f"Failed to load credentials from local file: {e}")

        self.logger.warning("No valid credentials found.")
        return None

    def refresh_tokens(self, credentials):
        try:
            credentials.refresh(Request())
            self.save_credentials(credentials)
            self.logger.info("Successfully refreshed tokens.")
        except Exception as e:
            self.logger.error(f"Error refreshing token: {e}")
            if self.has_s3_google:
                self.logger.error("Running on Lambda/S3 — cannot re-auth. Exiting.")
                self.logger.error("Please trigger a manual re-authentication from a local machine.")
                # TODO: Handle re-auth flow for Lambda/S3 by sending an email.
                # raise RuntimeError("Refresh token expired and cannot prompt user for auth")
                sys.exit(1)
            else:
                credentials = self.perform_oauth_flow()
        return credentials

    def perform_oauth_flow(self):
        scopes = ["https://www.googleapis.com/auth/calendar"]
        flow = InstalledAppFlow.from_client_secrets_file(str(self.local_client_secret_path), scopes)
        try:
            self.logger.info("Running OAuth flow...")
            credentials = flow.run_local_server(
                port=0
            )  # flow.run_console() is also an option if running in a non-GUI environment
            self.logger.info("Successfully fetched new tokens.")
        except Exception as e:
            self.logger.error(f"Error during OAuth flow: {e}")
            sys.exit()
        self.save_credentials(credentials)
        return credentials

    def save_credentials(self, credentials):
        buffer = BytesIO()
        pickle.dump(credentials, buffer)
        buffer.seek(0)

        if self.has_s3_google:
            try:
                s3 = boto3.client("s3")
                s3.put_object(
                    Bucket=self.config.get("s3_bucket_name"),
                    Key=self.config.get("s3_key_google"),
                    Body=buffer.getvalue(),
                )
                self.logger.info("Saved credentials to S3.")
                return
            except Exception as e:
                self.logger.error(f"Failed to save credentials to S3: {e}")

        try:
            local_credentials_path = self.config.get("local_credentials_path")
            if local_credentials_path.exists():
                os.remove(local_credentials_path)
                self.logger.info("Removed existing credentials file.")
            with local_credentials_path.open("wb") as token:
                pickle.dump(credentials, token)
                self.logger.info("Saved credentials to local file.")
        except Exception as e:
            self.logger.error(f"Error saving credentials to local file: {e}")


if __name__ == "__main__":
    # python -m src.gcal.gcal_token
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    # google
    from googleapiclient.discovery import build

    # Add the src directory to the Python path
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    from config.config import CONFIG  # noqa: E402

    gt = GoogleToken(CONFIG, logger)
    service = build("calendar", "v3", credentials=gt.token)
    if service:
        logger.info("Google Calendar service is ready to use.")
    else:
        logger.error("Failed to initialize Google Calendar service.")
    events_result = (
        service.events()
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
