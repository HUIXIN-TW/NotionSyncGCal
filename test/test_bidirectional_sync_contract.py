"""Regression contract tests for full Notion <-> Google Calendar bidirectional sync.

These tests intentionally lock product behaviour that must survive refactors:

- A user-created Google Calendar event in an owned/configured calendar creates a Notion task.
- The Google provider event ID is persisted on the created Notion task.
- On later syncs, that persisted provider ID matches the same Google event instead of
  creating a duplicate Notion task.
- A Notion-originated Google event writes the provider-generated Google event ID back to Notion.
- The persisted provider ID remains the association for later update, move, and delete flows.
- Direction flags are respected: Google-only and Notion-only modes must not mutate the disabled side.
- Provider/Notion failures must not fabricate or destroy the event association.
- Events that are not owned/configured or cannot be represented safely in Notion are rejected.

The provider association is part of the current sync contract. It must not be removed
unless an explicitly approved replacement preserves both creation directions and all
follow-up update/move/delete behaviour.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))

from notion.notion_service import NotionService  # noqa: E402
from sync.sync import synchronize_notion_and_google_calendar  # noqa: E402


CALENDAR_NAME = "My Calendar"
CALENDAR_ID = "cal@group.calendar.google.com"
OTHER_CALENDAR_NAME = "Other Calendar"
OTHER_CALENDAR_ID = "other@group.calendar.google.com"

USER_SETTING = {
    "page_property": {
        "Task_Notion_Name": "task-id",
        "Date_Notion_Name": "date-id",
        "GCal_End_Date_Notion_Name": "end-id",
        "GCal_EventId_Notion_Name": "event-id",
        "GCal_Name_Notion_Name": "calendar-id",
        "GCal_Sync_Time_Notion_Name": "sync-id",
        "Delete_Notion_Name": "delete-id",
        "ExtraInfo_Notion_Name": "extra-id",
        "Location_Notion_Name": "location-id",
        "CompleteIcon_Notion_Name": "icon-id",
    },
    "gcal_name_dict": {
        CALENDAR_NAME: CALENDAR_ID,
        OTHER_CALENDAR_NAME: OTHER_CALENDAR_ID,
    },
    "gcal_id_dict": {
        CALENDAR_ID: CALENDAR_NAME,
        OTHER_CALENDAR_ID: OTHER_CALENDAR_NAME,
    },
    "gcal_default_name": CALENDAR_NAME,
    "gcal_default_id": CALENDAR_ID,
    "google_timemin": "2026-10-01T00:00:00+08:00",
    "google_timemax": "2026-11-01T00:00:00+08:00",
    "timezone": "Australia/Perth",
    "timecode": "+08:00",
    "database_id": "db-id",
    "default_event_length": 60,
}

GOOGLE_CREATED_EVENT = {
    "id": "google-created-001",
    "status": "confirmed",
    "summary": "Created in Google",
    "description": "Google-originated event",
    "location": "Perth",
    "organizer": {"email": CALENDAR_ID},
    "updated": "2026-10-02T10:00:00.000Z",
    "start": {
        "dateTime": "2026-10-03T09:00:00+08:00",
        "timeZone": "Australia/Perth",
    },
    "end": {
        "dateTime": "2026-10-03T10:00:00+08:00",
        "timeZone": "Australia/Perth",
    },
}


def _make_notion_task(
    gcal_event_id,
    *,
    last_edited_time="2026-10-02T09:00:00.000Z",
    calendar_name=CALENDAR_NAME,
    deleted=False,
):
    props = USER_SETTING["page_property"]
    return {
        "id": "notion-page-001",
        "last_edited_time": last_edited_time,
        "properties": {
            "Name": {
                "id": props["Task_Notion_Name"],
                "title": [{"plain_text": "Created in Google"}],
            },
            "Calendar": {
                "id": props["GCal_Name_Notion_Name"],
                "select": {"name": calendar_name},
            },
            "Delete": {
                "id": props["Delete_Notion_Name"],
                "checkbox": deleted,
            },
            "GCal Event ID": {
                "id": props["GCal_EventId_Notion_Name"],
                "rich_text": ([{"plain_text": gcal_event_id}] if gcal_event_id else []),
            },
            "Last Sync": {
                "id": props["GCal_Sync_Time_Notion_Name"],
                "rich_text": [],
            },
        },
    }


def _run_sync(
    gcal_events,
    notion_tasks,
    *,
    compare_time=True,
    should_update_notion_tasks=True,
    should_update_google_events=True,
):
    notion_service = MagicMock()
    google_service = MagicMock()

    notion_service.get_notion_task.return_value = ({}, notion_tasks)
    google_service.get_gcal_event.return_value = gcal_events

    result = synchronize_notion_and_google_calendar(
        user_setting={**USER_SETTING},
        notion_service=notion_service,
        google_service=google_service,
        compare_time=compare_time,
        should_update_notion_tasks=should_update_notion_tasks,
        should_update_google_events=should_update_google_events,
    )
    return notion_service, google_service, result


class TestGoogleOriginatedCreationContract(unittest.TestCase):
    def test_owned_unmatched_google_event_creates_notion_task(self):
        event = {**GOOGLE_CREATED_EVENT}

        notion_service, google_service, result = _run_sync(
            gcal_events=[event],
            notion_tasks=[],
        )

        self.assertEqual(result["statusCode"], 200)
        notion_service.create_notion_task.assert_called_once_with(event, CALENDAR_NAME)
        google_service.create_gcal_event.assert_not_called()

    def test_google_originated_task_persists_provider_event_id(self):
        mock_client = MagicMock()
        logger = MagicMock()

        with patch("notion.notion_service.Client", return_value=mock_client):
            service = NotionService("fake-token", USER_SETTING, logger)

        service.create_notion_task({**GOOGLE_CREATED_EVENT}, CALENDAR_NAME)

        mock_client.pages.create.assert_called_once()
        properties = mock_client.pages.create.call_args.kwargs["properties"]

        self.assertEqual(
            properties[USER_SETTING["page_property"]["GCal_EventId_Notion_Name"]]["rich_text"][0]["text"]["content"],
            GOOGLE_CREATED_EVENT["id"],
        )
        self.assertEqual(
            properties[USER_SETTING["page_property"]["GCal_Name_Notion_Name"]]["select"]["name"],
            CALENDAR_NAME,
        )

    def test_persisted_provider_id_matches_same_google_event_on_next_sync(self):
        event = {**GOOGLE_CREATED_EVENT}
        notion_task = _make_notion_task(event["id"])

        notion_service, google_service, result = _run_sync(
            gcal_events=[event],
            notion_tasks=[notion_task],
        )

        self.assertEqual(result["statusCode"], 200)
        notion_service.update_notion_task.assert_called_once()
        update_args = notion_service.update_notion_task.call_args.args
        self.assertEqual(update_args[0], notion_task["id"])
        self.assertEqual(update_args[1], event)
        self.assertEqual(update_args[2], CALENDAR_NAME)

        notion_service.create_notion_task.assert_not_called()
        google_service.create_gcal_event.assert_not_called()

    def test_google_to_notion_direction_can_be_disabled_without_creating_task(self):
        event = {**GOOGLE_CREATED_EVENT}

        notion_service, _, result = _run_sync(
            gcal_events=[event],
            notion_tasks=[],
            should_update_notion_tasks=False,
            should_update_google_events=True,
        )

        self.assertEqual(result["statusCode"], 200)
        notion_service.create_notion_task.assert_not_called()

    def test_unowned_google_event_does_not_create_notion_task(self):
        event = {
            **GOOGLE_CREATED_EVENT,
            "id": "invited-event-001",
            "organizer": {"email": "other-owner@example.com"},
        }

        notion_service, _, result = _run_sync(
            gcal_events=[event],
            notion_tasks=[],
        )

        notion_service.create_notion_task.assert_not_called()
        self.assertEqual(result["statusCode"], 200)
        errors = result["body"]["message"]["errors"]
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["action"], "create_notion")
        self.assertEqual(errors[0]["error_code"], "gcal_event_not_owned")

    def test_google_event_without_owner_route_does_not_create_notion_task(self):
        event = {
            **GOOGLE_CREATED_EVENT,
            "id": "missing-owner-001",
            "organizer": {},
        }

        notion_service, _, result = _run_sync(
            gcal_events=[event],
            notion_tasks=[],
        )

        notion_service.create_notion_task.assert_not_called()
        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(
            result["body"]["message"]["errors"][0]["error_code"],
            "gcal_event_not_owned",
        )

    def test_google_event_with_too_long_description_is_not_materialized(self):
        event = {
            **GOOGLE_CREATED_EVENT,
            "id": "too-long-001",
            "description": "x" * 2001,
        }

        notion_service, _, result = _run_sync(
            gcal_events=[event],
            notion_tasks=[],
        )

        notion_service.create_notion_task.assert_not_called()
        self.assertEqual(result["statusCode"], 200)
        error = result["body"]["message"]["errors"][0]
        self.assertEqual(error["action"], "create_notion")
        self.assertEqual(error["error_code"], "gcal_description_too_long")
        self.assertFalse(error["retriable"])

    def test_notion_create_failure_reports_error_without_google_mutation(self):
        event = {**GOOGLE_CREATED_EVENT}
        notion_service = MagicMock()
        google_service = MagicMock()
        notion_service.get_notion_task.return_value = ({}, [])
        google_service.get_gcal_event.return_value = [event]
        notion_service.create_notion_task.side_effect = RuntimeError("notion write failed")

        result = synchronize_notion_and_google_calendar(
            user_setting={**USER_SETTING},
            notion_service=notion_service,
            google_service=google_service,
            compare_time=True,
            should_update_notion_tasks=True,
            should_update_google_events=True,
        )

        self.assertEqual(result["statusCode"], 200)
        google_service.create_gcal_event.assert_not_called()
        error = result["body"]["message"]["errors"][0]
        self.assertEqual(error["action"], "create_notion")
        self.assertEqual(error["error_code"], "runtime_error")
        self.assertTrue(error["retriable"])


class TestNotionOriginatedCreationContract(unittest.TestCase):
    def test_provider_generated_event_id_is_written_back_to_notion(self):
        notion_task = _make_notion_task("")
        notion_service = MagicMock()
        google_service = MagicMock()

        notion_service.get_notion_task.return_value = ({}, [notion_task])
        google_service.get_gcal_event.return_value = []
        google_service.create_gcal_event.return_value = "provider-created-001"

        result = synchronize_notion_and_google_calendar(
            user_setting={**USER_SETTING},
            notion_service=notion_service,
            google_service=google_service,
            compare_time=True,
            should_update_notion_tasks=True,
            should_update_google_events=True,
        )

        self.assertEqual(result["statusCode"], 200)
        google_service.create_gcal_event.assert_called_once_with(
            notion_task,
            CALENDAR_ID,
        )
        notion_service.update_notion_task_for_new_gcal_event_id.assert_called_once_with(
            notion_task["id"],
            "provider-created-001",
        )

    def test_notion_to_google_direction_can_be_disabled_without_creating_event(self):
        notion_task = _make_notion_task("")

        notion_service, google_service, result = _run_sync(
            gcal_events=[],
            notion_tasks=[notion_task],
            should_update_notion_tasks=True,
            should_update_google_events=False,
        )

        self.assertEqual(result["statusCode"], 200)
        google_service.create_gcal_event.assert_not_called()
        notion_service.update_notion_task_for_new_gcal_event_id.assert_not_called()

    def test_google_create_failure_does_not_write_provider_association(self):
        notion_task = _make_notion_task("")
        notion_service = MagicMock()
        google_service = MagicMock()

        notion_service.get_notion_task.return_value = ({}, [notion_task])
        google_service.get_gcal_event.return_value = []
        google_service.create_gcal_event.side_effect = RuntimeError("google write failed")

        result = synchronize_notion_and_google_calendar(
            user_setting={**USER_SETTING},
            notion_service=notion_service,
            google_service=google_service,
            compare_time=True,
            should_update_notion_tasks=True,
            should_update_google_events=True,
        )

        notion_service.update_notion_task_for_new_gcal_event_id.assert_not_called()
        self.assertEqual(result["statusCode"], 200)
        error = result["body"]["message"]["errors"][0]
        self.assertEqual(error["action"], "create_gcal")
        self.assertEqual(error["error_code"], "runtime_error")
        self.assertTrue(error["retriable"])

    def test_persisted_provider_id_updates_same_google_event_when_notion_is_newer(self):
        event_id = "provider-created-001"
        notion_task = _make_notion_task(
            event_id,
            last_edited_time="2026-10-02T11:00:00.000Z",
        )
        event = {
            **GOOGLE_CREATED_EVENT,
            "id": event_id,
            "updated": "2026-10-02T10:00:00.000Z",
        }

        notion_service, google_service, result = _run_sync(
            gcal_events=[event],
            notion_tasks=[notion_task],
        )

        self.assertEqual(result["statusCode"], 200)
        google_service.update_gcal_event.assert_called_once_with(
            notion_task,
            CALENDAR_ID,
            event_id,
        )
        notion_service.create_notion_task.assert_not_called()
        notion_service.update_notion_task.assert_not_called()

    def test_calendar_move_preserves_same_persisted_provider_event_id(self):
        event_id = "provider-created-001"
        notion_task = _make_notion_task(
            event_id,
            last_edited_time="2026-10-02T11:00:00.000Z",
            calendar_name=OTHER_CALENDAR_NAME,
        )
        event = {
            **GOOGLE_CREATED_EVENT,
            "id": event_id,
            "updated": "2026-10-02T10:00:00.000Z",
            "organizer": {"email": CALENDAR_ID},
        }

        notion_service, google_service, result = _run_sync(
            gcal_events=[event],
            notion_tasks=[notion_task],
        )

        self.assertEqual(result["statusCode"], 200)
        google_service.move_gcal_event.assert_called_once_with(
            event_id,
            OTHER_CALENDAR_ID,
            CALENDAR_ID,
        )
        google_service.update_gcal_event.assert_called_once_with(
            notion_task,
            OTHER_CALENDAR_ID,
            event_id,
        )
        notion_service.update_notion_task_for_new_gcal_event_id.assert_not_called()
        notion_service.create_notion_task.assert_not_called()


class TestProviderAssociationDeleteContract(unittest.TestCase):
    def test_delete_uses_persisted_provider_event_id_and_marks_notion_deleted(self):
        event_id = "provider-created-001"
        notion_task = _make_notion_task(event_id, deleted=True)
        event = {
            **GOOGLE_CREATED_EVENT,
            "id": event_id,
        }

        notion_service, google_service, result = _run_sync(
            gcal_events=[event],
            notion_tasks=[notion_task],
        )
        notion_service.get_notion_task_by_gcal_event_id.return_value = []

        self.assertEqual(result["statusCode"], 200)
        google_service.delete_gcal_event.assert_called_once_with(
            CALENDAR_ID,
            event_id,
        )
        notion_service.delete_notion_task.assert_called_once_with(notion_task["id"])

    def test_delete_provider_failure_preserves_notion_linkage(self):
        event_id = "provider-created-001"
        notion_task = _make_notion_task(event_id, deleted=True)
        notion_service = MagicMock()
        google_service = MagicMock()

        notion_service.get_notion_task.return_value = ({}, [notion_task])
        google_service.get_gcal_event.return_value = []
        google_service.delete_gcal_event.side_effect = RuntimeError("google delete failed")

        result = synchronize_notion_and_google_calendar(
            user_setting={**USER_SETTING},
            notion_service=notion_service,
            google_service=google_service,
            compare_time=True,
            should_update_notion_tasks=True,
            should_update_google_events=True,
        )

        notion_service.delete_notion_task.assert_not_called()
        notion_service.get_notion_task_by_gcal_event_id.assert_not_called()
        self.assertEqual(result["statusCode"], 200)
        error = result["body"]["message"]["errors"][0]
        self.assertEqual(error["action"], "delete_gcal")
        self.assertEqual(error["gcal_event_id"], event_id)
        self.assertTrue(error["retriable"])


if __name__ == "__main__":
    unittest.main()
