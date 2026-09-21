import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))

from notion.notion_token import NotionToken, SettingError  # noqa: E402
from utils.token_crypto import TokenCryptoError  # noqa: E402


def _make_logger():
    return MagicMock()


def _cloud_config(uuid="test-uuid-1234"):
    return {"mode": "cloud", "uuid": uuid}


def _local_config():
    return {"mode": "local", "mapping_domain_config_path": Path("/tmp/x.json")}


class TestNotionTokenLocalMode(unittest.TestCase):
    def test_local_reads_notion_token_env(self):
        with patch.dict(os.environ, {"NOTION_TOKEN": "secret-token-abc"}, clear=True):
            nt = NotionToken(_local_config(), _make_logger())
            self.assertEqual(nt.get(), "secret-token-abc")

    def test_local_plaintext_token_works_without_encryption_key(self):
        with patch.dict(os.environ, {"NOTION_TOKEN": "secret-token-abc"}, clear=True):
            nt = NotionToken(_local_config(), _make_logger())
            self.assertEqual(nt.get(), "secret-token-abc")

    def test_local_strips_whitespace(self):
        with patch.dict(os.environ, {"NOTION_TOKEN": "  token-with-spaces  "}):
            nt = NotionToken(_local_config(), _make_logger())
            self.assertEqual(nt.get(), "token-with-spaces")

    def test_local_encrypted_token_calls_decrypt_token_if_encrypted(self):
        encrypted_token = "enc:v1:encrypted-notion-token"
        with patch(
            "notion.notion_token.decrypt_token_if_encrypted",
            return_value="plain-notion-token",
        ) as mock_decrypt:
            with patch.dict(os.environ, {"NOTION_TOKEN": encrypted_token}, clear=True):
                nt = NotionToken(_local_config(), _make_logger())
        mock_decrypt.assert_called_once_with(encrypted_token)
        self.assertEqual(nt.get(), "plain-notion-token")

    def test_local_encrypted_token_missing_key_raises_setting_error(self):
        encrypted_token = "enc:v1:encrypted-notion-token"
        with patch(
            "notion.notion_token.decrypt_token_if_encrypted",
            side_effect=TokenCryptoError("TOKEN_ENCRYPTION_KEY missing"),
        ):
            with patch.dict(os.environ, {"NOTION_TOKEN": encrypted_token}, clear=True):
                with self.assertRaises(SettingError) as ctx:
                    NotionToken(_local_config(), _make_logger())
        self.assertIn("Failed to decrypt Notion token", str(ctx.exception))
        self.assertIn("TOKEN_ENCRYPTION_KEY", str(ctx.exception))

    def test_local_missing_env_raises(self):
        env = {k: v for k, v in os.environ.items() if k != "NOTION_TOKEN"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(SettingError) as ctx:
                NotionToken(_local_config(), _make_logger())
            self.assertIn("NOTION_TOKEN", str(ctx.exception))

    def test_local_empty_env_raises(self):
        with patch.dict(os.environ, {"NOTION_TOKEN": "   "}):
            with self.assertRaises(SettingError):
                NotionToken(_local_config(), _make_logger())

    def test_local_does_not_call_dynamodb(self):
        with patch.dict(os.environ, {"NOTION_TOKEN": "tok"}):
            with patch("utils.dynamodb_utils.get_notion_token_by_uuid") as mock_db:
                NotionToken(_local_config(), _make_logger())
                mock_db.assert_not_called()

    def test_local_token_not_logged(self):
        logger = _make_logger()
        with patch.dict(os.environ, {"NOTION_TOKEN": "super-secret-value"}):
            NotionToken(_local_config(), logger)
        all_log_calls = str(logger.mock_calls)
        self.assertNotIn("super-secret-value", all_log_calls)


class TestNotionTokenCloudMode(unittest.TestCase):
    @staticmethod
    def _row(**overrides):
        row = {
            "accessToken": "enc:v1:encrypted-cloud-notion-token",
            "workspaceId": "workspace-1",
            "updatedAt": 1_000,
        }
        row.update(overrides)
        return row

    def test_cloud_calls_dynamodb(self):
        mock_response = self._row()
        with patch("utils.dynamodb_utils.get_notion_token_by_uuid", return_value=mock_response) as mock_db:
            with patch(
                "notion.notion_token.decrypt_token",
                return_value="plain-cloud-notion-token",
            ) as mock_decrypt:
                nt = NotionToken(_cloud_config("uuid-abc"), _make_logger())
            mock_db.assert_called_once_with("uuid-abc", consistent_read=True)
            mock_decrypt.assert_called_once_with("enc:v1:encrypted-cloud-notion-token")
            self.assertEqual(nt.get(), "plain-cloud-notion-token")

    def test_cloud_plaintext_token_fails_closed(self):
        mock_response = self._row(accessToken="cloud-token-xyz")
        with patch("utils.dynamodb_utils.get_notion_token_by_uuid", return_value=mock_response):
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(SettingError) as ctx:
                    NotionToken(_cloud_config("uuid-abc"), _make_logger())
        self.assertIn("Token is not encrypted", str(ctx.exception))

    def test_cloud_encrypted_token_calls_decrypt_token_if_encrypted(self):
        encrypted_token = "enc:v1:encrypted-cloud-notion-token"
        mock_response = self._row(accessToken=encrypted_token)
        with patch("utils.dynamodb_utils.get_notion_token_by_uuid", return_value=mock_response) as mock_db:
            with patch(
                "notion.notion_token.decrypt_token",
                return_value="plain-cloud-notion-token",
            ) as mock_decrypt:
                nt = NotionToken(_cloud_config("uuid-abc"), _make_logger())
        mock_db.assert_called_once_with("uuid-abc", consistent_read=True)
        mock_decrypt.assert_called_once_with(encrypted_token)
        self.assertEqual(nt.get(), "plain-cloud-notion-token")

    def test_cloud_encrypted_token_missing_key_raises_setting_error(self):
        encrypted_token = "enc:v1:encrypted-cloud-notion-token"
        mock_response = self._row(accessToken=encrypted_token)
        with patch("utils.dynamodb_utils.get_notion_token_by_uuid", return_value=mock_response):
            with patch(
                "notion.notion_token.decrypt_token",
                side_effect=TokenCryptoError("TOKEN_ENCRYPTION_KEY missing"),
            ):
                with self.assertRaises(SettingError) as ctx:
                    NotionToken(_cloud_config("uuid-abc"), _make_logger())
        self.assertIn("Failed to decrypt Notion token", str(ctx.exception))
        self.assertIn("TOKEN_ENCRYPTION_KEY", str(ctx.exception))

    def test_cloud_dynamodb_error_raises_setting_error(self):
        with patch(
            "utils.dynamodb_utils.get_notion_token_by_uuid",
            side_effect=RuntimeError("DDB down"),
        ):
            with self.assertRaises(SettingError) as ctx:
                NotionToken(_cloud_config(), _make_logger())
            self.assertIn("DDB down", str(ctx.exception))

    def test_cloud_requires_workspace_binding(self):
        with patch(
            "utils.dynamodb_utils.get_notion_token_by_uuid",
            return_value=self._row(workspaceId=""),
        ):
            with self.assertRaises(SettingError) as ctx:
                NotionToken(_cloud_config("uuid-abc"), _make_logger())
        self.assertIn("workspaceId", str(ctx.exception))

    def test_cloud_requires_updated_at_binding(self):
        with patch(
            "utils.dynamodb_utils.get_notion_token_by_uuid",
            return_value=self._row(updatedAt=None),
        ):
            with self.assertRaises(SettingError) as ctx:
                NotionToken(_cloud_config("uuid-abc"), _make_logger())
        self.assertIn("updatedAt", str(ctx.exception))

    def test_admission_binding_accepts_row_loaded_before_admission(self):
        with patch(
            "utils.dynamodb_utils.get_notion_token_by_uuid",
            return_value=self._row(updatedAt=1_000),
        ), patch(
            "notion.notion_token.decrypt_token",
            return_value="plain-cloud-notion-token",
        ):
            nt = NotionToken(_cloud_config("uuid-abc"), _make_logger())

        nt.assert_admission_binding(1_001)

    def test_admission_binding_rejects_reconnect_after_admission(self):
        with patch(
            "utils.dynamodb_utils.get_notion_token_by_uuid",
            return_value=self._row(updatedAt=1_002),
        ), patch(
            "notion.notion_token.decrypt_token",
            return_value="plain-cloud-notion-token",
        ):
            nt = NotionToken(_cloud_config("uuid-abc"), _make_logger())

        with self.assertRaises(SettingError):
            nt.assert_admission_binding(1_001)

    def test_admission_binding_rejects_malformed_updated_at(self):
        with patch(
            "utils.dynamodb_utils.get_notion_token_by_uuid",
            return_value=self._row(updatedAt="not-a-timestamp"),
        ), patch(
            "notion.notion_token.decrypt_token",
            return_value="plain-cloud-notion-token",
        ):
            nt = NotionToken(_cloud_config("uuid-abc"), _make_logger())

        with self.assertRaises(SettingError):
            nt.assert_admission_binding(1_001)

    def test_current_binding_accepts_unchanged_row(self):
        row = self._row()
        with patch(
            "utils.dynamodb_utils.get_notion_token_by_uuid",
            side_effect=[row, dict(row)],
        ) as mock_db, patch(
            "notion.notion_token.decrypt_token",
            return_value="plain-cloud-notion-token",
        ):
            nt = NotionToken(_cloud_config("uuid-abc"), _make_logger())
            nt.assert_current_binding()

        self.assertEqual(mock_db.call_count, 2)
        self.assertTrue(mock_db.call_args_list[1].kwargs["consistent_read"])

    def test_current_binding_rejects_workspace_reconnect(self):
        with patch(
            "utils.dynamodb_utils.get_notion_token_by_uuid",
            side_effect=[
                self._row(),
                self._row(workspaceId="workspace-2", updatedAt=1_001),
            ],
        ), patch(
            "notion.notion_token.decrypt_token",
            return_value="plain-cloud-notion-token",
        ):
            nt = NotionToken(_cloud_config("uuid-abc"), _make_logger())
            with self.assertRaises(SettingError):
                nt.assert_current_binding()

    def test_current_binding_rejects_same_workspace_token_replacement(self):
        with patch(
            "utils.dynamodb_utils.get_notion_token_by_uuid",
            side_effect=[self._row(), self._row(updatedAt=1_001)],
        ), patch(
            "notion.notion_token.decrypt_token",
            return_value="plain-cloud-notion-token",
        ):
            nt = NotionToken(_cloud_config("uuid-abc"), _make_logger())
            with self.assertRaises(SettingError):
                nt.assert_current_binding()

    def test_current_binding_rejects_missing_row(self):
        with patch(
            "utils.dynamodb_utils.get_notion_token_by_uuid",
            side_effect=[self._row(), ValueError("missing")],
        ), patch(
            "notion.notion_token.decrypt_token",
            return_value="plain-cloud-notion-token",
        ):
            nt = NotionToken(_cloud_config("uuid-abc"), _make_logger())
            with self.assertRaises(SettingError):
                nt.assert_current_binding()


class TestNotionTokenUnknownMode(unittest.TestCase):
    def test_unknown_mode_raises(self):
        config = {"mode": "legacy_local"}
        with self.assertRaises(SettingError) as ctx:
            NotionToken(config, _make_logger())
        self.assertIn("legacy_local", str(ctx.exception))

    def test_none_mode_raises(self):
        config = {"mode": None}
        with self.assertRaises(SettingError):
            NotionToken(config, _make_logger())


if __name__ == "__main__":
    unittest.main()
