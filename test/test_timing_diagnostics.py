import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))

from gcal.gcal_service import GoogleService  # noqa: E402
from notion.notion_service import NotionService  # noqa: E402


CALENDAR_ID = "cal@group.calendar.google.com"
SETTING = {
    "before_date": "2026-10-20",
    "after_date": "2026-10-01",
    "timezone": "Australia/Perth",
    "database_id": "db-id",
    "default_event_length": 60,
    "gcal_default_id": CALENDAR_ID,
    "page_property": {
        "Task_Notion_Name": "task-id",
        "Date_Notion_Name": "date-id",
        "GCal_End_Date_Notion_Name": "end-id",
        "ExtraInfo_Notion_Name": "extra-id",
        "Location_Notion_Name": "location-id",
        "CompleteIcon_Notion_Name": "icon-id",
    },
}


def _timed_task():
    return {
        "id": "notion-page-1",
        "last_edited_time": "2026-10-05T12:20:00.342Z",
        "url": "https://notion.example/private-page",
        "properties": {
            "Task": {
                "id": "task-id",
                "title": [{"plain_text": "Sensitive task title"}],
            },
            "Date": {
                "id": "date-id",
                "date": {
                    "start": "2026-10-09T22:00:00.000Z",
                    "end": "2026-10-10T04:00:00.000Z",
                },
            },
            "Extra": {
                "id": "extra-id",
                "rich_text": [{"plain_text": "Sensitive notes"}],
            },
            "Location": {
                "id": "location-id",
                "place": {"address": "Sensitive location"},
            },
            "Icon": {
                "id": "icon-id",
                "formula": {"string": "🏕️"},
            },
        },
    }


class TimingDiagnosticsTests(unittest.TestCase):
    def test_notion_query_logs_only_timing_fields_for_returned_task(self):
        logger = MagicMock()
        client = MagicMock()
        task = _timed_task()

        with patch("notion.notion_service.Client", return_value=client):
            service = NotionService("token", SETTING, logger)

        service._query_database_with_pagination = MagicMock(return_value=[task])

        _, tasks = service.get_notion_task()

        self.assertEqual(tasks, [task])
        logger.info.assert_any_call(
            "Notion timing input task_id=%s start=%s end=%s last_edited=%s",
            "notion-page-1",
            "2026-10-09T22:00:00.000Z",
            "2026-10-10T04:00:00.000Z",
            "2026-10-05T12:20:00.342Z",
        )
        rendered_logs = " ".join(str(call) for call in logger.info.call_args_list)
        self.assertNotIn("Sensitive task title", rendered_logs)
        self.assertNotIn("Sensitive notes", rendered_logs)
        self.assertNotIn("Sensitive location", rendered_logs)
        self.assertNotIn("https://notion.example/private-page", rendered_logs)

    def test_gcal_update_logs_normalized_and_outgoing_timing_without_private_fields(self):
        logger = MagicMock()
        api = MagicMock()

        with patch("gcal.gcal_service.build", return_value=api):
            service = GoogleService(SETTING, MagicMock(), logger)

        service.update_gcal_event(
            _timed_task(),
            CALENDAR_ID,
            "event-123",
        )

        expected_start = {
            "dateTime": "2026-10-09T22:00:00+0000",
            "timeZone": "Australia/Perth",
        }
        expected_end = {
            "dateTime": "2026-10-10T04:00:00+0000",
            "timeZone": "Australia/Perth",
        }
        logger.info.assert_any_call(
            "GCal timing normalization raw_start=%s raw_end=%s normalized_start=%s normalized_end=%s",
            "2026-10-09T22:00:00.000Z",
            "2026-10-10T04:00:00.000Z",
            "2026-10-09T22:00:00+0000",
            "2026-10-10T04:00:00+0000",
        )
        logger.info.assert_any_call(
            "GCal update timing event_id=%s calendar_id=%s start=%s end=%s",
            "event-123",
            CALENDAR_ID,
            expected_start,
            expected_end,
        )

        patch_call = api.events.return_value.patch.call_args.kwargs
        self.assertEqual(patch_call["eventId"], "event-123")
        self.assertEqual(patch_call["calendarId"], CALENDAR_ID)
        self.assertEqual(patch_call["body"]["start"], expected_start)
        self.assertEqual(patch_call["body"]["end"], expected_end)

        rendered_logs = " ".join(str(call) for call in logger.info.call_args_list)
        self.assertNotIn("Sensitive task title", rendered_logs)
        self.assertNotIn("Sensitive notes", rendered_logs)
        self.assertNotIn("Sensitive location", rendered_logs)
        self.assertNotIn("https://notion.example/private-page", rendered_logs)


if __name__ == "__main__":
    unittest.main()
