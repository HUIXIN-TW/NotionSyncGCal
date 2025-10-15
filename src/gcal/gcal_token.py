import os
import json
import boto3
from datetime import datetime, timezone
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.exceptions import RefreshError


class SettingError(Exception):
    """Custom exception to handle setting errors in the Notion class."""

    def __init__(self, message):
        super().__init__(message)


class GoogleToken:
    def __init__(self, config, logger):
        self.credentials = None
        self.config = config
        self.mode = config.get("mode")
        self.logger = logger
        self.s3_client = boto3.client("s3") if self.mode == 's3' else None
        self.activate_token()

    def activate_token(self):
        credentials = self._load_credentials()
        if self.mode == 'local':
            self.logger.info("Running in local mode. Proceeding with OAuth flow via local server")
            credentials = self._perform_oauth_flow(credentials.scopes) if credentials.expired else credentials
        if credentials.expired and credentials.refresh_token:
            self.logger.info("Credentials has expired. Refreshing tokens...")
            credentials = self._refresh_tokens(credentials)
        self.credentials = credentials

    def _load_credentials(self):
        try:
            if not self.config:
                raise SettingError("Configuration is required to load settings.")
            if self.mode == 's3':
                self.logger.info(f"Loading credentials from S3")
                response = self.s3_client.get_object(
                    Bucket=self.config.get("s3_bucket_name"), Key=self.config.get("s3_key_google_token")
                )
                data = json.loads(response.get("Body").read().decode("utf-8"))
                credentials_data = {
                    "token": data.get("token"),
                    "refresh_token": data.get("refresh_token"),
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "scopes": data.get("scopes"),
                    "expiry": data.get("expiry"),
                    "client_id": os.environ.get("GOOGLE_CALENDAR_CLIENT_ID"),
                    "client_secret": os.environ.get("GOOGLE_CALENDAR_CLIENT_SECRET"),
                }
            elif self.mode == 'local':
                self.logger.info(f"Loading google token from local file: {self.config.get('local_google_token_path')}")
                with self.config.get('local_google_token_path').open("r") as f:
                    credentials_data = json.load(f)
            credentials_data = self._convert_expiry(credentials_data)
            credentials = Credentials(**credentials_data)
            self._verify_credentials(credentials)
            return credentials
        except SettingError as e:
            self.logger.error(f"SettingError: {e}")
            raise

    def _refresh_tokens(self, credentials):
        try:
            credentials.refresh(Request())
            self._save_credentials(credentials)
            self.logger.info("Successfully refreshed tokens.")
            return credentials
        except Exception as e:
            # local only
            credentials = self._perform_oauth_flow(credentials.scopes)
            return credentials
        except Exception as e:
            raise RefreshError("Failed to refresh Google credentials")

    def _perform_oauth_flow(self, scopes):
        self.logger.info("Google Scope: " + str(scopes))
        flow = InstalledAppFlow.from_client_secrets_file(str(self.config.get('local_google_client_secret_path')), scopes)
        credentials = flow.run_local_server(port=0)
        self.logger.info(f"Successfully fetched new google tokens to {self.config.get('local_google_token_path')}")
        self._save_credentials(credentials)
        return credentials

    def _save_credentials(self, credentials):
        # serialize credentials as JSON, all attributes of credentials
        # refresh_token, token_uri, client_id, and client_secret
        payload = {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "scopes": credentials.scopes,
            "expiry": credentials.expiry.isoformat() if credentials.expiry else None,
        }
        # convert payload to JSON
        json_buffer = json.dumps(payload).encode()

        try:
            if self.mode == 's3':
                self.s3_client.put_object(
                    Bucket=self.config.get("s3_bucket_name"),
                    Key=self.config.get("s3_key_google_token"),
                    Body=json_buffer,
                )
                self.logger.info("Saved credentials to S3.")
            elif self.mode == 'local':
                os.remove(self.config.get("local_google_token_path"))
                with self.config.get("local_google_token_path").open("w") as token:
                    json.dump(payload, token)
                self.logger.info("Saved credentials to local file.")
        except Exception as e:
            self.logger.error(f"Error saving credentials to local file: {e}")
            raise SettingError(f"Error saving credentials: {e}")

    def _convert_expiry(self, credentials_data):
        if "expiry" in credentials_data and isinstance(credentials_data["expiry"], str):
            try:
                credentials_data["expiry"] = datetime.fromisoformat(credentials_data["expiry"])
            except ValueError as e:
                self.logger.error(f"Error parsing expiry date: {e}")
                credentials_data["expiry"] = None
        return credentials_data

    def _verify_credentials(self, credentials):
        # refresh_token, token_uri, client_id, and client_secret
        if not isinstance(credentials, Credentials):
            raise SettingError("Invalid credentials object.")
        if not credentials.expiry:
            raise SettingError("Credentials have no expiry date.")
        if not credentials.refresh_token:
            raise SettingError("No refresh token found.")
        if not credentials.token:
            raise SettingError("No access token found.")
        if not credentials.scopes:
            raise SettingError("Scopes are missing.")
        if not credentials.token_uri:
            raise SettingError("Token URI is missing.")


if __name__ == "__main__":
    import sys
    import logging
    from pathlib import Path
    from googleapiclient.discovery import build

    # python -m src.gcal.gcal_token
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    # Add the src directory to the Python path
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    from config.config import generate_config  # noqa: E402

    config = generate_config("huixinyang")
    gt = GoogleToken(config, logger)
    service = build("calendar", "v3", credentials=gt.credentials)
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
