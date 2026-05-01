import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))

from gcal.gcal_token import GoogleToken, SettingError, _DEFAULT_SCOPES, _DEFAULT_TOKEN_URI  # noqa: E402
from google.oauth2.credentials import Credentials  # noqa: E402
from utils.token_crypto import TokenCryptoError, encrypt_token  # noqa: E402

# A far-future expiry in ms — prevents credentials.expired from being True in cloud tests
_FUTURE_EXPIRY_MS = str(int(datetime(2030, 1, 1, tzinfo=timezone.utc).timestamp() * 1000))

_CLOUD_DYNAMO_RESPONSE = {
    "accessToken": "cloud-access-token",
    "refreshToken": "cloud-refresh-token",
    "expiryDate": _FUTURE_EXPIRY_MS,
}
_CLOUD_ENV = {
    "GOOGLE_CALENDAR_CLIENT_ID": "gcal-client-id",
    "GOOGLE_CALENDAR_CLIENT_SECRET": "gcal-client-secret",
}
_BASE_LOCAL_ENV = {
    "GOOGLE_CLIENT_ID": "test-client-id",
    "GOOGLE_CLIENT_SECRET": "test-client-secret",
    "GOOGLE_REFRESH_TOKEN": "test-refresh-token",
}
_TOKEN_ENCRYPTION_KEY = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"


def _make_logger():
    return MagicMock()


def _local_env(**overrides):
    """Return a minimal env dict for local mode with optional overrides."""
    env = dict(_BASE_LOCAL_ENV)
    env.update(overrides)
    return env


def _local_env_without(*keys):
    """Return a minimal env dict for local mode with specified keys removed."""
    env = dict(_BASE_LOCAL_ENV)
    for k in keys:
        env.pop(k, None)
    return env


class TestGoogleTokenLocalModeCredentialConstruction(unittest.TestCase):
    """Tests for _load_local_credentials() — env parsing, defaults, validation."""

    def setUp(self):
        # Create a GoogleToken with activate_token mocked so we can call
        # _load_local_credentials() directly without triggering network I/O.
        with patch.object(GoogleToken, "activate_token"):
            self._gt = GoogleToken({"mode": "local"}, _make_logger())

    def _load(self, env):
        with patch.dict(os.environ, env, clear=True):
            return self._gt._load_local_credentials()

    def test_constructs_credentials_from_env(self):
        with patch.dict(os.environ, {}, clear=True):
            creds = self._load(_local_env())
        self.assertIsInstance(creds, Credentials)
        self.assertIsNone(creds.token)
        self.assertEqual(creds.refresh_token, _BASE_LOCAL_ENV["GOOGLE_REFRESH_TOKEN"])

    def test_plaintext_local_refresh_token_works_without_encryption_key(self):
        env = _local_env()
        env.pop("TOKEN_ENCRYPTION_KEY", None)
        creds = self._load(env)
        self.assertEqual(creds.refresh_token, _BASE_LOCAL_ENV["GOOGLE_REFRESH_TOKEN"])

    def test_encrypted_local_refresh_token_calls_decrypt_token(self):
        encrypted_token = "enc:v1:encrypted-refresh-token"
        with patch("gcal.gcal_token.decrypt_token_if_encrypted", return_value="plain-refresh-token") as mock_decrypt:
            creds = self._load(_local_env(GOOGLE_REFRESH_TOKEN=encrypted_token))
        mock_decrypt.assert_called_once_with(encrypted_token)
        self.assertEqual(creds.refresh_token, "plain-refresh-token")

    def test_encrypted_local_refresh_token_missing_key_raises_setting_error(self):
        encrypted_token = "enc:v1:encrypted-refresh-token"
        with patch(
            "gcal.gcal_token.decrypt_token_if_encrypted",
            side_effect=TokenCryptoError("TOKEN_ENCRYPTION_KEY missing"),
        ):
            with self.assertRaises(SettingError) as ctx:
                self._load(_local_env(GOOGLE_REFRESH_TOKEN=encrypted_token))
        self.assertIn("Failed to decrypt encrypted Google OAuth token", str(ctx.exception))
        self.assertIn("TOKEN_ENCRYPTION_KEY", str(ctx.exception))

    def test_token_is_none_before_refresh(self):
        creds = self._load(_local_env())
        self.assertIsNone(creds.token)

    def test_defaults_token_uri_when_google_token_uri_missing(self):
        creds = self._load(_local_env_without("GOOGLE_TOKEN_URI"))
        self.assertEqual(creds.token_uri, _DEFAULT_TOKEN_URI)

    def test_uses_custom_token_uri_when_provided(self):
        custom_uri = "https://custom.example.com/token"
        creds = self._load(_local_env(GOOGLE_TOKEN_URI=custom_uri))
        self.assertEqual(creds.token_uri, custom_uri)

    def test_uses_default_scopes_when_google_scopes_missing(self):
        creds = self._load(_local_env_without("GOOGLE_SCOPES"))
        self.assertEqual(set(creds.scopes), set(_DEFAULT_SCOPES))

    def test_parses_comma_separated_google_scopes(self):
        raw = "https://www.googleapis.com/auth/calendar.events, openid , https://www.googleapis.com/auth/userinfo.email"
        creds = self._load(_local_env(GOOGLE_SCOPES=raw))
        self.assertEqual(
            set(creds.scopes),
            {
                "https://www.googleapis.com/auth/calendar.events",
                "openid",
                "https://www.googleapis.com/auth/userinfo.email",
            },
        )

    def test_missing_google_client_id_raises(self):
        with self.assertRaises(SettingError) as ctx:
            self._load(_local_env_without("GOOGLE_CLIENT_ID"))
        self.assertIn("GOOGLE_CLIENT_ID", str(ctx.exception))

    def test_missing_google_client_secret_raises(self):
        with self.assertRaises(SettingError) as ctx:
            self._load(_local_env_without("GOOGLE_CLIENT_SECRET"))
        self.assertIn("GOOGLE_CLIENT_SECRET", str(ctx.exception))

    def test_missing_google_refresh_token_raises(self):
        with self.assertRaises(SettingError) as ctx:
            self._load(_local_env_without("GOOGLE_REFRESH_TOKEN"))
        self.assertIn("GOOGLE_REFRESH_TOKEN", str(ctx.exception))

    def test_empty_google_client_id_raises(self):
        with self.assertRaises(SettingError):
            self._load(_local_env(GOOGLE_CLIENT_ID="   "))

    def test_empty_google_scopes_raises(self):
        with self.assertRaises(SettingError) as ctx:
            self._load(_local_env(GOOGLE_SCOPES=","))
        self.assertIn("GOOGLE_SCOPES", str(ctx.exception))

    def test_scopes_whitespace_only_entry_filtered(self):
        raw = "openid,  ,https://www.googleapis.com/auth/calendar.events"
        creds = self._load(_local_env(GOOGLE_SCOPES=raw))
        self.assertEqual(
            set(creds.scopes),
            {"openid", "https://www.googleapis.com/auth/calendar.events"},
        )


