import logging
import os
import json
import sys
from datetime import datetime, timezone
import boto3
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.exceptions import RefreshError
from pathlib import Path


class SettingError(Exception):
    """Custom exception to handle setting errors in the Notion class."""

    def __init__(self, message):
        super().__init__(message)


class GoogleToken:
    def __init__(self, config, logger):
        self.credentials = None
        self.config = config
        self.has_s3_google = config.get("has_s3_google", "")
        self.local_client_secret_path = config.get("local_client_secret_path", "")
        self.local_credentials_path = config.get("local_credentials_path", "")
        self.logger = logger
        self.activate_token()

    def activate_token(self):
        credentials = self.load_credentials()
        if not credentials and not self.has_s3_google:
            credentials = self.perform_oauth_flow()
        elif not credentials and self.has_s3_google:
            self.logger.error(
                "No credentials found on S3. Cannot proceed `perform_oauth_flow`. Please use Web UI to re-authenticate."
            )
            sys.exit(1)
        self.logger.info(
            f"Credentials Expired: {credentials.expired}, Has Refresh Token: {bool(credentials.refresh_token)}"
        )
        if credentials.expired and credentials.refresh_token:
            self.logger.info("Credentials has expired. Refreshing tokens...")
            credentials = self.refresh_tokens(credentials)
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
                credentials_data = self._convert_expiry(credentials_data)
                credentials = Credentials(**credentials_data)
                return credentials
            except Exception as e:
                # fmt: off
                self.logger.error(f"Failed to load credentials from S3: {e}, {self.config.get('s3_bucket_name')}/{self.config.get('s3_credentials_path')}")  # noqa: E501
                # fmt: on
                return None

        if self.local_credentials_path and self.local_credentials_path.exists():
            try:
                self.logger.debug(f"local_credentials_path type: {type(self.local_credentials_path)}")
                self.logger.info(f"Loaded credentials from local file: {self.local_credentials_path}")
                with self.local_credentials_path.open("r") as f:
                    credentials_data = json.load(f)
                credentials_data = self._convert_expiry(credentials_data)
                credentials = Credentials(**credentials_data)
                return credentials
            except Exception as e:
                self.logger.exception(f"Failed to load credentials from local file: {e}")
                return None

        self.logger.debug(f"local_credentials_path type: {type(self.local_credentials_path)}")
        self.logger.warning(
            f"No valid credentials found in either {self.local_credentials_path} or S3: {self.has_s3_google}"
        )
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
                raise RefreshError("Failed to refresh Google credentials on Lambda/S3")
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
            raise
        self.save_credentials(credentials)
        return credentials

    def save_credentials(self, credentials):
        # serialize credentials as JSON, all attributes of credentials
        payload = {
            "access_token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": credentials.scopes,
            "expiry": credentials.expiry.isoformat() if credentials.expiry else None,
        }
        # convert payload to JSON
        json_buffer = json.dumps(payload).encode()

        try:
            if self.has_s3_google:
                self.logger.info("Saved credentials to S3.")
                s3 = boto3.client("s3")
                s3.put_object(
                    Bucket=self.config.get("s3_bucket_name"),
                    Key=self.config.get("s3_credentials_path"),
                    Body=json_buffer,
                )
                return
            if self.local_credentials_path.exists():
                self.logger.debug(f"local_credentials_path type: {type(self.local_credentials_path)}")
                self.logger.info(f"Removed existing credentials file: {self.local_credentials_path}")
                os.remove(self.local_credentials_path)
                with self.local_credentials_path.open("w") as token:
                    json.dump(payload, token)
            self.logger.info("Saved credentials to local file.")
        except Exception as e:
            self.logger.error(f"Error saving credentials to local file: {e}")

    def _convert_expiry(self, credentials_data):
        if "expiry" in credentials_data and isinstance(credentials_data["expiry"], str):
            try:
                credentials_data["expiry"] = datetime.fromisoformat(credentials_data["expiry"])
            except ValueError as e:
                self.logger.error(f"Error parsing expiry date: {e}")
                credentials_data["expiry"] = None
        return credentials_data


if __name__ == "__main__":
    # python -m src.gcal.gcal_token
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    # google
    from googleapiclient.discovery import build

    # Add the src directory to the Python path
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    from config.config import generate_uuid_config  # noqa: E402

    config = generate_uuid_config("")
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
