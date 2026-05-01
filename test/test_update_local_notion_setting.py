import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))

from user_setting import update_local_notion_setting  # noqa: E402


def _local_config():
    return {
        "database_id": "database-placeholder",
        "goback_days": 1,
        "goforward_days": 2,
        "timecode": "+08:00",
        "timezone": "Asia/Taipei",
        "default_event_length": 60,
        "default_start_time": 8,
        "gcal_dic": [{"My Calendar": "calendar-placeholder"}],
        "page_property": [{"Task_Notion_Name": "Task Name"}],
    }


class UpdateLocalNotionSettingTests(unittest.TestCase):
    def _with_temp_config(self):
        temp_dir = tempfile.TemporaryDirectory()
        path = Path(temp_dir.name) / "config" / "local.notion-setting.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(_local_config()), encoding="utf-8")
        self.addCleanup(temp_dir.cleanup)
        return path

    def test_helper_targets_config_local_notion_setting_not_token_dir(self):
        self.assertTrue(
            str(update_local_notion_setting.NOTION_SETTINGS_PATH).endswith("config/local.notion-setting.json")
        )
        self.assertNotIn("token/", str(update_local_notion_setting.NOTION_SETTINGS_PATH))

    def test_update_date_range_writes_local_config_and_preserves_existing_fields(self):
        path = self._with_temp_config()
        with (
            patch.object(update_local_notion_setting, "NOTION_SETTINGS_PATH", path),
            patch.dict(os.environ, {"APP_MODE": "local"}, clear=True),
        ):
            update_local_notion_setting.update_date_range(3, 9)

        updated = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(updated["goback_days"], 3)
        self.assertEqual(updated["goforward_days"], 9)
        self.assertEqual(updated["database_id"], "database-placeholder")
        self.assertEqual(updated["gcal_dic"], [{"My Calendar": "calendar-placeholder"}])

    def test_update_date_range_does_not_add_notion_token(self):
        path = self._with_temp_config()
        with (
            patch.object(update_local_notion_setting, "NOTION_SETTINGS_PATH", path),
            patch.dict(os.environ, {"APP_MODE": "local"}, clear=True),
        ):
            update_local_notion_setting.update_date_range(4, 10)

        updated = json.loads(path.read_text(encoding="utf-8"))
        self.assertNotIn("notion_token", updated)

    def test_update_rejects_non_local_app_mode(self):
        path = self._with_temp_config()
        with (
            patch.object(update_local_notion_setting, "NOTION_SETTINGS_PATH", path),
            patch.dict(os.environ, {"APP_MODE": "cloud"}, clear=True),
        ):
            with self.assertRaises(update_local_notion_setting.LocalSettingUpdateError):
                update_local_notion_setting.update_date_range(5, 11)

    def test_update_notion_token_is_not_supported(self):
        with self.assertRaises(update_local_notion_setting.LocalSettingUpdateError):
            update_local_notion_setting.update_notion_token("secret-token")


if __name__ == "__main__":
    unittest.main()
