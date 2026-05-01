import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))

import main as main_module  # noqa: E402


BASE_SETTING = {
    "database_id": "test-db-id",
    "goback_days": 1,
    "goforward_days": 2,
    "timecode": "+08:00",
    "timezone": "Asia/Taipei",
    "default_event_length": 60,
    "default_start_time": 8,
    "gcal_name_dict": {"TestCal": "test@gmail.com"},
    "gcal_id_dict": {"test@gmail.com": "TestCal"},
    "gcal_default_name": "TestCal",
    "gcal_default_id": "test@gmail.com",
    "page_property": {
        "Task_Notion_Name": "Task Name",
        "Date_Notion_Name": "Date",
        "GCal_Name_Notion_Name": "Calendar",
        "GCal_EventId_Notion_Name": "GCal Event Id",
        "GCal_Sync_Time_Notion_Name": "GCal Sync Time",
        "Delete_Notion_Name": "GCal Deleted?",
    },
}


class FakeNotionConfig:
    setting = None

    def __init__(self, config, logger):
        self.config = config
        self.logger = logger

    def get(self):
        return self.setting


class MainCliOverrideTests(unittest.TestCase):
    def _run_main_with_args(self, args, sync_patch_name):
        setting = copy.deepcopy(BASE_SETTING)
        FakeNotionConfig.setting = setting

        with (
            patch.object(sys, "argv", ["src/main.py", *args]),
            patch.object(
                main_module,
                "generate_config",
                return_value={"mode": "local"},
            ),
            patch.object(main_module, "NotionConfig", FakeNotionConfig),
            patch.object(main_module, "NotionToken", return_value=MagicMock()),
            patch.object(main_module, "GoogleToken", return_value=MagicMock()),
            patch.object(
                main_module,
                "NotionService",
                return_value=MagicMock(name="notion_service"),
            ),
            patch.object(
                main_module,
                "GoogleService",
                return_value=MagicMock(name="google_service"),
            ),
            patch(
                sync_patch_name,
                return_value={"statusCode": 200},
            ) as mock_sync,
        ):
            result = main_module.main("")

        mock_sync.assert_called_once()
        return result, setting, mock_sync

    def test_default_run_uses_loaded_setting_without_override(self):
        result, setting, mock_sync = self._run_main_with_args(
            [],
            "sync.sync.synchronize_notion_and_google_calendar",
        )

        self.assertEqual(result, {"statusCode": 200})
        self.assertEqual(setting["goback_days"], 1)
        self.assertEqual(setting["goforward_days"], 2)
        self.assertIs(mock_sync.call_args.kwargs["user_setting"], setting)

    def test_timestamp_flag_applies_date_range_in_memory(self):
        result, setting, mock_sync = self._run_main_with_args(
            ["-t", "3", "9"],
            "sync.sync.synchronize_notion_and_google_calendar",
        )

        self.assertEqual(result, {"statusCode": 200})
        self.assertEqual(setting["goback_days"], 3)
        self.assertEqual(setting["goforward_days"], 9)
        self.assertTrue(setting["google_timemin"].endswith("+08:00"))
        self.assertTrue(setting["google_timemax"].endswith("+08:00"))
        self.assertIs(mock_sync.call_args.kwargs["user_setting"], setting)

    def test_google_force_flag_uses_in_memory_setting_dict(self):
        result, setting, mock_sync = self._run_main_with_args(
            ["-g", "4", "10"],
            (
                "sync.sync."
                "force_update_notion_tasks_by_google_event_and_ignore_time"
            ),
        )

        self.assertEqual(result, {"statusCode": 200})
        self.assertEqual(setting["goback_days"], 4)
        self.assertEqual(setting["goforward_days"], 10)
        self.assertIs(mock_sync.call_args.kwargs["user_setting"], setting)

    def test_notion_force_flag_uses_in_memory_setting_dict(self):
        result, setting, mock_sync = self._run_main_with_args(
            ["-n", "6", "12"],
            (
                "sync.sync."
                "force_update_google_event_by_notion_task_and_ignore_time"
            ),
        )

        self.assertEqual(result, {"statusCode": 200})
        self.assertEqual(setting["goback_days"], 6)
        self.assertEqual(setting["goforward_days"], 12)
        self.assertIs(mock_sync.call_args.kwargs["user_setting"], setting)


if __name__ == "__main__":
    unittest.main()
