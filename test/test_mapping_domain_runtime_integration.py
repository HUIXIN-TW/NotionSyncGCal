import argparse
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
for path in (REPO_ROOT, SRC_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import lambda_function  # noqa: E402
import src.main as main_module  # noqa: E402


def _property(property_id, property_name, property_type):
    return {
        "propertyId": property_id,
        "propertyName": property_name,
        "propertyType": property_type,
    }


def _cloud_rows(owner="user-1"):
    properties = {
        "task": _property("task-id", "Task", "title"),
        "date": _property("date-id", "Date", "date"),
        "calendarName": _property("calendar-name-id", "Calendar", "select"),
        "location": _property("location-id", "Location", "place"),
        "extraInfo": _property("extra-id", "Extra Info", "rich_text"),
        "googleCalendarEndDate": _property("end-id", "GCal End Date", "formula"),
        "googleCalendarDeleted": _property("deleted-id", "GCal Deleted?", "checkbox"),
        "googleCalendarEventId": _property("event-id", "GCal Event Id", "rich_text"),
        "googleCalendarSyncTime": _property("sync-id", "GCal Sync Time", "rich_text"),
        "googleCalendarIcon": _property("icon-id", "GCal Icon", "formula"),
    }
    source = {
        "id": "source-1",
        "ownerUserUuid": owner,
        "lifecycle": "active",
        "version": 1,
        "database": {
            "externalId": "05482e3c-4aca-40e0-9527-9ff2f2630e66",
            "url": "https://app.notion.com/p/05482e3c4aca40e095279ff2f2630e66",
            "name": "Task DB",
        },
        "defaults": {
            "goBackDays": 7,
            "goForwardDays": 100,
            "defaultEventLengthMinutes": 60,
            "defaultStartHour": 8,
            "defaultCalendarName": "Learning",
        },
        "propertyMappings": properties,
        "updatedAtMs": 1,
    }
    calendar_names = [
        "Learning",
        "School",
        "Registered Event",
        "Life",
        "Mission",
        "Job",
        "Other",
    ]
    mappings = [
        {
            "id": f"mapping-{index}",
            "ownerUserUuid": owner,
            "sourceId": "source-1",
            "calendarName": name,
            "calendarId": f"calendar-{index}@example.com",
            "lifecycle": "active",
            "version": 1,
            "updatedAtMs": 1,
        }
        for index, name in enumerate(calendar_names)
    ]
    settings = {
        "ownerUserUuid": owner,
        "timeZone": "Asia/Taipei",
        "timeCode": "+08:00",
        "version": 1,
        "updatedAtMs": 1,
    }
    return settings, [source], mappings


def _context():
    return type(
        "Context",
        (),
        {
            "function_name": "test-notion-sync",
            "aws_request_id": "req-1",
        },
    )()


class MappingDomainRefactorIntegrationTests(unittest.TestCase):
    def test_cloud_rows_expand_and_feed_existing_sync_algorithm(self):
        settings, sources, mappings = _cloud_rows()

        with patch.dict(os.environ, {"APP_MODE": "cloud"}, clear=True):
            with patch(
                "utils.dynamodb_utils.get_mapping_domain_settings",
                return_value=settings,
            ), patch(
                "utils.dynamodb_utils.list_mapping_domain_task_sources",
                return_value=sources,
            ), patch(
                "utils.dynamodb_utils.list_mapping_domain_calendar_mappings_for_owner",
                return_value=mappings,
            ), patch.object(
                main_module,
                "NotionToken",
            ) as notion_token_cls, patch.object(
                main_module,
                "GoogleToken",
            ) as google_token_cls, patch.object(
                main_module,
                "NotionService",
            ) as notion_service_cls, patch.object(
                main_module,
                "GoogleService",
            ) as google_service_cls, patch.object(
                main_module,
                "_parse_args",
                return_value=argparse.Namespace(
                    test_connection=False,
                    timestamp=None,
                    google=None,
                    notion=None,
                ),
            ), patch(
                "sync.sync.synchronize_notion_and_google_calendar",
                return_value={
                    "statusCode": 200,
                    "body": {"status": "sync_success", "message": "ok"},
                },
            ) as sync_fn:
                notion_token_cls.return_value.get.return_value = "notion-token"
                google_token_cls.return_value = MagicMock()

                result = main_module.main("user-1")

        self.assertEqual(result["statusCode"], 200)
        notion_service_cls.assert_called_once()
        google_service_cls.assert_called_once()

        setting = notion_service_cls.call_args.args[1]
        self.assertEqual(setting["source_id"], "source-1")
        self.assertEqual(setting["database_id"], "05482e3c-4aca-40e0-9527-9ff2f2630e66")
        self.assertEqual(setting["timezone"], "Asia/Taipei")
        self.assertEqual(setting["timecode"], "+08:00")
        self.assertEqual(setting["gcal_default_name"], "Learning")
        self.assertEqual(
            list(setting["gcal_name_dict"]),
            ["Learning", "Job", "Life", "Mission", "Other", "Registered Event", "School"],
        )
        self.assertEqual(setting["page_property"]["GCal_EventId_Notion_Name"], "event-id")
        self.assertEqual(setting["page_property"]["GCal_Sync_Time_Notion_Name"], "sync-id")

        sync_fn.assert_called_once()
        self.assertIs(sync_fn.call_args.kwargs["user_setting"], setting)
        self.assertTrue(sync_fn.call_args.kwargs["should_update_notion_tasks"])
        self.assertTrue(sync_fn.call_args.kwargs["should_update_google_events"])


class LambdaToMainIntegrationTests(unittest.TestCase):
    def test_sqs_handler_calls_main_with_uuid_only(self):
        seen = []

        def strict_main(uuid):
            seen.append(uuid)
            return {
                "statusCode": 200,
                "body": {"status": "sync_success", "message": "ok"},
            }

        event = {
            "Records": [
                {
                    "messageId": "msg-1",
                    "body": json.dumps({"uuid": "user-1"}),
                    "eventSource": "aws:sqs",
                }
            ]
        }

        with patch("src.main.main", new=strict_main), patch(
            "src.utils.lambda_utils._save_sync_logs"
        ):
            result = lambda_function.lambda_handler(event, _context())

        self.assertEqual(seen, ["user-1"])
        self.assertEqual(result["batchItemFailures"], [])
        self.assertEqual(result["success_count"], 1)

    def test_eventbridge_handler_calls_main_with_uuid_only(self):
        seen = []

        def strict_main(uuid):
            seen.append(uuid)
            return {
                "statusCode": 200,
                "body": {"status": "sync_success", "message": "ok"},
            }

        event = {
            "id": "event-1",
            "detail-type": "Notica Sync",
            "source": "notica.sync",
            "time": "2026-09-22T00:00:00Z",
            "detail": {"uuid": "user-1"},
        }

        with patch("src.main.main", new=strict_main), patch(
            "src.utils.lambda_utils._save_sync_logs"
        ):
            result = lambda_function.lambda_handler(event, _context())

        self.assertEqual(seen, ["user-1"])
        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(result["status"], "sync_success")


if __name__ == "__main__":
    unittest.main()
