import copy
import os
import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))
os.environ.setdefault("APP_REGION", "ap-southeast-2")
import utils.dynamodb_utils  # noqa: E402 — force boto3 init before test imports

from notion.notion_config import NotionConfig, SettingError  # noqa: E402

VALID_LOCAL_CONFIG = {
    "database_id": "test-db-id",
    "goback_days": 3,
    "goforward_days": 90,
    "timecode": "+08:00",
    "timezone": "Asia/Taipei",
    "default_event_length": 60,
    "default_start_time": 8,
    "gcal_dic": [{"TestCal": "test@gmail.com"}],
    "page_property": [
        {
            "Task_Notion_Name": "Task Name",
            "Date_Notion_Name": "Date",
            "Initiative_Notion_Name": "Initiative",
            "Status_Notion_Name": "Status",
            "Location_Notion_Name": "Location",
            "ExtraInfo_Notion_Name": "Extra Info",
            "GCal_Name_Notion_Name": "Calendar",
            "GCal_EventId_Notion_Name": "GCal Event Id",
            "GCal_Sync_Time_Notion_Name": "GCal Sync Time",
            "GCal_End_Date_Notion_Name": "GCal End Date",
            "Delete_Notion_Name": "GCal Deleted?",
            "CompleteIcon_Notion_Name": "GCal Icon",
        }
    ],
}


def _make_logger():
    return MagicMock()


def _write_json(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


class TestNotionConfigLocalMode(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.json_path = Path(self.tmp.name) / "notion-setting.json"

    def tearDown(self):
        self.tmp.cleanup()

    def _local_config(self, path=None):
        return {"mode": "local", "notion_setting_path": path or self.json_path}

    def test_local_loads_valid_json(self):
        _write_json(VALID_LOCAL_CONFIG, self.json_path)
        nc = NotionConfig(self._local_config(), _make_logger())
        self.assertEqual(nc.get()["database_id"], "test-db-id")

    def test_local_notion_token_not_required(self):
        data = dict(VALID_LOCAL_CONFIG)
        self.assertNotIn("notion_token", data)
        _write_json(data, self.json_path)
        nc = NotionConfig(self._local_config(), _make_logger())
        self.assertIsNotNone(nc.get())

    def test_local_notion_token_present_does_not_break(self):
        data = dict(VALID_LOCAL_CONFIG, notion_token="should-be-ignored")
        _write_json(data, self.json_path)
        nc = NotionConfig(self._local_config(), _make_logger())
        self.assertIsNotNone(nc.get())

    def test_local_missing_file_raises(self):
        missing = Path(self.tmp.name) / "does-not-exist.json"
        with self.assertRaises(SettingError) as ctx:
            NotionConfig(self._local_config(missing), _make_logger())
        self.assertIn("not found", str(ctx.exception))

    def test_local_malformed_json_raises(self):
        self.json_path.write_text("{not valid json", encoding="utf-8")
        with self.assertRaises(SettingError) as ctx:
            NotionConfig(self._local_config(), _make_logger())
        self.assertIn("not valid JSON", str(ctx.exception))

    def test_local_missing_required_key_raises(self):
        data = dict(VALID_LOCAL_CONFIG)
        del data["database_id"]
        _write_json(data, self.json_path)
        with self.assertRaises(SettingError) as ctx:
            NotionConfig(self._local_config(), _make_logger())
        self.assertIn("database_id", str(ctx.exception))

    def test_local_multiple_missing_keys_listed(self):
        data = dict(VALID_LOCAL_CONFIG)
        del data["database_id"]
        del data["timezone"]
        _write_json(data, self.json_path)
        with self.assertRaises(SettingError) as ctx:
            NotionConfig(self._local_config(), _make_logger())
        msg = str(ctx.exception)
        self.assertIn("database_id", msg)
        self.assertIn("timezone", msg)

    def test_local_does_not_call_dynamodb(self):
        _write_json(VALID_LOCAL_CONFIG, self.json_path)
        with patch("utils.dynamodb_utils.get_notion_config_by_uuid") as mock_db:
            NotionConfig(self._local_config(), _make_logger())
            mock_db.assert_not_called()


class TestNotionConfigCloudMode(unittest.TestCase):
    def test_cloud_calls_dynamodb(self):
        with patch("utils.dynamodb_utils.get_notion_config_by_uuid", return_value=copy.deepcopy(VALID_LOCAL_CONFIG)) as mock_db:
            config = {"mode": "cloud", "uuid": "uuid-cloud-123"}
            nc = NotionConfig(config, _make_logger())
            mock_db.assert_called_once_with("uuid-cloud-123")
            self.assertEqual(nc.get()["database_id"], "test-db-id")

    def test_cloud_dynamodb_error_raises_setting_error(self):
        with patch("utils.dynamodb_utils.get_notion_config_by_uuid", side_effect=RuntimeError("DDB down")):
            config = {"mode": "cloud", "uuid": "uuid-cloud-123"}
            with self.assertRaises(SettingError) as ctx:
                NotionConfig(config, _make_logger())
            self.assertIn("DDB down", str(ctx.exception))


class TestNotionConfigUnknownMode(unittest.TestCase):
    def test_unknown_mode_raises(self):
        config = {"mode": "legacy_local"}
        with self.assertRaises(SettingError) as ctx:
            NotionConfig(config, _make_logger())
        self.assertIn("legacy_local", str(ctx.exception))

    def test_none_mode_raises(self):
        config = {"mode": None}
        with self.assertRaises(SettingError):
            NotionConfig(config, _make_logger())


if __name__ == "__main__":
    unittest.main()
