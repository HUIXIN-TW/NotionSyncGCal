import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))

from notion.notion_service import NotionService  # noqa: E402


class NotionTimezoneBoundaryTests(unittest.TestCase):
    def _build_service(self, *, timecode="-05:00"):
        setting = {
            "before_date": "2026-03-09",
            "after_date": "2026-03-07",
            "timezone": "America/New_York",
            "timecode": timecode,
            "database_id": "database-id",
            "page_property": {
                "Date_Notion_Name": "date-id",
                "GCal_End_Date_Notion_Name": "end-id",
            },
        }
        client = MagicMock()
        client.request.return_value = {
            "results": [],
            "has_more": False,
            "next_cursor": None,
        }
        logger = MagicMock()

        with patch("notion.notion_service.Client", return_value=client):
            service = NotionService("token", setting, logger)
        return service, client

    def test_query_boundaries_use_date_specific_dst_offsets(self):
        service, client = self._build_service()

        service.get_notion_task()

        body = client.request.call_args.kwargs["body"]
        filters = body["filter"]["and"]
        self.assertEqual(
            filters[0]["date"]["before"],
            "2026-03-09T00:00:00.000-04:00",
        )
        self.assertEqual(
            filters[1]["formula"]["date"]["on_or_after"],
            "2026-03-07T00:00:00.000-05:00",
        )

    def test_query_boundaries_ignore_stale_persisted_timecode(self):
        service, client = self._build_service(timecode="+09:00")

        service.get_notion_task()

        body = client.request.call_args.kwargs["body"]
        rendered = str(body["filter"])
        self.assertNotIn("+09:00", rendered)
        self.assertIn("-04:00", rendered)
        self.assertIn("-05:00", rendered)

    def test_runtime_timestamp_formatting_uses_configured_timezone(self):
        service, _ = self._build_service(timecode="+09:00")
        instant = datetime(2026, 7, 1, 16, 0, tzinfo=timezone.utc)

        self.assertEqual(
            service.parse_date_in_notion_format(instant),
            "2026-07-01T12:00:00-04:00",
        )

    def test_naive_runtime_timestamp_is_interpreted_as_local_wall_time(self):
        service, _ = self._build_service(timecode="+09:00")

        self.assertEqual(
            service.parse_date_in_notion_format(datetime(2026, 7, 1, 12, 0)),
            "2026-07-01T12:00:00-04:00",
        )


if __name__ == "__main__":
    unittest.main()
