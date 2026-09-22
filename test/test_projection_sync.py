import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))

from sync.contracts import StaleExecutionError  # noqa: E402
from sync.projection_identity import (  # noqa: E402
    ProjectionIdentityError,
    build_projection_identity,
)
from sync.sync import project_notion_to_google_calendar  # noqa: E402


MAPPING_LEARNING = {
    "mapping_id": "mapping-learning",
    "mapping_version": 1,
    "calendar_id": "learning@example.com",
    "routing": {
        "mode": "notion_calendar_value",
        "value": "Learning",
    },
}
MAPPING_JOB = {
    "mapping_id": "mapping-job",
    "mapping_version": 1,
    "calendar_id": "job@example.com",
    "routing": {
        "mode": "notion_calendar_value",
        "value": "Job",
    },
}
SETTING = {
    "owner_user_uuid": "11111111-1111-4111-8111-111111111111",
    "settings_version": 1,
    "source_id": "source-1",
    "source_version": 1,
    "calendar_mappings": [
        MAPPING_LEARNING,
        MAPPING_JOB,
    ],
    "database_id": "database-1",
    "page_property": {
        "Task_Notion_Name": "Task",
        "Date_Notion_Name": "Date",
        "GCal_Name_Notion_Name": "Calendar",
        "Delete_Notion_Name": "Delete",
    },
}
TASK_ONE = "22222222-2222-4222-8222-222222222222"
TASK_TWO = "33333333-3333-4333-8333-333333333333"


def _task(task_id, *, route="Job", deleted=False):
    return {
        "id": task_id,
        "properties": {
            "Task": {
                "id": "Task",
                "title": [{"plain_text": "Task"}],
            },
            "Date": {
                "id": "Date",
                "date": {"start": "2026-09-20"},
            },
            "Calendar": {
                "id": "Calendar",
                "select": (
                    {"name": route}
                    if route is not None
                    else None
                ),
            },
            "Delete": {
                "id": "Delete",
                "checkbox": deleted,
            },
        },
    }


def _mapping_setting(mapping):
    return {
        **SETTING,
        "mapping_id": mapping["mapping_id"],
        "mapping_version": mapping["mapping_version"],
        "calendar_id": mapping["calendar_id"],
        "routing": mapping["routing"],
    }


def _owned_event(task_id, mapping):
    projection = build_projection_identity(
        _mapping_setting(mapping),
        task_id,
    )
    return {
        "id": projection["event_id"],
        "extendedProperties": {
            "private": dict(projection["private"])
        },
    }


def _google_services():
    learning = MagicMock(name="learning_google")
    job = MagicMock(name="job_google")
    learning.get_gcal_event.return_value = []
    job.get_gcal_event.return_value = []
    return {
        "mapping-learning": learning,
        "mapping-job": job,
    }


