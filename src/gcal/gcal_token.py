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
        self.ddb_client = boto3.client("dynamodb") if self.mode == "serverless" else None
        self.activate_token()

    def activate_token(self):
        credentials = self._load_credentials()
        if self.mode == "local":
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
            if self.mode == "serverless":
                self.logger.debug("Loading credentials from DynamoDB")
                response = self.ddb_client.get_item(
                    TableName=self.config.get("dynamo_google_token_table"),
                    Key={"uuid": {"S": self.config.get("uuid")}},
                )
                data = response.get("Item")
                credentials_data = {
                    "token": data.get("accessToken").get("S"),
                    "refresh_token": data.get("refreshToken").get("S"),
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "scopes": [
                        "https://www.googleapis.com/auth/calendar.events",
                        "openid",
                        "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
                        "https://www.googleapis.com/auth/userinfo.profile",
                        "https://www.googleapis.com/auth/userinfo.email",
                    ],
                    "expiry": self._convert_google_expiry_date_format(data.get("expiryDate").get("N")),
                    "client_id": os.environ.get("GOOGLE_CALENDAR_CLIENT_ID"),
                    "client_secret": os.environ.get("GOOGLE_CALENDAR_CLIENT_SECRET"),
                }
            elif self.mode == "local":
                self.logger.info(f"Loading google token from local file: {self.config.get('local_google_token_path')}")
                with self.config.get("local_google_token_path").open("r") as f:
                    credentials_data = json.load(f)
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
            self.logger.warning(f"Token refresh failed: {e}, running OAuth flow locally.")
            try:
                credentials = self._perform_oauth_flow(credentials.scopes)
                return credentials
            except Exception as e:
                raise RefreshError(f"Failed to refresh Google credentials: {e}")

    def _perform_oauth_flow(self, scopes):
        self.logger.info("Google Scope: " + str(scopes))
        flow = InstalledAppFlow.from_client_secrets_file(
            str(self.config.get("local_google_client_secret_path")), scopes
        )
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
            "expiry": credentials.expiry if credentials.expiry else None,
        }
        try:
            if self.mode == "serverless":
                self.ddb_client.update_item(
                    TableName=self.config.get("dynamo_google_token_table"),
                    Key={"uuid": {"S": self.config.get("uuid")}},
                    UpdateExpression="SET accessToken = :at, refreshToken = :rt, expiryDate = :ed",
                    ExpressionAttributeValues={
                        ":at": {"S": credentials.token},
                        ":rt": {"S": credentials.refresh_token},
                        ":ed": {"N": self._convert_notica_expiry_date_format(credentials.expiry)},
                    },
                )
                self.logger.info("Saved credentials to DynamoDB.")
            elif self.mode == "local":
                os.remove(self.config.get("local_google_token_path"))
                with self.config.get("local_google_token_path").open("w") as token:
                    json.dump(payload, token)
                self.logger.info("Saved credentials to local file.")
        except Exception as e:
            self.logger.error(f"Error saving credentials to local file: {e}")
            raise SettingError(f"Error saving credentials: {e}")

    def _convert_google_expiry_date_format(self, expiryDate):
        expiry_ts = int(expiryDate) / 1000
        return datetime.fromtimestamp(expiry_ts, tz=timezone.utc).replace(tzinfo=None)

    def _convert_notica_expiry_date_format(self, expiryDate):
        if not expiryDate:
            return None
        return str(int(expiryDate.timestamp()) * 1000)

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

    config = generate_config("")
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
