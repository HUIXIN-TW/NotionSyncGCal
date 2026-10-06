import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))

from gcal.gcal_service import GoogleService  # noqa: E402


CALENDAR_ID = "cal@group.calendar.google.com"
SETTING = {
    "timezone": "Australia/Perth",
    "default_event_length": 60,
    "gcal_default_id": CALENDAR_ID,
    "page_property": {
        "Task_Notion_Name": "task-id",
        "Date_Notion_Name": "date-id",
        "ExtraInfo_Notion_Name": "extra-id",
        "Location_Notion_Name": "location-id",
        "CompleteIcon_Notion_Name": "icon-id",
    },
}


def _task(start, end):
    return {
        "id": "notion-page-1",
        "url": "https://notion.example/page",
        "properties": {
            "Task": {
                "id": "task-id",
                "title": [{"plain_text": "Transition test"}],
            },
            "Date": {
                "id": "date-id",
                "date": {
                    "start": start,
                    "end": end,
                },
            },
            "Extra": {
                "id": "extra-id",
                "rich_text": [],
            },
            "Location": {
                "id": "location-id",
                "place": {"address": ""},
            },
            "Icon": {
                "id": "icon-id",
                "formula": {"string": ""},
            },
        },
    }


class GoogleCalendarTimedTransitionTests(unittest.TestCase):
    def _service(self):
        logger = MagicMock()
        api = MagicMock()
        with patch("gcal.gcal_service.build", return_value=api):
            service = GoogleService(SETTING, MagicMock(), logger)
        return service, api

    def test_timed_update_clears_previous_all_day_date_representation(self):
        service, api = self._service()

        service.update_gcal_event(
            _task(
                "2026-10-06T20:00:00.000+08:00",
                "2026-10-06T20:00:00.000+08:00",
            ),
            CALENDAR_ID,
            "existing-event-123",
        )

        patch_call = api.events.return_value.patch.call_args.kwargs
        self.assertEqual(patch_call["calendarId"], CALENDAR_ID)
        self.assertEqual(patch_call["eventId"], "existing-event-123")
        self.assertEqual(
            patch_call["body"]["start"],
            {
                "dateTime": "2026-10-06T20:00:00+0800",
                "timeZone": "Australia/Perth",
                "date": None,
            },
        )
        self.assertEqual(
            patch_call["body"]["end"],
            {
                "dateTime": "2026-10-06T21:00:00+0800",
                "timeZone": "Australia/Perth",
                "date": None,
            },
        )
        api.events.return_value.update.assert_not_called()
        api.events.return_value.insert.assert_not_called()

    def test_timed_create_does_not_include_patch_only_clear_fields(self):
        service, api = self._service()
        api.events.return_value.insert.return_value.execute.return_value = {
            "id": "new-event-123",
        }

        event_id = service.create_gcal_event(
            _task(
                "2026-10-06T20:00:00.000+08:00",
                "2026-10-06T21:00:00.000+08:00",
            ),
            CALENDAR_ID,
        )

        self.assertEqual(event_id, "new-event-123")
        body = api.events.return_value.insert.call_args.kwargs["body"]
        self.assertEqual(
            body["start"],
            {
                "dateTime": "2026-10-06T20:00:00+0800",
                "timeZone": "Australia/Perth",
            },
        )
        self.assertEqual(
            body["end"],
            {
                "dateTime": "2026-10-06T21:00:00+0800",
                "timeZone": "Australia/Perth",
            },
        )
        self.assertNotIn("date", body["start"])
        self.assertNotIn("date", body["end"])

    def test_all_day_update_remains_date_only(self):
        service, api = self._service()

        service.update_gcal_event(
            _task("2026-10-09", None),
            CALENDAR_ID,
            "existing-all-day-123",
        )

        body = api.events.return_value.patch.call_args.kwargs["body"]
        self.assertEqual(body["start"], {"date": "2026-10-09"})
        self.assertEqual(body["end"], {"date": "2026-10-10"})
        self.assertNotIn("dateTime", body["start"])
        self.assertNotIn("dateTime", body["end"])


if __name__ == "__main__":
    unittest.main()
