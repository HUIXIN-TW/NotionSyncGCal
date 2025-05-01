import logging
import os
import json
import sys
from datetime import datetime, timezone
import boto3
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
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
                # fmt: off
                self.logger.info(f"Loaded credentials from S3: {self.config.get('s3_bucket_name')}/{self.config.get('s3_credentials_path')}")  # noqa: E501
                # fmt: on
                s3 = boto3.client("s3")
                response = s3.get_object(
                    Bucket=self.config.get("s3_bucket_name"), Key=self.config.get("s3_credentials_path")
                )
                credentials_data = json.loads(response.get("Body").read().decode("utf-8"))
                credentials = Credentials(**credentials_data)
                return credentials
            except Exception as e:
                # fmt: off
                self.logger.error(f"Failed to load credentials from S3: {e}, {self.config.get('s3_bucket_name')}/{self.config.get('s3_credentials_path')}")  # noqa: E501
                # fmt: on

        local_credentials_path = self.config.get("local_credentials_path")
        if local_credentials_path.exists():
            try:
                with local_credentials_path.open("r") as f:
                    credentials_data = json.load(f)
                credentials = Credentials(**credentials_data)
                self.logger.info(f"Loaded credentials from local file: {local_credentials_path}")
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
                # On Lambda/S3, raise error when refresh token is invalid
                sys.exit()
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
        # serialize credentials as JSON
        payload = {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "scopes": credentials.scopes,
        }
        json_buffer = json.dumps(payload).encode()

        if self.has_s3_google:
            try:
                s3 = boto3.client("s3")
                s3.put_object(
                    Bucket=self.config.get("s3_bucket_name"),
                    Key=self.config.get("s3_credentials_path"),
                    Body=json_buffer,
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
            with local_credentials_path.open("w") as token:
                json.dump(payload, token)
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
    from config.config import generate_uuid_config  # noqa: E402

    config = generate_uuid_config("huixinyang")
    gt = GoogleToken(config, logger)
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
