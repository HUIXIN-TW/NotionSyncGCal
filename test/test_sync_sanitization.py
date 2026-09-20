import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))

from sync.sync import synchronize_notion_and_google_calendar  # noqa: E402

USER_SETTING = {
    "owner_user_uuid": "11111111-1111-4111-8111-111111111111",
    "settings_version": 1,
    "source_id": "source-1",
    "source_version": 1,
    "mapping_id": "mapping-1",
    "mapping_version": 1,
    "calendar_id": "primary@example.com",
    "page_property": {
        "Task_Notion_Name": "Task Name",
        "Date_Notion_Name": "Date",
        "GCal_Name_Notion_Name": "Calendar",
        "GCal_EventId_Notion_Name": "GCal Event Id",
        "GCal_Sync_Time_Notion_Name": "GCal Sync Time",
        "Delete_Notion_Name": "Delete",
        "GCal_End_Date_Notion_Name": "End Date",
    },
    "gcal_name_dict": {"Primary": "primary@example.com"},
    "gcal_id_dict": {"primary@example.com": "Primary"},
}


def _make_notion_task(event_id: str) -> dict:
    return {
        "id": "22222222-2222-4222-8222-222222222222",
        "last_edited_time": "2026-05-01T00:00:00.000Z",
        "properties": {
            "Calendar": {"select": {"name": "Primary"}},
            "GCal Event Id": {"rich_text": [{"plain_text": event_id}]},
            "GCal Sync Time": {"rich_text": []},
            "Delete": {"checkbox": False},
            "Task Name": {"title": [{"plain_text": "Highly sensitive task title"}]},
            "Date": {"date": {"start": "2026-05-23"}},
        },
    }


class SyncSanitizationTests(unittest.TestCase):
    def test_sync_errors_expose_safe_message_for_retriable_failures(self):
        notion_service = MagicMock()
        google_service = MagicMock()
        notion_service.get_notion_task.return_value = (
            {},
            [_make_notion_task("evt-123")],
        )
        google_service.upsert_projection.side_effect = RuntimeError(
            "private provider payload: secret summary and customer data"
        )

        result = synchronize_notion_and_google_calendar(
            user_setting=copy.deepcopy(USER_SETTING),
            notion_service=notion_service,
            google_service=google_service,
            compare_time=True,
            should_update_notion_tasks=True,
            should_update_google_events=True,
        )

        self.assertEqual(result["statusCode"], 200)
        error = result["body"]["message"]["errors"][0]
        self.assertEqual(error["action"], "upsert_gcal")
        self.assertEqual(error["error_code"], "runtime_error")
        self.assertEqual(
            error["error_message"],
            "Sync failed. See Lambda logs with aws_request_id for details.",
        )
        self.assertIsNone(error["error"])
        self.assertEqual(
            error["notion_task_id"],
            "22222222-2222-4222-8222-222222222222",
        )
        self.assertTrue(error["gcal_event_id"].startswith("n"))
        self.assertIsNone(error["gcal_event_start"])
        self.assertTrue(error["retriable"])
        self.assertNotIn("notion_task_name", error)
        self.assertNotIn("gcal_event_title", error)
        self.assertNotIn("debug_detail", error)

    def test_sync_errors_include_debug_detail_only_with_explicit_non_prod_flag(self):
        notion_service = MagicMock()
        google_service = MagicMock()
        notion_service.get_notion_task.return_value = (
            {},
            [_make_notion_task("evt-123")],
        )
        google_service.upsert_projection.side_effect = RuntimeError(
            "private provider payload: secret summary and customer data"
        )

        with patch.dict(
            "os.environ",
            {"ENVIRONMENT": "development", "EXPOSE_DEBUG_SYNC_ERRORS": "true"},
            clear=False,
        ):
            result = synchronize_notion_and_google_calendar(
                user_setting=copy.deepcopy(USER_SETTING),
                notion_service=notion_service,
                google_service=google_service,
                compare_time=True,
                should_update_notion_tasks=True,
                should_update_google_events=True,
            )

        self.assertEqual(result["statusCode"], 200)
        error = result["body"]["message"]["errors"][0]
        self.assertEqual(
            error["error_message"],
            "Sync failed. See Lambda logs with aws_request_id for details.",
        )
        self.assertIsNone(error["error"])
        self.assertIn("debug_detail", error)
        self.assertIn("RuntimeError", error["debug_detail"])


if __name__ == "__main__":
    unittest.main()
