import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))

from gcal.gcal_service import GoogleService  # noqa: E402
from notion.notion_service import NotionService  # noqa: E402


SETTING = {
    "database_id": "db-id",
    "timecode": "+08:00",
    "timezone": "Asia/Taipei",
    "default_event_length": 60,
    "gcal_name_dict": {"Learning": "learning@example.com"},
    "gcal_id_dict": {"learning@example.com": "Learning"},
    "gcal_default_name": "Learning",
    "gcal_default_id": "learning@example.com",
    "page_property": {
        "Task_Notion_Name": "task-id",
        "Date_Notion_Name": "date-id",
        "ExtraInfo_Notion_Name": "extra-id",
        "Location_Notion_Name": "location-id",
        "GCal_Sync_Time_Notion_Name": "sync-id",
        "GCal_EventId_Notion_Name": "event-id",
        "GCal_Name_Notion_Name": "calendar-id",
        "Delete_Notion_Name": "delete-id",
        "CompleteIcon_Notion_Name": "icon-id",
        "GCal_End_Date_Notion_Name": "end-id",
    },
}


class NotionServicePropertyIdTests(unittest.TestCase):
    def test_update_uses_provider_property_ids_as_write_keys(self):
        client = MagicMock()
        with patch("notion.notion_service.Client", return_value=client):
            service = NotionService("token", SETTING, MagicMock())

        service.update_notion_task_for_new_gcal_sync_time(
            "page-id",
            "2026-09-22T12:00:00Z",
        )

        properties = client.pages.update.call_args.kwargs["properties"]
        self.assertEqual(list(properties), ["sync-id"])
        self.assertNotIn("GCal Sync Time", properties)


class GoogleServicePropertyIdTests(unittest.TestCase):
    def test_event_body_reads_renamed_notion_properties_by_provider_id(self):
        with patch("gcal.gcal_service.build"):
            service = GoogleService(SETTING, MagicMock(), MagicMock())

        page = {
            "url": "https://www.notion.so/page",
            "properties": {
                "Renamed Task": {
                    "id": "task-id",
                    "title": [{"plain_text": "Strict ID task"}],
                },
                "Renamed Date": {
                    "id": "date-id",
                    "date": {
                        "start": "2026-09-22T10:00:00+08:00",
                        "end": "2026-09-22T11:00:00+08:00",
                    },
                },
                "Renamed Notes": {
                    "id": "extra-id",
                    "rich_text": [{"plain_text": "Description"}],
                },
                "Renamed Location": {
                    "id": "location-id",
                    "place": {"address": "Perth"},
                },
                "Renamed Icon": {
                    "id": "icon-id",
                    "formula": {"string": "✅"},
                },
            },
        }

        event = service.make_event_body(page)

        self.assertEqual(event["summary"], "✅Strict ID task")
        self.assertEqual(event["description"], "Description")
        self.assertEqual(event["location"], "Perth")


if __name__ == "__main__":
    unittest.main()