class RoutedOneWayProjectionTests(unittest.TestCase):
    def test_queries_notion_once_and_routes_task_to_selected_mapping(self):
        notion = MagicMock()
        services = _google_services()
        notion.get_notion_task.return_value = (
            {},
            [_task(TASK_ONE, route="Job")],
        )

        result = project_notion_to_google_calendar(
            copy.deepcopy(SETTING),
            notion,
            services,
        )

        self.assertEqual(result["statusCode"], 200)
        notion.get_notion_task.assert_called_once()
        services["mapping-job"].upsert_projection.assert_called_once()
        services[
            "mapping-learning"
        ].upsert_projection.assert_not_called()
        notion.update_notion_task.assert_not_called()
        notion.create_notion_task.assert_not_called()
        notion.delete_notion_task.assert_not_called()

    def test_all_routing_projects_without_calendar_select(self):
        notion = MagicMock()
        all_mapping = {
            "mapping_id": "mapping-all",
            "mapping_version": 1,
            "calendar_id": "all@example.com",
            "routing": {"mode": "all"},
        }
        setting = {
            **copy.deepcopy(SETTING),
            "calendar_mappings": [all_mapping],
        }
        setting["page_property"].pop("GCal_Name_Notion_Name", None)
        google = MagicMock(name="all_google")
        google.get_gcal_event.return_value = []
        notion.get_notion_task.return_value = (
            {},
            [_task(TASK_ONE, route=None)],
        )

        result = project_notion_to_google_calendar(
            setting,
            notion,
            {"mapping-all": google},
        )

        self.assertEqual(result["statusCode"], 200)
        notion.get_notion_task.assert_called_once()
        google.upsert_projection.assert_called_once()
        google.delete_projection.assert_not_called()

    def test_blank_or_unknown_route_fails_closed_without_mutation(self):
        for route in (None, "Unknown"):
            with self.subTest(route=route):
                notion = MagicMock()
                services = _google_services()
                notion.get_notion_task.return_value = (
                    {},
                    [_task(TASK_ONE, route=route)],
                )
                services["mapping-job"].get_gcal_event.return_value = [
                    _owned_event(TASK_ONE, MAPPING_JOB)
                ]

                result = project_notion_to_google_calendar(
                    copy.deepcopy(SETTING),
                    notion,
                    services,
                )

                for service in services.values():
                    service.upsert_projection.assert_not_called()
                    service.delete_projection.assert_not_called()
                error = result["body"]["message"]["errors"][0]
                self.assertEqual(
                    error["error_code"],
                    "calendar_route_unresolved",
                )
                self.assertFalse(error["retriable"])

    def test_route_change_upserts_new_mapping_and_retires_old_projection(self):
        notion = MagicMock()
        services = _google_services()
        notion.get_notion_task.return_value = (
            {},
            [_task(TASK_ONE, route="Learning")],
        )
        services["mapping-job"].get_gcal_event.return_value = [
            _owned_event(TASK_ONE, MAPPING_JOB)
        ]

        project_notion_to_google_calendar(
            copy.deepcopy(SETTING),
            notion,
            services,
        )

        services[
            "mapping-learning"
        ].upsert_projection.assert_called_once()
        services["mapping-job"].upsert_projection.assert_not_called()
        services["mapping-job"].delete_projection.assert_called_once_with(
            build_projection_identity(
                _mapping_setting(MAPPING_JOB),
                TASK_ONE,
            )
        )

    def test_deleted_task_deletes_owned_projection_from_every_mapping(self):
        notion = MagicMock()
        services = _google_services()
        notion.get_notion_task.return_value = (
            {},
            [_task(TASK_ONE, route=None, deleted=True)],
        )

        project_notion_to_google_calendar(
            copy.deepcopy(SETTING),
            notion,
            services,
        )

        for mapping in SETTING["calendar_mappings"]:
            service = services[mapping["mapping_id"]]
            service.delete_projection.assert_any_call(
                build_projection_identity(
                    _mapping_setting(mapping),
                    TASK_ONE,
                )
            )
            service.upsert_projection.assert_not_called()
        notion.delete_notion_task.assert_not_called()

    def test_stale_execution_stops_remaining_provider_writes(self):
        notion = MagicMock()
        services = _google_services()
        notion.get_notion_task.return_value = (
            {},
            [
                _task(TASK_ONE, route="Job"),
                _task(TASK_TWO, route="Job"),
            ],
        )
        services[
            "mapping-job"
        ].upsert_projection.side_effect = StaleExecutionError(
            "stale"
        )

        result = project_notion_to_google_calendar(
            copy.deepcopy(SETTING),
            notion,
            services,
        )

        self.assertEqual(
            services["mapping-job"].upsert_projection.call_count,
            1,
        )
        for service in services.values():
            service.get_gcal_event.assert_not_called()
        error = result["body"]["message"]["errors"][0]
        self.assertEqual(
            error["error_code"],
            "stale_execution_snapshot",
        )
        self.assertFalse(error["retriable"])

    def test_projection_identity_mismatch_is_non_retriable(self):
        notion = MagicMock()
        services = _google_services()
        notion.get_notion_task.return_value = (
            {},
            [_task(TASK_ONE, route="Job")],
        )
        services[
            "mapping-job"
        ].upsert_projection.side_effect = ProjectionIdentityError(
            "wrong owner"
        )

        result = project_notion_to_google_calendar(
            copy.deepcopy(SETTING),
            notion,
            services,
        )

        error = result["body"]["message"]["errors"][0]
        self.assertEqual(
            error["error_code"],
            "projection_identity_mismatch",
        )
        self.assertFalse(error["retriable"])

    def test_provider_failure_is_retryable_but_never_writes_notion(self):
        notion = MagicMock()
        services = _google_services()
        notion.get_notion_task.return_value = (
            {},
            [_task(TASK_ONE, route="Job")],
        )
        services[
            "mapping-job"
        ].upsert_projection.side_effect = RuntimeError(
            "provider unavailable"
        )

        result = project_notion_to_google_calendar(
            copy.deepcopy(SETTING),
            notion,
            services,
        )

        error = result["body"]["message"]["errors"][0]
        self.assertTrue(error["retriable"])
        notion.update_notion_task.assert_not_called()
        notion.create_notion_task.assert_not_called()

    def test_missing_notion_task_retires_owned_projection_per_mapping(self):
        notion = MagicMock()
        services = _google_services()
        notion.get_notion_task.return_value = ({}, [])
        services["mapping-job"].get_gcal_event.return_value = [
            _owned_event(TASK_ONE, MAPPING_JOB)
        ]

        result = project_notion_to_google_calendar(
            copy.deepcopy(SETTING),
            notion,
            services,
        )

        self.assertEqual(result["statusCode"], 200)
        services["mapping-job"].delete_projection.assert_called_once_with(
            build_projection_identity(
                _mapping_setting(MAPPING_JOB),
                TASK_ONE,
            )
        )

    def test_current_task_is_not_retired_from_selected_mapping(self):
        notion = MagicMock()
        services = _google_services()
        notion.get_notion_task.return_value = (
            {},
            [_task(TASK_ONE, route="Job")],
        )
        services["mapping-job"].get_gcal_event.return_value = [
            _owned_event(TASK_ONE, MAPPING_JOB)
        ]

        project_notion_to_google_calendar(
            copy.deepcopy(SETTING),
            notion,
            services,
        )

        services["mapping-job"].upsert_projection.assert_called_once()
        services["mapping-job"].delete_projection.assert_not_called()

    def test_incomplete_tagged_event_is_ignored_without_mutation(self):
        notion = MagicMock()
        services = _google_services()
        notion.get_notion_task.return_value = ({}, [])
        services["mapping-job"].get_gcal_event.return_value = [
            {
                "id": "incomplete-event",
                "extendedProperties": {
                    "private": {
                        "noticaMapping": "mapping-job"
                    }
                },
            }
        ]

        result = project_notion_to_google_calendar(
            copy.deepcopy(SETTING),
            notion,
            services,
        )

        services["mapping-job"].delete_projection.assert_not_called()
        error = result["body"]["message"]["errors"][0]
        self.assertEqual(
            error["error_code"],
            "projection_identity_mismatch",
        )
        self.assertFalse(error["retriable"])


if __name__ == "__main__":
    unittest.main()
