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


def _make_timed_task(
    start="2026-10-09T22:00:00.000Z",
    end="2026-10-10T04:00:00.000Z",
):
    return {
        "id": "notion-page-1",
        "url": "https://www.notion.so/page-1",
        "properties": {
            "Task": {
                "id": "task-id",
                "title": [{"plain_text": "Herdsman Lake"}],
            },
            "Date": {
                "id": "date-id",
                "date": {
                    "start": start,
                    "end": end,
                },
            },
            "Notes": {
                "id": "extra-id",
                "rich_text": [{"plain_text": "Route notes"}],
            },
            "Location": {
                "id": "location-id",
                "place": {"address": "Herdsman Lake"},
            },
            "Icon": {
                "id": "icon-id",
                "formula": {"string": "🏕️"},
            },
        },
    }


class GoogleCalendarDateSerializationTests(unittest.TestCase):
    def _make_service(self):
        api = MagicMock()
        with patch("gcal.gcal_service.build", return_value=api):
            service = GoogleService(SETTING, MagicMock(), MagicMock())
        service.service = api
        return service, api

    def test_utc_timed_input_is_serialized_as_rfc3339_in_configured_timezone(self):
        service, _ = self._make_service()

        start, end = service.adjust_notion_dates(
            "2026-10-09T22:00:00.000Z",
            "2026-10-10T04:00:00.000Z",
        )

        self.assertEqual(start, "2026-10-10T06:00:00+08:00")
        self.assertEqual(end, "2026-10-10T12:00:00+08:00")
        self.assertNotIn("+0800", start)
        self.assertNotIn("+0000", start)

    def test_explicit_offset_timed_input_remains_rfc3339(self):
        service, _ = self._make_service()

        start, end = service.adjust_notion_dates(
            "2026-10-10T06:00:00+08:00",
            "2026-10-10T12:00:00+08:00",
        )

        self.assertEqual(start, "2026-10-10T06:00:00+08:00")
        self.assertEqual(end, "2026-10-10T12:00:00+08:00")

    def test_missing_timed_end_uses_default_duration(self):
        service, _ = self._make_service()

        start, end = service.adjust_notion_dates(
            "2026-10-10T06:00:00+08:00",
        )

        self.assertEqual(start, "2026-10-10T06:00:00+08:00")
        self.assertEqual(end, "2026-10-10T07:00:00+08:00")

    def test_all_day_event_keeps_date_only_contract(self):
        service, _ = self._make_service()

        start, end = service.adjust_notion_dates(
            "2026-10-10",
            "2026-10-10",
        )

        self.assertEqual(start, "2026-10-10")
        self.assertEqual(end, "2026-10-11")

    def test_event_body_uses_rfc3339_datetime_and_configured_timezone(self):
        service, _ = self._make_service()

        event = service.make_event_body(_make_timed_task())

        self.assertEqual(
            event["start"],
            {
                "dateTime": "2026-10-10T06:00:00+08:00",
                "timeZone": "Australia/Perth",
            },
        )
        self.assertEqual(
            event["end"],
            {
                "dateTime": "2026-10-10T12:00:00+08:00",
                "timeZone": "Australia/Perth",
            },
        )

    def test_update_patches_existing_event_id_with_rfc3339_body(self):
        service, api = self._make_service()

        service.update_gcal_event(
            _make_timed_task(),
            CALENDAR_ID,
            "f6919vlvjaq4jcid56vvmp94uo",
        )

        api.events.return_value.patch.assert_called_once()
        kwargs = api.events.return_value.patch.call_args.kwargs
        self.assertEqual(kwargs["calendarId"], CALENDAR_ID)
        self.assertEqual(kwargs["eventId"], "f6919vlvjaq4jcid56vvmp94uo")
        self.assertEqual(
            kwargs["body"]["start"]["dateTime"],
            "2026-10-10T06:00:00+08:00",
        )
        self.assertEqual(
            kwargs["body"]["end"]["dateTime"],
            "2026-10-10T12:00:00+08:00",
        )
        api.events.return_value.insert.assert_not_called()
        api.events.return_value.delete.assert_not_called()


if __name__ == "__main__":
    unittest.main()
