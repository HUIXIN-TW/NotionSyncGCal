import json
import sys
import tempfile
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))

from config.mapping_domain_config import (  # noqa: E402
    MappingDomainConfig,
    SettingError,
    apply_date_range,
)


def property_mapping(property_id, property_type):
    return {
        "propertyId": property_id,
        "propertyName": f"Name {property_id}",
        "propertyType": property_type,
    }


def task_source(source_id="source-1", owner="user-1", lifecycle="active", database_id="db-1"):
    return {
        "id": source_id,
        "ownerUserUuid": owner,
        "lifecycle": lifecycle,
        "version": 1,
        "database": {"externalId": database_id, "url": "https://notion.so/db", "name": "Tasks"},
        "defaults": {
            "goBackDays": 3,
            "goForwardDays": 14,
            "defaultEventLengthMinutes": 60,
            "defaultStartHour": 8,
        },
        "propertyMappings": {
            "task": property_mapping("task-id", "title"),
            "date": property_mapping("date-id", "date"),
            "location": property_mapping("location-id", "place"),
            "calendarName": property_mapping("calendar-id", "select"),
            "googleCalendarEventId": property_mapping("event-id", "rich_text"),
            "googleCalendarSyncTime": property_mapping("sync-id", "rich_text"),
            "googleCalendarEndDate": property_mapping("end-id", "formula"),
        },
        "updatedAtMs": 1,
    }


def calendar_mapping(source_id="source-1", calendar_id="calendar-1", owner="user-1", lifecycle="active"):
    return {
        "id": f"mapping-{source_id}-{calendar_id}",
        "ownerUserUuid": owner,
        "sourceId": source_id,
        "calendarId": calendar_id,
        "lifecycle": lifecycle,
        "version": 1,
        "updatedAtMs": 1,
    }


def contract(owner="user-1"):
    return {
        "settings": {
            "ownerUserUuid": owner,
            "timeZone": "Australia/Perth",
            "version": 1,
            "updatedAtMs": 1,
        },
        "taskSources": [task_source(owner=owner)],
        "calendarMappings": [calendar_mapping(owner=owner)],
    }


class MappingDomainConfigLocalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "mapping-domain.json"

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, payload):
        self.path.write_text(json.dumps(payload), encoding="utf-8")

    def load(self, payload):
        self.write(payload)
        return MappingDomainConfig({"mode": "local", "mapping_domain_config_path": self.path}, MagicMock()).get()

    def test_loads_active_source_using_provider_property_ids(self):
        payload = contract(owner="local-user")
        settings = self.load(payload)

        self.assertEqual(len(settings), 1)
        self.assertEqual(settings[0]["source_id"], "source-1")
        self.assertEqual(settings[0]["database_id"], "db-1")
        self.assertEqual(settings[0]["page_property"]["Task_Notion_Name"], "task-id")
        self.assertEqual(settings[0]["calendar_ids"], ["calendar-1"])
        self.assertEqual(settings[0]["calendar_id"], "calendar-1")
        self.assertEqual(settings[0]["mapping_id"], "mapping-source-1-calendar-1")
        self.assertEqual(settings[0]["settings_version"], 1)
        self.assertEqual(settings[0]["source_version"], 1)
        self.assertEqual(settings[0]["mapping_version"], 1)
        self.assertNotIn("timecode", settings[0])

    def test_rejects_missing_required_settings_shape(self):
        payload = contract(owner="local-user")
        del payload["settings"]["timeZone"]
        with self.assertRaisesRegex(SettingError, "settings.timeZone"):
            self.load(payload)

    def test_filters_disabled_sources_and_mappings(self):
        payload = contract(owner="local-user")
        payload["taskSources"].append(task_source("source-2", "local-user", "disabled", "db-2"))
        payload["calendarMappings"].append(calendar_mapping("source-2", "calendar-2", "local-user"))
        payload["calendarMappings"].append(calendar_mapping("source-1", "calendar-disabled", "local-user", "disabled"))

        settings = self.load(payload)

        self.assertEqual([setting["source_id"] for setting in settings], ["source-1"])
        self.assertEqual(settings[0]["calendar_ids"], ["calendar-1"])

    def test_rejects_missing_sync_required_mapping(self):
        payload = contract(owner="local-user")
        del payload["taskSources"][0]["propertyMappings"]["googleCalendarEndDate"]
        with self.assertRaisesRegex(SettingError, "not sync-ready"):
            self.load(payload)

    def test_rejects_wrong_property_type(self):
        payload = contract(owner="local-user")
        payload["taskSources"][0]["propertyMappings"]["task"]["propertyType"] = "rich_text"
        with self.assertRaisesRegex(SettingError, "must be title"):
            self.load(payload)

    def test_rejects_cross_owner_record(self):
        payload = contract(owner="local-user")
        payload["calendarMappings"][0]["ownerUserUuid"] = "other-user"
        with self.assertRaisesRegex(SettingError, "requested owner"):
            self.load(payload)

    def test_rejects_cross_owner_disabled_record(self):
        payload = contract(owner="local-user")
        payload["calendarMappings"].append(calendar_mapping("source-1", "disabled", "other-user", "disabled"))
        with self.assertRaisesRegex(SettingError, "requested owner"):
            self.load(payload)

    def test_rejects_invalid_source_lifecycle(self):
        payload = contract(owner="local-user")
        payload["taskSources"][0]["lifecycle"] = "deleted"
        with self.assertRaisesRegex(SettingError, "lifecycle must be active or disabled"):
            self.load(payload)

    def test_rejects_invalid_mapping_lifecycle(self):
        payload = contract(owner="local-user")
        payload["calendarMappings"][0]["lifecycle"] = "deleted"
        with self.assertRaisesRegex(SettingError, "lifecycle must be active or disabled"):
            self.load(payload)

    def test_rejects_mapping_for_unknown_source(self):
        payload = contract(owner="local-user")
        payload["calendarMappings"].append(calendar_mapping("missing-source", "calendar-2", "local-user"))
        with self.assertRaisesRegex(SettingError, "references unknown Task source"):
            self.load(payload)

    def test_rejects_duplicate_mapping_id(self):
        payload = contract(owner="local-user")
        duplicate = calendar_mapping("source-1", "calendar-2", "local-user")
        duplicate["id"] = payload["calendarMappings"][0]["id"]
        payload["calendarMappings"].append(duplicate)
        with self.assertRaisesRegex(SettingError, "Duplicate Calendar mapping id"):
            self.load(payload)

    def test_rejects_duplicate_active_calendar_mapping_for_one_source(self):
        payload = contract(owner="local-user")
        duplicate = calendar_mapping("source-1", "calendar-1", "local-user")
        duplicate["id"] = "mapping-duplicate"
        payload["calendarMappings"].append(duplicate)
        with self.assertRaisesRegex(SettingError, "exactly one active Calendar mapping"):
            self.load(payload)

    def test_accepts_calendar_shared_by_distinct_active_sources(self):
        payload = contract(owner="local-user")
        payload["taskSources"].append(task_source("source-2", "local-user", database_id="db-2"))
        payload["calendarMappings"].append(calendar_mapping("source-2", "calendar-1", "local-user"))

        settings = self.load(payload)

        self.assertEqual([setting["source_id"] for setting in settings], ["source-1", "source-2"])
        self.assertEqual([setting["calendar_id"] for setting in settings], ["calendar-1", "calendar-1"])
        self.assertNotEqual(settings[0]["mapping_id"], settings[1]["mapping_id"])

    def test_rejects_active_source_without_active_calendar_mapping(self):
        payload = contract(owner="local-user")
        payload["calendarMappings"][0]["lifecycle"] = "disabled"
        with self.assertRaisesRegex(SettingError, "exactly one active Calendar mapping"):
            self.load(payload)

    def test_rejects_one_unmapped_active_source_even_when_another_source_is_ready(self):
        payload = contract(owner="local-user")
        payload["taskSources"].append(task_source("source-2", "local-user", database_id="db-2"))

        with self.assertRaisesRegex(SettingError, "Task source source-2 requires exactly one active Calendar mapping"):
            self.load(payload)


