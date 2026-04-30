import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))
os.environ.setdefault("APP_REGION", "ap-southeast-2")
import utils.dynamodb_utils  # noqa: E402 — force boto3 init before test imports

from notion.notion_token import NotionToken, SettingError  # noqa: E402


def _make_logger():
    return MagicMock()


def _cloud_config(uuid="test-uuid-1234"):
    return {"mode": "cloud", "uuid": uuid}


def _local_config():
    return {"mode": "local", "notion_setting_path": Path("/tmp/x.json")}


class TestNotionTokenLocalMode(unittest.TestCase):
    def test_local_reads_notion_token_env(self):
        with patch.dict(os.environ, {"NOTION_TOKEN": "secret-token-abc"}):
            nt = NotionToken(_local_config(), _make_logger())
            self.assertEqual(nt.get(), "secret-token-abc")

    def test_local_strips_whitespace(self):
        with patch.dict(os.environ, {"NOTION_TOKEN": "  token-with-spaces  "}):
            nt = NotionToken(_local_config(), _make_logger())
            self.assertEqual(nt.get(), "token-with-spaces")

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
    def test_cloud_calls_dynamodb(self):
        mock_response = {"accessToken": "cloud-token-xyz"}
        with patch("utils.dynamodb_utils.get_notion_token_by_uuid", return_value=mock_response) as mock_db:
            nt = NotionToken(_cloud_config("uuid-abc"), _make_logger())
            mock_db.assert_called_once_with("uuid-abc")
            self.assertEqual(nt.get(), "cloud-token-xyz")

    def test_cloud_dynamodb_error_raises_setting_error(self):
        with patch("utils.dynamodb_utils.get_notion_token_by_uuid", side_effect=RuntimeError("DDB down")):
            with self.assertRaises(SettingError) as ctx:
                NotionToken(_cloud_config(), _make_logger())
            self.assertIn("DDB down", str(ctx.exception))


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
