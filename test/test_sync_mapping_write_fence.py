import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))

from sync.mapping_write_fence import MappingWriteFenceError  # noqa: E402
from sync.sync import synchronize_notion_and_google_calendar  # noqa: E402


def user_setting():
    return {
        "page_property": {
            "GCal_Name_Notion_Name": "calendar",
            "GCal_EventId_Notion_Name": "event-id",
            "Delete_Notion_Name": "deleted",
            "Task_Notion_Name": "task",
            "GCal_Sync_Time_Notion_Name": "sync-time",
        },
        "gcal_name_dict": {
            "Learning": "learning@example.com",
            "Job": "job@example.com",
        },
        "gcal_id_dict": {
            "learning@example.com": "Learning",
            "job@example.com": "Job",
        },
        "gcal_default_name": "Learning",
        "gcal_default_id": "learning@example.com",
    }


def notion_task():
    return {
        "id": "page-1",
        "properties": {},
        "last_edited_time": "2026-10-01T00:00:00+00:00",
    }


def services(events=None):
    notion_service = MagicMock()
    notion_service.get_notion_task.return_value = ({}, [notion_task()])
    google_service = MagicMock()
    google_service.get_gcal_event.return_value = events or []
    return notion_service, google_service


class SyncMappingWriteFenceTests(unittest.TestCase):
    def _patch_notion_values(self, *, event_id=None, deleted=False, calendar_name="Learning"):
        return (
            patch("sync.sync.get_select", return_value=calendar_name),
            patch("sync.sync.get_rich_text", side_effect=[event_id, ""]),
            patch("sync.sync.get_checkbox", return_value=deleted),
            patch("sync.sync.get_title", return_value="Task"),
        )

    def test_create_is_blocked_before_google_mutation(self):
        notion_service, google_service = services()
        patches = self._patch_notion_values(event_id=None)

        with patches[0], patches[1], patches[2], patches[3], patch(
            "sync.sync.assert_current_google_write_route",
            side_effect=MappingWriteFenceError("mapping_version_changed"),
        ):
            result = synchronize_notion_and_google_calendar(
                user_setting(),
                notion_service,
                google_service,
                compare_time=False,
            )

        self.assertEqual(result["statusCode"], 409)
        self.assertEqual(
            result["body"]["message"]["error_code"],
            "mapping_write_fence_blocked",
        )
        google_service.create_gcal_event.assert_not_called()

    def test_delete_is_blocked_before_google_mutation(self):
        notion_service, google_service = services()
        patches = self._patch_notion_values(event_id="event-1", deleted=True)

        with patches[0], patches[1], patches[2], patches[3], patch(
            "sync.sync.assert_current_google_write_route",
            side_effect=MappingWriteFenceError("mapping_inactive"),
        ):
            result = synchronize_notion_and_google_calendar(
                user_setting(),
                notion_service,
                google_service,
                compare_time=False,
            )

        self.assertEqual(result["statusCode"], 409)
        google_service.delete_gcal_event.assert_not_called()
        notion_service.delete_notion_task.assert_not_called()

    def test_update_is_blocked_before_google_mutation(self):
        event = {
            "id": "event-1",
            "summary": "Task",
            "updated": "2026-10-01T00:00:00+00:00",
            "organizer": {"email": "learning@example.com"},
        }
        notion_service, google_service = services([event])
        patches = self._patch_notion_values(event_id="event-1")

        with patches[0], patches[1], patches[2], patches[3], patch(
            "sync.sync.assert_current_google_write_route",
            side_effect=MappingWriteFenceError("source_version_changed"),
        ):
            result = synchronize_notion_and_google_calendar(
                user_setting(),
                notion_service,
                google_service,
                compare_time=False,
            )

        self.assertEqual(result["statusCode"], 409)
        google_service.update_gcal_event.assert_not_called()

    def test_move_is_blocked_before_google_mutation_when_destination_is_stale(self):
        event = {
            "id": "event-1",
            "summary": "Task",
            "updated": "2026-10-01T00:00:00+00:00",
            "organizer": {"email": "job@example.com"},
        }
        notion_service, google_service = services([event])
        patches = self._patch_notion_values(event_id="event-1", calendar_name="Learning")

        with patches[0], patches[1], patches[2], patches[3], patch(
            "sync.sync.assert_current_google_write_route",
            side_effect=[None, MappingWriteFenceError("mapping_version_changed")],
        ):
            result = synchronize_notion_and_google_calendar(
                user_setting(),
                notion_service,
                google_service,
                compare_time=False,
            )

        self.assertEqual(result["statusCode"], 409)
        google_service.move_gcal_event.assert_not_called()
        google_service.update_gcal_event.assert_not_called()

    def test_matching_route_allows_create(self):
        notion_service, google_service = services()
        google_service.create_gcal_event.return_value = "event-new"
        patches = self._patch_notion_values(event_id=None)

        with patches[0], patches[1], patches[2], patches[3], patch(
            "sync.sync.assert_current_google_write_route",
            return_value=None,
        ) as fence:
            result = synchronize_notion_and_google_calendar(
                user_setting(),
                notion_service,
                google_service,
                compare_time=False,
                should_update_notion_tasks=False,
            )

        self.assertEqual(result["statusCode"], 200)
        fence.assert_called_once_with(
            user_setting(),
            "Learning",
            "learning@example.com",
        )
        google_service.create_gcal_event.assert_called_once()
        notion_service.update_notion_task_for_new_gcal_event_id.assert_called_once_with(
            "page-1",
            "event-new",
        )


if __name__ == "__main__":
    unittest.main()