class TestGoogleTokenLocalModeActivation(unittest.TestCase):
    """Tests for full activate_token() behaviour in local mode."""

    def test_refresh_called_for_local_credentials(self):
        env = _local_env()
        with patch.dict(os.environ, env, clear=True):
            with patch("google.oauth2.credentials.Credentials.refresh") as mock_refresh:
                GoogleToken({"mode": "local"}, _make_logger())
                mock_refresh.assert_called_once()

    def test_save_credentials_is_noop_in_local_mode(self):
        env = _local_env()
        with patch.dict(os.environ, env, clear=True):
            with patch("google.oauth2.credentials.Credentials.refresh"):
                gt = GoogleToken({"mode": "local"}, _make_logger())
        mock_creds = MagicMock()
        mock_creds.expiry = None
        with patch("utils.dynamodb_utils.update_google_token_by_uuid") as mock_updater:
            gt._save_credentials(mock_creds)
            mock_updater.assert_not_called()

    def test_local_mode_does_not_call_dynamodb_loader(self):
        env = _local_env()
        with patch.dict(os.environ, env, clear=True):
            with patch("google.oauth2.credentials.Credentials.refresh"):
                with patch("utils.dynamodb_utils.get_google_token_by_uuid") as mock_loader:
                    GoogleToken({"mode": "local"}, _make_logger())
                    mock_loader.assert_not_called()

    def test_local_mode_does_not_call_dynamodb_updater(self):
        env = _local_env()
        with patch.dict(os.environ, env, clear=True):
            with patch("google.oauth2.credentials.Credentials.refresh"):
                with patch("utils.dynamodb_utils.update_google_token_by_uuid") as mock_updater:
                    GoogleToken({"mode": "local"}, _make_logger())
                    mock_updater.assert_not_called()

    def test_secrets_not_logged(self):
        env = _local_env()
        logger = _make_logger()
        with patch.dict(os.environ, env, clear=True):
            with patch("google.oauth2.credentials.Credentials.refresh"):
                GoogleToken({"mode": "local"}, logger)
        log_calls = str(logger.mock_calls)
        self.assertNotIn(_BASE_LOCAL_ENV["GOOGLE_CLIENT_SECRET"], log_calls)
        self.assertNotIn(_BASE_LOCAL_ENV["GOOGLE_REFRESH_TOKEN"], log_calls)


