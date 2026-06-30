import os
from datetime import datetime, timezone
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.auth.exceptions import RefreshError
from utils.ssm_secrets import SSMSecretError, get_ssm_parameter
from utils.token_crypto import (
    TOKEN_ENCRYPTION_PREFIX,
    TokenCryptoError,
    decrypt_token,
    decrypt_token_if_encrypted,
)
from utils.dynamodb_utils import GoogleTokenWriteConflictError

_DEFAULT_TOKEN_URI = "https://oauth2.googleapis.com/token"
_DEFAULT_SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "openid",
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
]


class SettingError(Exception):
    """Custom exception to handle setting errors in the GoogleToken class."""

    def __init__(self, message):
        super().__init__(message)


class GoogleToken:
    def __init__(self, config, logger):
        self.credentials = None
        self.config = config
        self.mode = config.get("mode")
        self.logger = logger
        self._loaded_updated_at = None
        self.activate_token()

    def activate_token(self):
        credentials = self._load_credentials()
        if self.mode == "local":
            self.logger.info("Local mode: refreshing Google credentials in memory")
            credentials = self._refresh_tokens(credentials)
        elif credentials.expired and credentials.refresh_token:
            self.logger.info("Credentials has expired. Refreshing tokens...")
            credentials = self._refresh_tokens(credentials)
        self.credentials = credentials

    def _load_credentials(self, consistent_read: bool = False):
        if not self.config:
            raise SettingError("Configuration is required to load settings.")
        if self.mode == "cloud":
            try:
                from utils.dynamodb_utils import get_google_token_by_uuid

                self.logger.debug("Loading credentials from DynamoDB")
                data = get_google_token_by_uuid(self.config.get("uuid"), consistent_read=consistent_read)
                self._loaded_updated_at = data.get("updatedAt")
                try:
                    access_token = decrypt_token(data.get("accessToken"))
                    refresh_token = decrypt_token(data.get("refreshToken"))
                except TokenCryptoError as e:
                    raise SettingError(f"Failed to decrypt encrypted Google OAuth token: {e}") from e

                self._assert_plaintext_runtime_token("accessToken", access_token)
                self._assert_plaintext_runtime_token("refreshToken", refresh_token)

                client_secret_ssm_path = os.environ.get("GOOGLE_CALENDAR_CLIENT_SECRET_SSM_PATH", "").strip()
                if not client_secret_ssm_path:
                    raise SettingError(
                        "GOOGLE_CALENDAR_CLIENT_SECRET_SSM_PATH env var is required but not set in APP_MODE=cloud."
                    )
                try:
                    client_secret = get_ssm_parameter(client_secret_ssm_path)
                except SSMSecretError as e:
                    raise SettingError(f"Failed to resolve Google client secret from SSM: {e}") from e
                credentials_data = {
                    "token": access_token,
                    "refresh_token": refresh_token,
                    "token_uri": _DEFAULT_TOKEN_URI,
                    "scopes": list(_DEFAULT_SCOPES),
                    "expiry": self._convert_google_expiry_date_format(data.get("expiryDate")),
                    "client_id": os.environ.get("GOOGLE_CALENDAR_CLIENT_ID"),
                    "client_secret": client_secret,
                }
                credentials = Credentials(**credentials_data)
                self._verify_credentials(credentials)
                return credentials
            except SettingError:
                raise
            except Exception as e:
                raise SettingError(f"Error loading Google credentials from DynamoDB: {e}") from e
        if self.mode == "local":
            return self._load_local_credentials()
        raise SettingError(f"Unknown config mode '{self.mode}'. Expected 'cloud' or 'local'.")

    def _load_local_credentials(self):
        client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
        client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
        refresh_token = os.environ.get("GOOGLE_REFRESH_TOKEN", "").strip()

        missing = [
            name
            for name, val in [
                ("GOOGLE_CLIENT_ID", client_id),
                ("GOOGLE_CLIENT_SECRET", client_secret),
                ("GOOGLE_REFRESH_TOKEN", refresh_token),
            ]
            if not val
        ]
        if missing:
            raise SettingError(f"Required environment variables for local Google auth are missing or empty: {missing}")
        try:
            refresh_token = decrypt_token_if_encrypted(refresh_token)
        except TokenCryptoError as e:
            raise SettingError(f"Failed to decrypt encrypted Google OAuth token: {e}") from e
        self._assert_plaintext_runtime_token("refreshToken", refresh_token)

        token_uri = os.environ.get("GOOGLE_TOKEN_URI", "").strip() or _DEFAULT_TOKEN_URI

        scopes_raw = os.environ.get("GOOGLE_SCOPES", "").strip()
        if scopes_raw:
            scopes = [s.strip() for s in scopes_raw.split(",") if s.strip()]
            if not scopes:
                raise SettingError("GOOGLE_SCOPES is set but resulted in an empty scope list after parsing.")
        else:
            scopes = list(_DEFAULT_SCOPES)

        return Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri=token_uri,
            client_id=client_id,
            client_secret=client_secret,
            scopes=scopes,
        )

    def _refresh_tokens(self, credentials):
        try:
            existing_refresh_token = credentials.refresh_token
            credentials.refresh(Request())
            if not credentials.refresh_token:
                credentials._refresh_token = existing_refresh_token
            self._save_credentials(credentials)
            self.logger.info("Successfully refreshed tokens.")
            return credentials
        except GoogleTokenWriteConflictError:
            if self.mode == "cloud":
                self.logger.warning(
                    "Google credentials were refreshed by another worker first; reloading the latest token row."
                )
                latest_credentials = self._load_credentials(consistent_read=True)
                self.credentials = latest_credentials
                return latest_credentials
            raise
        except Exception as e:
            if self.mode == "local":
                raise RefreshError(
                    "Failed to refresh Google credentials in local mode. "
                    "GOOGLE_REFRESH_TOKEN is likely invalid/expired; renew it outside runtime and update .env.local."
                ) from e
            raise RefreshError("Failed to refresh Google credentials. Refresh token is likely invalid/expired.") from e

    def _save_credentials(self, credentials):
        try:
            if self.mode == "cloud":
                from utils.dynamodb_utils import update_google_token_by_uuid

                expiry_str = self._convert_notica_expiry_date_format(credentials.expiry)
                updated_str = str(int(datetime.now(timezone.utc).timestamp() * 1000))
                update_google_token_by_uuid(
                    self.config.get("uuid"),
                    credentials.token,
                    credentials.refresh_token,
                    expiry_str,
                    updated_str,
                    self._loaded_updated_at,
                )
                self._loaded_updated_at = updated_str
                self.logger.info("Saved credentials to DynamoDB.")
            elif self.mode == "local":
                self.logger.debug("Local mode: skipping credential persistence.")
        except GoogleTokenWriteConflictError:
            raise
        except Exception as e:
            self.logger.error(f"Error saving credentials: {e}")
            raise SettingError(f"Error saving credentials: {e}")

    def _convert_google_expiry_date_format(self, expiryDate):
        expiry_ts = int(expiryDate) / 1000
        return datetime.fromtimestamp(expiry_ts, tz=timezone.utc).replace(tzinfo=None)

    def _convert_notica_expiry_date_format(self, expiryDate):
        if not expiryDate:
            return None
        if expiryDate.tzinfo is None:
            expiryDate = expiryDate.replace(tzinfo=timezone.utc)
        expiryDate = expiryDate.astimezone(timezone.utc)
        return str(int(expiryDate.timestamp() * 1000))

    def _verify_credentials(self, credentials):
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

    def _assert_plaintext_runtime_token(self, token_name, value):
        if isinstance(value, str) and value.startswith(TOKEN_ENCRYPTION_PREFIX):
            raise SettingError(f"Internal token handling error: {token_name} remained encrypted at runtime.")


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

    # APP_MODE must be set in the shell (e.g. APP_MODE=local or APP_MODE=cloud)
    config = generate_config()
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