class MappingDomainConfigCloudTests(unittest.TestCase):
    def test_reads_only_mapping_domain_records(self):
        payload = contract()
        with (
            patch(
                "utils.dynamodb_utils.get_mapping_domain_settings",
                return_value=payload["settings"],
            ) as get_settings,
            patch(
                "utils.dynamodb_utils.list_mapping_domain_task_sources",
                return_value=payload["taskSources"],
            ) as list_sources,
            patch(
                "utils.dynamodb_utils.list_mapping_domain_calendar_mappings_for_owner",
                return_value=payload["calendarMappings"],
            ) as list_mappings,
        ):
            result = MappingDomainConfig({"mode": "cloud", "uuid": "user-1"}, MagicMock()).get()

        self.assertEqual(result[0]["source_id"], "source-1")
        get_settings.assert_called_once_with("user-1")
        list_sources.assert_called_once_with("user-1")
        list_mappings.assert_called_once_with("user-1")

    def test_accepts_integral_dynamodb_decimal_defaults(self):
        payload = contract()
        defaults = payload["taskSources"][0]["defaults"]
        defaults["goBackDays"] = Decimal("3")
        defaults["goForwardDays"] = Decimal("14")
        defaults["defaultEventLengthMinutes"] = Decimal("60")
        defaults["defaultStartHour"] = Decimal("8")

        with (
            patch(
                "utils.dynamodb_utils.get_mapping_domain_settings",
                return_value=payload["settings"],
            ),
            patch(
                "utils.dynamodb_utils.list_mapping_domain_task_sources",
                return_value=payload["taskSources"],
            ),
            patch(
                "utils.dynamodb_utils.list_mapping_domain_calendar_mappings_for_owner",
                return_value=payload["calendarMappings"],
            ),
        ):
            result = MappingDomainConfig({"mode": "cloud", "uuid": "user-1"}, MagicMock()).get()

        self.assertEqual(result[0]["goback_days"], 3)
        self.assertIsInstance(result[0]["goback_days"], int)
        self.assertEqual(result[0]["default_event_length"], 60)
        self.assertIsInstance(result[0]["default_event_length"], int)

    def test_rejects_non_integral_dynamodb_decimal_defaults(self):
        payload = contract()
        payload["taskSources"][0]["defaults"]["goBackDays"] = Decimal("1.5")

        with (
            patch(
                "utils.dynamodb_utils.get_mapping_domain_settings",
                return_value=payload["settings"],
            ),
            patch(
                "utils.dynamodb_utils.list_mapping_domain_task_sources",
                return_value=payload["taskSources"],
            ),
            patch(
                "utils.dynamodb_utils.list_mapping_domain_calendar_mappings_for_owner",
                return_value=payload["calendarMappings"],
            ),
        ):
            with self.assertRaisesRegex(SettingError, "goBackDays must be an integer"):
                MappingDomainConfig({"mode": "cloud", "uuid": "user-1"}, MagicMock()).get()

    def test_rejects_execution_fence_when_settings_version_changed(self):
        payload = contract()
        execution = {
            "contractVersion": 2,
            "admissionStartedAtMs": 1789920000000,
            "operationId": "operation-1",
            "ownerUserUuid": "user-1",
            "settingsVersion": 2,
            "taskSources": [
                {
                    "sourceId": "source-1",
                    "sourceVersion": 1,
                    "mappingId": "mapping-source-1-calendar-1",
                    "mappingVersion": 1,
                    "calendarId": "calendar-1",
                }
            ],
        }

        with (
            patch(
                "utils.dynamodb_utils.get_mapping_domain_settings",
                return_value=payload["settings"],
            ),
            patch(
                "utils.dynamodb_utils.list_mapping_domain_task_sources",
                return_value=payload["taskSources"],
            ),
            patch(
                "utils.dynamodb_utils.list_mapping_domain_calendar_mappings_for_owner",
                return_value=payload["calendarMappings"],
            ),
        ):
            with self.assertRaisesRegex(SettingError, "settings changed"):
                MappingDomainConfig(
                    {"mode": "cloud", "uuid": "user-1"},
                    MagicMock(),
                    execution_fence=execution,
                ).get()

    def test_accepts_matching_execution_fence_and_keeps_operation_identity(self):
        payload = contract()
        execution = {
            "contractVersion": 2,
            "admissionStartedAtMs": 1789920000000,
            "operationId": "operation-1",
            "ownerUserUuid": "user-1",
            "settingsVersion": 1,
            "taskSources": [
                {
                    "sourceId": "source-1",
                    "sourceVersion": 1,
                    "mappingId": "mapping-source-1-calendar-1",
                    "mappingVersion": 1,
                    "calendarId": "calendar-1",
                }
            ],
        }

        with (
            patch(
                "utils.dynamodb_utils.get_mapping_domain_settings",
                return_value=payload["settings"],
            ),
            patch(
                "utils.dynamodb_utils.list_mapping_domain_task_sources",
                return_value=payload["taskSources"],
            ),
            patch(
                "utils.dynamodb_utils.list_mapping_domain_calendar_mappings_for_owner",
                return_value=payload["calendarMappings"],
            ),
        ):
            result = MappingDomainConfig(
                {"mode": "cloud", "uuid": "user-1"},
                MagicMock(),
                execution_fence=execution,
            ).get()

        self.assertEqual(result[0]["operation_id"], "operation-1")
        self.assertEqual(result[0]["execution_contract_version"], 2)
        self.assertEqual(result[0]["admission_started_at_ms"], 1789920000000)


class MappingDomainDateRangeTests(unittest.TestCase):
    def test_derives_dst_offsets_from_iana_timezone_for_each_boundary(self):
        setting = {"timezone": "Australia/Sydney"}
        now = datetime(2026, 4, 5, 12, tzinfo=ZoneInfo("Australia/Sydney"))

        apply_date_range(setting, 1, 1, now=now)

        self.assertTrue(setting["google_timemin"].endswith("+11:00"))
        self.assertTrue(setting["google_timemax"].endswith("+10:00"))

    def test_rejects_invalid_iana_timezone(self):
        with self.assertRaisesRegex(SettingError, "valid IANA"):
            apply_date_range({"timezone": "Mars/Olympus"}, 1, 1)


if __name__ == "__main__":
    unittest.main()
