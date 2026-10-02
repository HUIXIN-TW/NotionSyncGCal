import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))

from gcal.event_identity import deterministic_google_event_id  # noqa: E402
from sync.mapping_write_fence import MappingWriteFenceError  # noqa: E402
from sync.sync import synchronize_notion_and_google_calendar  # noqa: E402


def user_setting():
    return {
        "source_id": "source-1",
        "page_property": {
            "GCal_Name_Notion_Name": "calendar",
            "Delete_Notion_Name": "deleted",
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
        "gcal_route_by_name": {
            "Learning": {
                "mapping_id": "mapping-learning",
                "mapping_version": 3,
                "calendar_id": "learning@example.com",
            },
            "Job": {
                "mapping_id": "mapping-job",
                "mapping_version": 5,
                "calendar_id": "job@example.com",
            },
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


def event_id():
    return deterministic_google_event_id("source-1", "page-1")


def services(events=None):
    notion_service = MagicMock()
    notion_service.get_notion_task.return_value = ({}, [notion_task()])
    google_service = MagicMock()
    google_service.get_gcal_event.return_value = events or []
    google_service.get_gcal_event_by_id.return_value = None
    return notion_service, google_service


class SyncMappingWriteFenceTests(unittest.TestCase):
    def _patch_notion_values(self, *, deleted=False, calendar_name="Learning"):
        return (
            patch("sync.sync.get_select", return_value=calendar_name),
            patch("sync.sync.get_rich_text", return_value=""),
            patch("sync.sync.get_checkbox", return_value=deleted),
        )

    def test_create_is_blocked_before_google_mutation(self):
        notion_service, google_service = services()
        patches = self._patch_notion_values()

        with patches[0], patches[1], patches[2], patch(
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
        event = {
            "id": event_id(),
            "summary": "Task",
            "updated": "2026-10-01T00:00:00+00:00",
            "organizer": {"email": "learning@example.com"},
        }
        notion_service, google_service = services([event])
        patches = self._patch_notion_values(deleted=True)

        with patches[0], patches[1], patches[2], patch(
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
            "id": event_id(),
            "summary": "Task",
            "updated": "2026-10-01T00:00:00+00:00",
            "organizer": {"email": "learning@example.com"},
        }
        notion_service, google_service = services([event])
        patches = self._patch_notion_values()

        with patches[0], patches[1], patches[2], patch(
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
            "id": event_id(),
            "summary": "Task",
            "updated": "2026-10-01T00:00:00+00:00",
            "organizer": {"email": "job@example.com"},
        }
        notion_service, google_service = services([event])
        patches = self._patch_notion_values(calendar_name="Learning")

        with patches[0], patches[1], patches[2], patch(
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

    def test_matching_route_allows_create_with_deterministic_identity_and_metadata(self):
        notion_service, google_service = services()
        google_service.create_gcal_event.return_value = event_id()
        patches = self._patch_notion_values()

        with patches[0], patches[1], patches[2], patch(
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
        google_service.create_gcal_event.assert_called_once_with(
            notion_task(),
            "learning@example.com",
            event_id(),
            {
                "noticaSourceId": "source-1",
                "noticaMappingId": "mapping-learning",
                "noticaMappingVersion": "3",
            },
        )

    def test_move_preserves_event_id_and_updates_destination_metadata(self):
        event = {
            "id": event_id(),
            "summary": "Task",
            "updated": "2026-10-01T00:00:00+00:00",
            "organizer": {"email": "job@example.com"},
        }
        notion_service, google_service = services([event])
        patches = self._patch_notion_values(calendar_name="Learning")

        with patches[0], patches[1], patches[2], patch(
            "sync.sync.assert_current_google_write_route",
            return_value=None,
        ):
            result = synchronize_notion_and_google_calendar(
                user_setting(),
                notion_service,
                google_service,
                compare_time=False,
                should_update_notion_tasks=False,
            )

        self.assertEqual(result["statusCode"], 200)
        google_service.move_gcal_event.assert_called_once_with(
            event_id(),
            "learning@example.com",
            "job@example.com",
        )
        google_service.update_gcal_event.assert_called_once_with(
            notion_task(),
            "learning@example.com",
            event_id(),
            {
                "noticaSourceId": "source-1",
                "noticaMappingId": "mapping-learning",
                "noticaMappingVersion": "3",
            },
        )

    def test_delete_uses_actual_provider_calendar_when_notion_calendar_changed(self):
        event = {
            "id": event_id(),
            "summary": "Task",
            "updated": "2026-10-01T00:00:00+00:00",
            "organizer": {"email": "job@example.com"},
        }
        notion_service, google_service = services([event])
        patches = self._patch_notion_values(deleted=True, calendar_name="Learning")

        with patches[0], patches[1], patches[2], patch(
            "sync.sync.assert_current_google_write_route",
            return_value=None,
        ) as fence:
            result = synchronize_notion_and_google_calendar(
                user_setting(),
                notion_service,
                google_service,
                compare_time=False,
            )

        self.assertEqual(result["statusCode"], 200)
        fence.assert_called_once_with(
            user_setting(),
            "Job",
            "job@example.com",
        )
        google_service.delete_gcal_event.assert_called_once_with(
            "job@example.com",
            event_id(),
        )
        notion_service.delete_notion_task.assert_called_once_with("page-1")

    def test_out_of_window_event_is_resolved_before_move(self):
        event = {
            "id": event_id(),
            "summary": "Task",
            "updated": "2026-10-01T00:00:00+00:00",
            "organizer": {"email": "job@example.com"},
            "_notica_calendar_id": "job@example.com",
        }
        notion_service, google_service = services()
        patches = self._patch_notion_values(calendar_name="Learning")

        def lookup(calendar_id, provider_event_id):
            self.assertEqual(provider_event_id, event_id())
            if calendar_id == "job@example.com":
                return event
            return None

        google_service.get_gcal_event_by_id.side_effect = lookup

        with patches[0], patches[1], patches[2], patch(
            "sync.sync.assert_current_google_write_route",
            return_value=None,
        ):
            result = synchronize_notion_and_google_calendar(
                user_setting(),
                notion_service,
                google_service,
                compare_time=False,
                should_update_notion_tasks=False,
            )

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(
            google_service.get_gcal_event_by_id.call_args_list,
            [
                call("learning@example.com", event_id()),
                call("job@example.com", event_id()),
            ],
        )
        google_service.move_gcal_event.assert_called_once_with(
            event_id(),
            "learning@example.com",
            "job@example.com",
        )
        google_service.update_gcal_event.assert_called_once_with(
            notion_task(),
            "learning@example.com",
            event_id(),
            {
                "noticaSourceId": "source-1",
                "noticaMappingId": "mapping-learning",
                "noticaMappingVersion": "3",
            },
        )


if __name__ == "__main__":
    unittest.main()
