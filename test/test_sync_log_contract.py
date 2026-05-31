import copy
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))

from sync.sync import synchronize_notion_and_google_calendar  # noqa: E402
import utils.lambda_utils as lambda_utils  # noqa: E402

USER_SETTING = {
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
    "gcal_default_name": "Primary",
    "gcal_default_id": "primary@example.com",
}


class SyncContractTests(unittest.TestCase):
    def test_sync_success_message_contract_shape(self):
        notion_service = MagicMock()
        google_service = MagicMock()

        notion_service.get_notion_task.return_value = ({"db": "x"}, [])
        google_service.get_gcal_event.return_value = []

        result = synchronize_notion_and_google_calendar(
            user_setting=copy.deepcopy(USER_SETTING),
            notion_service=notion_service,
            google_service=google_service,
            compare_time=True,
            should_update_notion_tasks=True,
            should_update_google_events=True,
        )

        self.assertEqual(result["statusCode"], 200)
        body = result["body"]
        self.assertIn("status", body)
        self.assertIn("message", body)
        message = body["message"]
        self.assertIn(type(message), (dict, str))
        if isinstance(message, dict):
            self.assertIn("summary", message)
            self.assertIn("trigger_time", message)
            self.assertIn("errors", message)
            self.assertIsInstance(message["errors"], list)

    def test_persisted_log_contract_has_required_top_level_fields(self):
        logger = MagicMock()
        logger.level = 20
        ctx = MagicMock()
        ctx.function_name = "lambda-fn"
        ctx.aws_request_id = "request-id"
        start = datetime.now(timezone.utc)

        sync_result = {
            "statusCode": 200,
            "body": {
                "status": "sync_success",
                "message": {
                    "summary": {"google_event_count": 1, "notion_task_count": 1},
                    "trigger_time": "2026-05-23T00:00:00.000Z",
                    "errors": [
                        {
                            "action": "update_notion",
                            "error_code": "runtime_error",
                            "error": "provider failure",
                            "gcal_event_title": "title",
                            "notion_task_name": "task",
                            "gcal_event_start": "2026-05-23T09:00:00+08:00",
                            "gcal_event_id": "evt-1",
                            "notion_task_id": "page-1",
                            "retriable": True,
                        }
                    ],
                },
            },
        }

        with patch.object(lambda_utils, "_save_sync_logs") as mock_save:
            lambda_utils.process_and_log_sync_result(
                logger_obj=logger,
                sync_result=sync_result,
                context=ctx,
                uuid="real-uuid",
                lambda_start_time=start,
                trigger_name="sqs",
            )

        payload = mock_save.call_args[0][1]

        required_top_level_keys = {
            "contract_version",
            "trigger_by",
            "uuid",
            "statusCode",
            "status",
            "message",
            "lambda_name",
            "aws_request_id",
            "log_level",
            "duration_ms",
        }
        self.assertTrue(required_top_level_keys.issubset(payload.keys()))
        self.assertEqual(payload["contract_version"], lambda_utils.SYNC_LOG_CONTRACT_VERSION)

        persisted_errors = payload["message"]["errors"]
        self.assertEqual(len(persisted_errors), 1)

        required_error_keys = {
            "action",
            "error_code",
            "error_message",
            "error",
            "gcal_event_title",
            "notion_task_name",
            "gcal_event_start",
            "gcal_event_id",
            "notion_task_id",
            "retriable",
        }
        self.assertTrue(required_error_keys.issubset(persisted_errors[0].keys()))
        self.assertEqual(
            persisted_errors[0]["error_message"],
            lambda_utils.SAFE_SYNC_FAILURE_MESSAGE,
        )
        self.assertIsNone(persisted_errors[0]["error"])


if __name__ == "__main__":
    unittest.main()