class TestGoogleTokenCloudMode(unittest.TestCase):
    """Tests for cloud mode — DynamoDB-backed loading and saving."""

    def _cloud_config(self, uuid="test-uuid"):
        return {"mode": "cloud", "uuid": uuid}

    def test_cloud_loads_token_from_dynamodb(self):
        with patch("utils.dynamodb_utils.get_google_token_by_uuid", return_value=_CLOUD_DYNAMO_RESPONSE) as mock_loader:
            with patch.dict(os.environ, _CLOUD_ENV):
                gt = GoogleToken(self._cloud_config("my-uuid"), _make_logger())
                mock_loader.assert_called_once_with("my-uuid")
                self.assertEqual(gt.credentials.token, "cloud-access-token")
                self.assertEqual(gt.credentials.refresh_token, "cloud-refresh-token")

    def test_plaintext_cloud_tokens_work_without_encryption_key(self):
        env = dict(_CLOUD_ENV)
        env.pop("TOKEN_ENCRYPTION_KEY", None)
        with patch("utils.dynamodb_utils.get_google_token_by_uuid", return_value=_CLOUD_DYNAMO_RESPONSE):
            with patch.dict(os.environ, env, clear=True):
                gt = GoogleToken(self._cloud_config(), _make_logger())
        self.assertEqual(gt.credentials.token, "cloud-access-token")
        self.assertEqual(gt.credentials.refresh_token, "cloud-refresh-token")

    def test_encrypted_cloud_refresh_token_calls_decrypt_token(self):
        response = {
            **_CLOUD_DYNAMO_RESPONSE,
            "refreshToken": "enc:v1:encrypted-cloud-refresh-token",
        }
        with patch("utils.dynamodb_utils.get_google_token_by_uuid", return_value=response):
            with patch(
                "gcal.gcal_token.decrypt_token_if_encrypted", return_value="plain-cloud-refresh-token"
            ) as mock_decrypt:
                with patch.dict(os.environ, _CLOUD_ENV):
                    gt = GoogleToken(self._cloud_config(), _make_logger())
        mock_decrypt.assert_any_call("enc:v1:encrypted-cloud-refresh-token")
        self.assertEqual(gt.credentials.refresh_token, "plain-cloud-refresh-token")

    def test_encrypted_cloud_access_token_calls_decrypt_token(self):
        response = {
            **_CLOUD_DYNAMO_RESPONSE,
            "accessToken": "enc:v1:encrypted-cloud-access-token",
        }
        with patch("utils.dynamodb_utils.get_google_token_by_uuid", return_value=response):
            with patch(
                "gcal.gcal_token.decrypt_token_if_encrypted", return_value="plain-cloud-access-token"
            ) as mock_decrypt:
                with patch.dict(os.environ, _CLOUD_ENV):
                    gt = GoogleToken(self._cloud_config(), _make_logger())
        mock_decrypt.assert_any_call("enc:v1:encrypted-cloud-access-token")
        self.assertEqual(gt.credentials.token, "plain-cloud-access-token")

    def test_cloud_save_credentials_calls_dynamodb_updater(self):
        with patch("utils.dynamodb_utils.get_google_token_by_uuid", return_value=_CLOUD_DYNAMO_RESPONSE):
            with patch.dict(os.environ, _CLOUD_ENV):
                gt = GoogleToken(self._cloud_config(), _make_logger())
        mock_creds = MagicMock()
        mock_creds.token = "new-access-token"
        mock_creds.refresh_token = "new-refresh-token"
        mock_creds.expiry = datetime(2030, 1, 1, tzinfo=timezone.utc)
        with patch("utils.dynamodb_utils.update_google_token_by_uuid") as mock_updater:
            with patch.dict(os.environ, {"TOKEN_ENCRYPTION_KEY": _TOKEN_ENCRYPTION_KEY}, clear=True):
                gt._save_credentials(mock_creds)
            mock_updater.assert_called_once()

    def test_cloud_save_credentials_writes_encrypted_tokens(self):
        with patch("utils.dynamodb_utils.get_google_token_by_uuid", return_value=_CLOUD_DYNAMO_RESPONSE):
            with patch.dict(os.environ, _CLOUD_ENV):
                gt = GoogleToken(self._cloud_config("uuid-encrypted-save"), _make_logger())
        mock_creds = MagicMock()
        mock_creds.token = "new-access-token"
        mock_creds.refresh_token = "new-refresh-token"
        mock_creds.expiry = datetime(2030, 1, 1, tzinfo=timezone.utc)

        with patch("utils.dynamodb_utils.update_google_token_by_uuid") as mock_updater:
            with patch.dict(os.environ, {"TOKEN_ENCRYPTION_KEY": _TOKEN_ENCRYPTION_KEY}, clear=True):
                gt._save_credentials(mock_creds)

        _, saved_access_token, saved_refresh_token, _, _ = mock_updater.call_args[0]
        self.assertTrue(saved_access_token.startswith("enc:v1:"))
        self.assertTrue(saved_refresh_token.startswith("enc:v1:"))
        self.assertNotEqual(saved_access_token, "new-access-token")
        self.assertNotEqual(saved_refresh_token, "new-refresh-token")

    def test_cloud_save_credentials_missing_encryption_key_raises_setting_error(self):
        with patch("utils.dynamodb_utils.get_google_token_by_uuid", return_value=_CLOUD_DYNAMO_RESPONSE):
            with patch.dict(os.environ, _CLOUD_ENV):
                gt = GoogleToken(self._cloud_config(), _make_logger())
        mock_creds = MagicMock()
        mock_creds.token = "new-access-token"
        mock_creds.refresh_token = "new-refresh-token"
        mock_creds.expiry = datetime(2030, 1, 1, tzinfo=timezone.utc)

        with patch("utils.dynamodb_utils.update_google_token_by_uuid") as mock_updater:
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(SettingError) as ctx:
                    gt._save_credentials(mock_creds)
        mock_updater.assert_not_called()
        self.assertIn("TOKEN_ENCRYPTION_KEY", str(ctx.exception))

    def test_encrypted_cloud_load_refresh_save_keeps_dynamodb_tokens_encrypted(self):
        expired_response = {
            "accessToken": None,
            "refreshToken": None,
            "expiryDate": str(int(datetime(2000, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)),
        }

        def refresh_credentials(credentials, request):  # noqa: ARG001
            credentials.token = "refreshed-access-token"
            credentials._refresh_token = "refreshed-refresh-token"
            credentials.expiry = datetime(2030, 1, 1, tzinfo=timezone.utc)

        with patch.dict(os.environ, {**_CLOUD_ENV, "TOKEN_ENCRYPTION_KEY": _TOKEN_ENCRYPTION_KEY}, clear=True):
            expired_response["accessToken"] = encrypt_token("old-access-token")
            expired_response["refreshToken"] = encrypt_token("old-refresh-token")

            with patch("utils.dynamodb_utils.get_google_token_by_uuid", return_value=expired_response):
                with patch("utils.dynamodb_utils.update_google_token_by_uuid") as mock_updater:
                    with patch("google.oauth2.credentials.Credentials.refresh", new=refresh_credentials):
                        gt = GoogleToken(self._cloud_config(), _make_logger())

        self.assertEqual(gt.credentials.token, "refreshed-access-token")
        self.assertEqual(gt.credentials.refresh_token, "refreshed-refresh-token")
        _, saved_access_token, saved_refresh_token, _, _ = mock_updater.call_args[0]
        self.assertTrue(saved_access_token.startswith("enc:v1:"))
        self.assertTrue(saved_refresh_token.startswith("enc:v1:"))

    def test_cloud_dynamodb_error_raises_setting_error(self):
        with patch("utils.dynamodb_utils.get_google_token_by_uuid", side_effect=RuntimeError("DDB down")):
            with patch.dict(os.environ, _CLOUD_ENV):
                with self.assertRaises(SettingError) as ctx:
                    GoogleToken(self._cloud_config(), _make_logger())
                self.assertIn("DDB down", str(ctx.exception))


class TestGoogleTokenUnknownMode(unittest.TestCase):
    def test_unknown_mode_raises(self):
        with self.assertRaises(SettingError) as ctx:
            GoogleToken({"mode": "legacy_local"}, _make_logger())
        self.assertIn("legacy_local", str(ctx.exception))

    def test_none_mode_raises(self):
        with self.assertRaises(SettingError):
            GoogleToken({"mode": None}, _make_logger())


if __name__ == "__main__":
    unittest.main()
