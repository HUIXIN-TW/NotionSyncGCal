import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))

import main as main_module  # noqa: E402


BASE_SETTING = {
    "source_id": "source-1",
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
        "Task_Notion_Name": "task-id",
        "Date_Notion_Name": "date-id",
        "GCal_Name_Notion_Name": "calendar-id",
        "GCal_EventId_Notion_Name": "event-id",
        "GCal_Sync_Time_Notion_Name": "sync-id",
        "Delete_Notion_Name": "deleted-id",
        "GCal_End_Date_Notion_Name": "end-id",
        "Location_Notion_Name": "location-id",
        "ExtraInfo_Notion_Name": "extra-id",
        "CompleteIcon_Notion_Name": "icon-id",
    },
}


class FakeMappingDomainConfig:
    settings = None

    def __init__(self, config, logger):
        self.config = config
        self.logger = logger

    def get(self):
        return self.settings


class MainCliOverrideTests(unittest.TestCase):
    def _run_main_with_args(self, args, sync_patch_name):
        setting = copy.deepcopy(BASE_SETTING)
        FakeMappingDomainConfig.settings = [setting]

        with (
            patch.object(sys, "argv", ["src/main.py", *args]),
            patch.object(
                main_module,
                "generate_config",
                return_value={"mode": "local"},
            ),
            patch.object(
                main_module,
                "MappingDomainConfig",
                FakeMappingDomainConfig,
            ),
            patch.object(main_module, "NotionToken") as notion_token_cls,
            patch.object(main_module, "GoogleToken") as google_token_cls,
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
                return_value={
                    "statusCode": 200,
                    "body": {"status": "sync_success", "message": {}},
                },
            ) as mock_sync,
        ):
            notion_token_cls.return_value.get.return_value = MagicMock()
            google_token_cls.return_value = MagicMock()
            result = main_module.main("user-1")

        mock_sync.assert_called_once()
        return result, setting, mock_sync

    def test_default_run_preserves_loaded_event_id_setting(self):
        result, setting, mock_sync = self._run_main_with_args(
            [],
            "sync.sync.synchronize_notion_and_google_calendar",
        )

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(
            setting["page_property"]["GCal_EventId_Notion_Name"],
            "event-id",
        )
        self.assertIs(mock_sync.call_args.kwargs["user_setting"], setting)

    def test_timestamp_flag_applies_date_range_in_memory(self):
        result, setting, mock_sync = self._run_main_with_args(
            ["-t", "3", "9"],
            "sync.sync.synchronize_notion_and_google_calendar",
        )

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(setting["goback_days"], 3)
        self.assertEqual(setting["goforward_days"], 9)
        self.assertTrue(setting["google_timemin"].endswith("+08:00"))
        self.assertTrue(setting["google_timemax"].endswith("+08:00"))
        self.assertIs(mock_sync.call_args.kwargs["user_setting"], setting)

    def test_google_force_flag_preserves_existing_direction(self):
        result, setting, mock_sync = self._run_main_with_args(
            ["-g", "4", "10"],
            "sync.sync.force_update_notion_tasks_by_google_event_and_ignore_time",
        )

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(setting["goback_days"], 4)
        self.assertEqual(setting["goforward_days"], 10)
        self.assertIs(mock_sync.call_args.kwargs["user_setting"], setting)

    def test_notion_force_flag_preserves_existing_direction(self):
        result, setting, mock_sync = self._run_main_with_args(
            ["-n", "6", "12"],
            "sync.sync.force_update_google_event_by_notion_task_and_ignore_time",
        )

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(setting["goback_days"], 6)
        self.assertEqual(setting["goforward_days"], 12)
        self.assertIs(mock_sync.call_args.kwargs["user_setting"], setting)

    def test_runs_each_normalized_task_source_independently(self):
        first = copy.deepcopy(BASE_SETTING)
        second = copy.deepcopy(BASE_SETTING)
        second["source_id"] = "source-2"
        second["database_id"] = "db-2"
        FakeMappingDomainConfig.settings = [first, second]

        with (
            patch.object(sys, "argv", ["src/main.py"]),
            patch.object(main_module, "generate_config", return_value={"mode": "local"}),
            patch.object(main_module, "MappingDomainConfig", FakeMappingDomainConfig),
            patch.object(main_module, "NotionToken") as notion_token_cls,
            patch.object(main_module, "GoogleToken"),
            patch.object(main_module, "NotionService", return_value=MagicMock()),
            patch.object(main_module, "GoogleService", return_value=MagicMock()),
            patch(
                "sync.sync.synchronize_notion_and_google_calendar",
                return_value={
                    "statusCode": 200,
                    "body": {"status": "sync_success", "message": {}},
                },
            ) as mock_sync,
        ):
            notion_token_cls.return_value.get.return_value = MagicMock()
            result = main_module.main("user-1")

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(mock_sync.call_count, 2)


if __name__ == "__main__":
    unittest.main()
