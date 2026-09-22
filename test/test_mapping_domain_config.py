import json
import sys
import tempfile
import unittest
from copy import deepcopy
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


def task_source(
    source_id="source-1",
    owner="user-1",
    lifecycle="active",
    database_id="db-1",
):
    return {
        "id": source_id,
        "ownerUserUuid": owner,
        "lifecycle": lifecycle,
        "version": 1,
        "database": {
            "externalId": database_id,
            "url": "https://notion.so/db",
            "name": "Tasks",
        },
        "defaults": {
            "goBackDays": 3,
            "goForwardDays": 14,
            "defaultEventLengthMinutes": 60,
            "defaultStartHour": 8,
        },
        "propertyMappings": {
            "task": property_mapping("task-id", "title"),
            "date": property_mapping("date-id", "date"),
            "location": property_mapping(
                "location-id",
                "place",
            ),
            "calendarName": property_mapping(
                "calendar-id",
                "select",
            ),
            "googleCalendarEndDate": property_mapping(
                "end-id",
                "formula",
            ),
        },
        "updatedAtMs": 1,
    }


def calendar_mapping(
    source_id="source-1",
    calendar_id="calendar-1",
    owner="user-1",
    lifecycle="active",
    *,
    mapping_id=None,
    routing=None,
):
    return {
        "id": (
            mapping_id
            or f"mapping-{source_id}-{calendar_id}"
        ),
        "ownerUserUuid": owner,
        "sourceId": source_id,
        "calendarId": calendar_id,
        "routing": routing or {"mode": "all"},
        "lifecycle": lifecycle,
        "version": 1,
        "updatedAtMs": 1,
    }


def routed_mapping(
    value,
    *,
    source_id="source-1",
    calendar_id=None,
    owner="user-1",
    mapping_id=None,
):
    calendar_id = calendar_id or f"{value.lower()}-calendar"
    return calendar_mapping(
        source_id,
        calendar_id,
        owner,
        mapping_id=(
            mapping_id or f"mapping-{source_id}-{value.lower()}"
        ),
        routing={
            "mode": "notion_calendar_value",
            "value": value,
        },
    )


def contract(owner="user-1"):
    return {
        "settings": {
            "ownerUserUuid": owner,
            "timeZone": "Australia/Perth",
            "version": 1,
            "updatedAtMs": 1,
        },
        "taskSources": [task_source(owner=owner)],
        "calendarMappings": [
            calendar_mapping(owner=owner)
        ],
    }


def execution_for(payload, *, settings_version=1):
    source = payload["taskSources"][0]
    source_mappings = [
        mapping
        for mapping in payload["calendarMappings"]
        if (
            mapping["sourceId"] == source["id"]
            and mapping["lifecycle"] == "active"
        )
    ]
    return {
        "contractVersion": 3,
        "admissionStartedAtMs": 1789920000000,
        "operationId": "operation-1",
        "ownerUserUuid": source["ownerUserUuid"],
        "settingsVersion": settings_version,
        "taskSources": [
            {
                "sourceId": source["id"],
                "sourceVersion": source["version"],
                "mappings": [
                    {
                        "mappingId": mapping["id"],
                        "mappingVersion": mapping["version"],
                        "calendarId": mapping["calendarId"],
                        "routing": deepcopy(mapping["routing"]),
                    }
                    for mapping in source_mappings
                ],
            }
        ],
    }


class MappingDomainConfigLocalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = (
            Path(self.tmp.name) / "mapping-domain.json"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def load(self, payload):
        self.path.write_text(
            json.dumps(payload),
            encoding="utf-8",
        )
        return MappingDomainConfig(
            {
                "mode": "local",
                "mapping_domain_config_path": self.path,
            },
            MagicMock(),
        ).get()

    def test_loads_source_with_complete_mapping_set(self):
        payload = contract(owner="local-user")
        settings = self.load(payload)

        self.assertEqual(len(settings), 1)
        setting = settings[0]
        self.assertEqual(setting["source_id"], "source-1")
        self.assertEqual(setting["database_id"], "db-1")
        self.assertEqual(
            setting["page_property"]["Task_Notion_Name"],
            "task-id",
        )
        self.assertEqual(
            setting["calendar_mappings"],
            [
                {
                    "mapping_id": (
                        "mapping-source-1-calendar-1"
                    ),
                    "mapping_version": 1,
                    "calendar_id": "calendar-1",
                    "routing": {"mode": "all"},
                }
            ],
        )
        self.assertNotIn("mapping_id", setting)
        self.assertNotIn("calendar_id", setting)
        self.assertNotIn("timecode", setting)

    def test_filters_disabled_sources_and_mappings(self):
        payload = contract(owner="local-user")
        payload["taskSources"].append(
            task_source(
                "source-2",
                "local-user",
                "disabled",
                "db-2",
            )
        )
        payload["calendarMappings"].append(
            calendar_mapping(
                "source-2",
                "calendar-2",
                "local-user",
            )
        )
        payload["calendarMappings"].append(
            calendar_mapping(
                "source-1",
                "calendar-disabled",
                "local-user",
                "disabled",
            )
        )

        settings = self.load(payload)

        self.assertEqual(
            [setting["source_id"] for setting in settings],
            ["source-1"],
        )
        self.assertEqual(
            len(settings[0]["calendar_mappings"]),
            1,
        )

    def test_rejects_missing_sync_required_property(self):
        payload = contract(owner="local-user")
        del payload["taskSources"][0][
            "propertyMappings"
        ]["googleCalendarEndDate"]
        with self.assertRaisesRegex(
            SettingError,
            "not sync-ready",
        ):
            self.load(payload)

    def test_rejects_wrong_property_type(self):
        payload = contract(owner="local-user")
        payload["taskSources"][0]["propertyMappings"][
            "task"
        ]["propertyType"] = "rich_text"
        with self.assertRaisesRegex(
            SettingError,
            "must be title",
        ):
            self.load(payload)

    def test_rejects_cross_owner_and_unknown_source_mapping(self):
        payload = contract(owner="local-user")
        payload["calendarMappings"][0][
            "ownerUserUuid"
        ] = "other-user"
        with self.assertRaisesRegex(
            SettingError,
            "requested owner",
        ):
            self.load(payload)

        payload = contract(owner="local-user")
        payload["calendarMappings"].append(
            calendar_mapping(
                "missing-source",
                "calendar-2",
                "local-user",
            )
        )
        with self.assertRaisesRegex(
            SettingError,
            "references unknown Task source",
        ):
            self.load(payload)

    def test_rejects_duplicate_mapping_id(self):
        payload = contract(owner="local-user")
        duplicate = routed_mapping(
            "Job",
            owner="local-user",
            mapping_id=payload["calendarMappings"][0]["id"],
        )
        payload["calendarMappings"].append(duplicate)
        with self.assertRaisesRegex(
            SettingError,
            "Duplicate Calendar mapping id",
        ):
            self.load(payload)

    def test_all_routing_requires_exactly_one_active_mapping(self):
        payload = contract(owner="local-user")
        payload["calendarMappings"].append(
            calendar_mapping(
                "source-1",
                "calendar-2",
                "local-user",
            )
        )
        with self.assertRaisesRegex(
            SettingError,
            "all routing requires exactly one",
        ):
            self.load(payload)

    def test_accepts_multiple_unique_notion_calendar_routes(self):
        payload = contract(owner="local-user")
        payload["calendarMappings"] = [
            routed_mapping(
                "Learning",
                owner="local-user",
            ),
            routed_mapping(
                "Job",
                owner="local-user",
            ),
        ]

        settings = self.load(payload)

        routes = [
            mapping["routing"]["value"]
            for mapping in settings[0]["calendar_mappings"]
        ]
        self.assertEqual(routes, ["Job", "Learning"])

    def test_rejects_mixed_or_duplicate_routing(self):
        payload = contract(owner="local-user")
        payload["calendarMappings"].append(
            routed_mapping(
                "Job",
                owner="local-user",
            )
        )
        with self.assertRaisesRegex(
            SettingError,
            "cannot mix",
        ):
            self.load(payload)

        payload = contract(owner="local-user")
        payload["calendarMappings"] = [
            routed_mapping(
                "Job",
                owner="local-user",
                mapping_id="mapping-job-1",
            ),
            routed_mapping(
                "Job",
                owner="local-user",
                calendar_id="other-calendar",
                mapping_id="mapping-job-2",
            ),
        ]
        with self.assertRaisesRegex(
            SettingError,
            "duplicate Notion Calendar routing value",
        ):
            self.load(payload)

    def test_routed_mode_requires_calendar_name_binding(self):
        payload = contract(owner="local-user")
        payload["calendarMappings"] = [
            routed_mapping(
                "Job",
                owner="local-user",
            )
        ]
        del payload["taskSources"][0][
            "propertyMappings"
        ]["calendarName"]
        with self.assertRaisesRegex(
            SettingError,
            "requires calendarName",
        ):
            self.load(payload)

    def test_accepts_shared_calendar_for_distinct_sources(self):
        payload = contract(owner="local-user")
        payload["taskSources"].append(
            task_source(
                "source-2",
                "local-user",
                database_id="db-2",
            )
        )
        payload["calendarMappings"].append(
            calendar_mapping(
                "source-2",
                "calendar-1",
                "local-user",
            )
        )

        settings = self.load(payload)

        self.assertEqual(
            [setting["source_id"] for setting in settings],
            ["source-1", "source-2"],
        )
        self.assertEqual(
            [
                setting["calendar_mappings"][0]["calendar_id"]
                for setting in settings
            ],
            ["calendar-1", "calendar-1"],
        )

    def test_rejects_active_source_without_mapping(self):
        payload = contract(owner="local-user")
        payload["calendarMappings"][0][
            "lifecycle"
        ] = "disabled"
        with self.assertRaisesRegex(
            SettingError,
            "at least one active Calendar mapping",
        ):
            self.load(payload)


class MappingDomainConfigCloudTests(unittest.TestCase):
    def _load_cloud(self, payload, execution=None):
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
            return MappingDomainConfig(
                {"mode": "cloud", "uuid": "user-1"},
                MagicMock(),
                execution_fence=execution,
            )

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
            result = MappingDomainConfig(
                {"mode": "cloud", "uuid": "user-1"},
                MagicMock(),
            ).get()

        self.assertEqual(
            result[0]["source_id"],
            "source-1",
        )
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

        config = self._load_cloud(payload)

        result = config.get()
        self.assertEqual(result[0]["goback_days"], 3)
        self.assertIsInstance(
            result[0]["default_event_length"],
            int,
        )

    def test_rejects_v2_execution_contract(self):
        payload = contract()
        execution = execution_for(payload)
        execution["contractVersion"] = 2

        with self.assertRaisesRegex(
            SettingError,
            "Unsupported sync execution contract version",
        ):
            self._load_cloud(
                payload,
                execution,
            )

    def test_rejects_execution_fence_when_settings_changed(self):
        payload = contract()
        execution = execution_for(
            payload,
            settings_version=2,
        )

        with self.assertRaisesRegex(
            SettingError,
            "settings changed",
        ):
            self._load_cloud(
                payload,
                execution,
            )

    def test_accepts_matching_v3_execution_mapping_set(self):
        payload = contract()
        payload["calendarMappings"] = [
            routed_mapping("Learning"),
            routed_mapping("Job"),
        ]
        execution = execution_for(payload)

        config = self._load_cloud(
            payload,
            execution,
        )
        result = config.get()

        self.assertEqual(
            result[0]["operation_id"],
            "operation-1",
        )
        self.assertEqual(
            result[0]["execution_contract_version"],
            3,
        )
        self.assertEqual(
            len(result[0]["calendar_mappings"]),
            2,
        )

    def test_rejects_changed_execution_mapping_route(self):
        payload = contract()
        payload["calendarMappings"] = [
            routed_mapping("Job")
        ]
        execution = execution_for(payload)
        execution["taskSources"][0]["mappings"][0][
            "routing"
        ]["value"] = "Life"

        with self.assertRaisesRegex(
            SettingError,
            "changed after the sync job was admitted",
        ):
            self._load_cloud(
                payload,
                execution,
            )

    def test_revalidate_source_compares_complete_mapping_set(self):
        payload = contract()
        payload["calendarMappings"] = [
            routed_mapping("Learning"),
            routed_mapping("Job"),
        ]
        config = self._load_cloud(payload)
        setting = config.get()[0]

        with (
            patch(
                "utils.dynamodb_utils.get_mapping_domain_settings",
                return_value=payload["settings"],
            ),
            patch(
                "utils.dynamodb_utils.get_mapping_domain_task_source",
                return_value=payload["taskSources"][0],
            ),
            patch(
                "utils.dynamodb_utils.list_mapping_domain_calendar_mappings_for_owner",
                return_value=payload["calendarMappings"],
            ),
        ):
            config.revalidate_source(setting)

        changed = json.loads(
            json.dumps(payload["calendarMappings"])
        )
        changed[0]["routing"]["value"] = "Changed"
        with (
            patch(
                "utils.dynamodb_utils.get_mapping_domain_settings",
                return_value=payload["settings"],
            ),
            patch(
                "utils.dynamodb_utils.get_mapping_domain_task_source",
                return_value=payload["taskSources"][0],
            ),
            patch(
                "utils.dynamodb_utils.list_mapping_domain_calendar_mappings_for_owner",
                return_value=changed,
            ),
        ):
            with self.assertRaisesRegex(
                SettingError,
                "changed while the sync job was running",
            ):
                config.revalidate_source(setting)


class MappingDomainDateRangeTests(unittest.TestCase):
    def test_derives_dst_offsets_from_iana_timezone(self):
        setting = {"timezone": "Australia/Sydney"}
        now = datetime(
            2026,
            4,
            5,
            12,
            tzinfo=ZoneInfo("Australia/Sydney"),
        )

        apply_date_range(
            setting,
            1,
            1,
            now=now,
        )

        self.assertTrue(
            setting["google_timemin"].endswith("+11:00")
        )
        self.assertTrue(
            setting["google_timemax"].endswith("+10:00")
        )

    def test_rejects_invalid_iana_timezone(self):
        with self.assertRaisesRegex(
            SettingError,
            "valid IANA",
        ):
            apply_date_range(
                {"timezone": "Mars/Olympus"},
                1,
                1,
            )


if __name__ == "__main__":
    unittest.main()
