import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))

from config.mapping_domain_config import MappingDomainConfig, SettingError  # noqa: E402


def property_mapping(property_id, property_name, property_type):
    return {
        "propertyId": property_id,
        "propertyName": property_name,
        "propertyType": property_type,
    }


def build_payload():
    return {
        "settings": {
            "ownerUserUuid": "local-user",
            "timeZone": "Asia/Taipei",
            "timeCode": "+08:00",
            "version": 1,
            "updatedAtMs": 1,
        },
        "taskSources": [
            {
                "id": "source-1",
                "ownerUserUuid": "local-user",
                "lifecycle": "active",
                "version": 1,
                "database": {
                    "externalId": "notion-db-1",
                    "url": "https://notion.so/notion-db-1",
                    "name": "Tasks",
                },
                "defaults": {
                    "goBackDays": 1,
                    "goForwardDays": 2,
                    "defaultEventLengthMinutes": 60,
                    "defaultStartHour": 8,
                    "defaultCalendarName": "Learning",
                },
                "propertyMappings": {
                    "task": property_mapping("task-id", "Task Name", "title"),
                    "date": property_mapping("date-id", "Date", "date"),
                    "calendarName": property_mapping(
                        "calendar-id", "Calendar", "select"
                    ),
                    "location": property_mapping(
                        "location-id", "Location", "place"
                    ),
                    "extraInfo": property_mapping(
                        "extra-id", "Extra Info", "rich_text"
                    ),
                    "googleCalendarEndDate": property_mapping(
                        "end-id", "GCal End Date", "formula"
                    ),
                    "googleCalendarDeleted": property_mapping(
                        "deleted-id", "GCal Deleted?", "checkbox"
                    ),
                    "googleCalendarEventId": property_mapping(
                        "event-id", "GCal Event Id", "rich_text"
                    ),
                    "googleCalendarSyncTime": property_mapping(
                        "sync-id", "GCal Sync Time", "rich_text"
                    ),
                    "googleCalendarIcon": property_mapping(
                        "icon-id", "GCal Icon", "formula"
                    ),
                },
                "updatedAtMs": 1,
            }
        ],
        "calendarMappings": [
            {
                "id": "mapping-learning",
                "ownerUserUuid": "local-user",
                "sourceId": "source-1",
                "calendarName": "Learning",
                "calendarId": "learning@example.com",
                "lifecycle": "active",
                "version": 1,
                "updatedAtMs": 1,
            },
            {
                "id": "mapping-job",
                "ownerUserUuid": "local-user",
                "sourceId": "source-1",
                "calendarName": "Job",
                "calendarId": "job@example.com",
                "lifecycle": "active",
                "version": 1,
                "updatedAtMs": 1,
            },
        ],
    }


class MappingDomainConfigTests(unittest.TestCase):
    def load(self, payload):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mapping.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            return MappingDomainConfig(
                {
                    "mode": "local",
                    "mapping_domain_config_path": str(path),
                },
                logger=mock.MagicMock(),
            ).get()

    def test_expands_normalized_rows_to_worker_setting(self):
        [setting] = self.load(build_payload())

        self.assertEqual(setting["database_id"], "notion-db-1")
        self.assertEqual(setting["timezone"], "Asia/Taipei")
        self.assertEqual(setting["timecode"], "+08:00")
        self.assertEqual(setting["goback_days"], 1)
        self.assertEqual(setting["goforward_days"], 2)
        self.assertEqual(setting["default_event_length"], 60)
        self.assertEqual(setting["default_start_time"], 8)

        self.assertEqual(setting["page_property"]["Task_Notion_Name"], "task-id")
        self.assertEqual(
            setting["page_property"]["GCal_EventId_Notion_Name"],
            "event-id",
        )
        self.assertEqual(
            setting["page_property"]["GCal_Sync_Time_Notion_Name"],
            "sync-id",
        )

        self.assertEqual(
            list(setting["gcal_name_dict"].items()),
            [
                ("Learning", "learning@example.com"),
                ("Job", "job@example.com"),
            ],
        )
        self.assertEqual(
            setting["gcal_id_dict"]["learning@example.com"],
            "Learning",
        )
        self.assertEqual(setting["gcal_default_name"], "Learning")
        self.assertEqual(setting["gcal_default_id"], "learning@example.com")
        self.assertTrue(setting["google_timemin"].endswith("+08:00"))
        self.assertTrue(setting["google_timemax"].endswith("+08:00"))

    def test_uses_stable_provider_ids_for_worker_runtime(self):
        [setting] = self.load(build_payload())
        self.assertEqual(setting["page_property"]["Date_Notion_Name"], "date-id")
        self.assertNotEqual(
            setting["page_property"]["Date_Notion_Name"],
            "Date",
        )

    def test_rejects_missing_event_id_binding(self):
        payload = build_payload()
        del payload["taskSources"][0]["propertyMappings"]["googleCalendarEventId"]
        with self.assertRaisesRegex(SettingError, "googleCalendarEventId"):
            self.load(payload)

    def test_rejects_duplicate_calendar_names(self):
        payload = build_payload()
        payload["calendarMappings"][1]["calendarName"] = "Learning"
        with self.assertRaisesRegex(SettingError, "Duplicate Calendar name"):
            self.load(payload)

    def test_rejects_default_calendar_without_active_mapping(self):
        payload = build_payload()
        payload["taskSources"][0]["defaults"]["defaultCalendarName"] = "Other"
        with self.assertRaisesRegex(SettingError, "defaultCalendarName"):
            self.load(payload)

    def test_filters_disabled_sources_and_mappings(self):
        payload = build_payload()
        payload["calendarMappings"][1]["lifecycle"] = "disabled"
        second = copy.deepcopy(payload["taskSources"][0])
        second["id"] = "source-disabled"
        second["lifecycle"] = "disabled"
        second["database"]["externalId"] = "notion-db-disabled"
        payload["taskSources"].append(second)

        [setting] = self.load(payload)
        self.assertEqual(
            setting["gcal_name_dict"],
            {"Learning": "learning@example.com"},
        )

    def test_supports_multiple_task_sources(self):
        payload = build_payload()
        second = copy.deepcopy(payload["taskSources"][0])
        second["id"] = "source-2"
        second["database"]["externalId"] = "notion-db-2"
        second["defaults"]["defaultCalendarName"] = "Life"
        payload["taskSources"].append(second)
        payload["calendarMappings"].append(
            {
                "id": "mapping-life",
                "ownerUserUuid": "local-user",
                "sourceId": "source-2",
                "calendarName": "Life",
                "calendarId": "life@example.com",
                "lifecycle": "active",
                "version": 1,
                "updatedAtMs": 1,
            }
        )

        settings = self.load(payload)
        self.assertEqual(
            {setting["source_id"] for setting in settings},
            {"source-1", "source-2"},
        )

    def test_rejects_cross_owner_mapping(self):
        payload = build_payload()
        payload["calendarMappings"][0]["ownerUserUuid"] = "other-user"
        with self.assertRaisesRegex(SettingError, "requested owner"):
            self.load(payload)


if __name__ == "__main__":
    unittest.main()
