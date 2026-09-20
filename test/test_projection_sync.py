import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))

from sync.contracts import StaleExecutionError  # noqa: E402
from sync.projection_identity import ProjectionIdentityError  # noqa: E402
from sync.sync import (  # noqa: E402
    force_update_notion_tasks_by_google_event_and_ignore_time,
    project_notion_to_google_calendar,
)


SETTING = {
    "owner_user_uuid": "11111111-1111-4111-8111-111111111111",
    "settings_version": 1,
    "source_id": "source-1",
    "source_version": 1,
    "mapping_id": "mapping-1",
    "mapping_version": 1,
    "calendar_id": "calendar@example.com",
    "database_id": "database-1",
    "page_property": {
        "Task_Notion_Name": "Task",
        "Date_Notion_Name": "Date",
        "Delete_Notion_Name": "Delete",
    },
}
TASK_ONE = "22222222-2222-4222-8222-222222222222"
TASK_TWO = "33333333-3333-4333-8333-333333333333"


def _task(task_id, *, deleted=False):
    return {
        "id": task_id,
        "properties": {
            "Task": {"title": [{"plain_text": "Task"}]},
            "Date": {"date": {"start": "2026-09-20"}},
            "Delete": {"checkbox": deleted},
        },
    }


class OneWayProjectionTests(unittest.TestCase):
    def test_active_task_only_upserts_google_projection(self):
        notion = MagicMock()
        google = MagicMock()
        notion.get_notion_task.return_value = ({}, [_task(TASK_ONE)])

        result = project_notion_to_google_calendar(
            copy.deepcopy(SETTING),
            notion,
            google,
        )

        self.assertEqual(result["statusCode"], 200)
        google.upsert_projection.assert_called_once()
        google.delete_projection.assert_not_called()
        notion.update_notion_task.assert_not_called()
        notion.create_notion_task.assert_not_called()
        notion.delete_notion_task.assert_not_called()

    def test_deleted_task_only_deletes_owned_projection(self):
        notion = MagicMock()
        google = MagicMock()
        notion.get_notion_task.return_value = ({}, [_task(TASK_ONE, deleted=True)])

        project_notion_to_google_calendar(copy.deepcopy(SETTING), notion, google)

        google.delete_projection.assert_called_once()
        google.upsert_projection.assert_not_called()
        notion.delete_notion_task.assert_not_called()

    def test_stale_execution_stops_remaining_provider_writes_without_retry(self):
        notion = MagicMock()
        google = MagicMock()
        notion.get_notion_task.return_value = (
            {},
            [_task(TASK_ONE), _task(TASK_TWO)],
        )
        google.upsert_projection.side_effect = StaleExecutionError("stale")

        result = project_notion_to_google_calendar(
            copy.deepcopy(SETTING),
            notion,
            google,
        )

        self.assertEqual(google.upsert_projection.call_count, 1)
        error = result["body"]["message"]["errors"][0]
        self.assertEqual(error["error_code"], "stale_execution_snapshot")
        self.assertFalse(error["retriable"])

    def test_projection_identity_mismatch_is_non_retriable(self):
        notion = MagicMock()
        google = MagicMock()
        notion.get_notion_task.return_value = ({}, [_task(TASK_ONE)])
        google.upsert_projection.side_effect = ProjectionIdentityError("wrong owner")

        result = project_notion_to_google_calendar(
            copy.deepcopy(SETTING),
            notion,
            google,
        )

        error = result["body"]["message"]["errors"][0]
        self.assertEqual(error["error_code"], "projection_identity_mismatch")
        self.assertFalse(error["retriable"])

    def test_provider_failure_is_retryable_but_never_writes_notion(self):
        notion = MagicMock()
        google = MagicMock()
        notion.get_notion_task.return_value = ({}, [_task(TASK_ONE)])
        google.upsert_projection.side_effect = RuntimeError("provider unavailable")

        result = project_notion_to_google_calendar(
            copy.deepcopy(SETTING),
            notion,
            google,
        )

        error = result["body"]["message"]["errors"][0]
        self.assertTrue(error["retriable"])
        notion.update_notion_task.assert_not_called()
        notion.create_notion_task.assert_not_called()

    def test_legacy_google_to_notion_entry_point_fails_closed(self):
        notion = MagicMock()
        google = MagicMock()

        result = force_update_notion_tasks_by_google_event_and_ignore_time(
            copy.deepcopy(SETTING),
            notion,
            google,
        )

        self.assertEqual(result["statusCode"], 409)
        self.assertEqual(
            result["body"]["message"]["error_code"],
            "google_to_notion_sync_not_supported",
        )
        notion.update_notion_task.assert_not_called()
        notion.create_notion_task.assert_not_called()


if __name__ == "__main__":
    unittest.main()
