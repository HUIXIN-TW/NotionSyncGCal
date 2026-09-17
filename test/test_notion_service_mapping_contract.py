import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))

from notion.notion_service import NotionService  # noqa: E402


SETTING = {
    "database_id": "database-id",
    "timezone": "Asia/Taipei",
    "notion_api_version": "2022-06-28",
    "google_timemin": "2026-01-01T00:00:00.000+08:00",
    "google_timemax": "2026-02-01T00:00:00.000+08:00",
    "after_date": "2026-01-01",
    "before_date": "2026-02-01",
    "page_property": {
        "Task_Notion_Name": "task-id",
        "Date_Notion_Name": "date-id",
        "GCal_End_Date_Notion_Name": "end-id",
        "GCal_EventId_Notion_Name": "event-id",
        "GCal_Sync_Time_Notion_Name": "sync-id",
        "GCal_Name_Notion_Name": "calendar-id",
    },
}


class NotionServiceMappingContractTests(unittest.TestCase):
    def make_service(self):
        client = MagicMock()
        with patch("notion.notion_service.Client", return_value=client):
            service = NotionService("token", copy.deepcopy(SETTING), MagicMock())
        return service, client

    def test_query_filters_use_stable_provider_property_ids(self):
        service, client = self.make_service()
        client.request.return_value = {"results": [], "has_more": False}

        service.get_notion_task()

        filters = client.request.call_args.kwargs["body"]["filter"]["and"]
        self.assertEqual(filters[0]["property"], "date-id")
        self.assertEqual(filters[1]["property"], "end-id")

    def test_updates_use_stable_provider_property_ids(self):
        service, client = self.make_service()

        service.update_notion_task_for_new_gcal_event_id("page-id", "event-123")

        properties = client.pages.update.call_args.kwargs["properties"]
        self.assertEqual(list(properties), ["event-id"])
        self.assertEqual(properties["event-id"]["rich_text"][0]["text"]["content"], "event-123")


if __name__ == "__main__":
    unittest.main()
