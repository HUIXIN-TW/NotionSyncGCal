import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from googleapiclient.errors import HttpError

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))

from gcal.gcal_service import GoogleService, SettingError  # noqa: E402
from sync.projection_identity import (  # noqa: E402
    ProjectionIdentityError,
    build_projection_identity,
)


USER_SETTING = {
    "owner_user_uuid": "11111111-1111-4111-8111-111111111111",
    "settings_version": 1,
    "source_id": "source-1",
    "source_version": 1,
    "mapping_id": "mapping-1",
    "mapping_version": 1,
    "calendar_id": "calendar@example.com",
    "routing": {"mode": "all"},
    "google_timemin": "2026-05-01T00:00:00+08:00",
    "google_timemax": "2026-06-01T00:00:00+08:00",
    "timezone": "Australia/Perth",
    "database_id": "database-1",
    "default_event_length": 60,
    "page_property": {
        "Task_Notion_Name": "Task",
        "Date_Notion_Name": "Date",
        "Delete_Notion_Name": "Delete",
        "ExtraInfo_Notion_Name": "Extra",
        "Location_Notion_Name": "Location",
        "CompleteIcon_Notion_Name": "Icon",
    },
}

TASK_ID = "22222222-2222-4222-8222-222222222222"


def _projection():
    return build_projection_identity(USER_SETTING, TASK_ID)


def _owned_event(projection=None):
    projection = projection or _projection()
    return {
        "id": projection["event_id"],
        "status": "confirmed",
        "start": {"date": "2026-05-20"},
        "end": {"date": "2026-05-21"},
        "extendedProperties": {"private": dict(projection["private"])},
    }


def _http_error(status):
    class Resp:
        reason = "test"
    Resp.status = status
    return HttpError(Resp(), b'{"error":{"message":"test"}}')


def _service(*, guard=None):
    api = MagicMock()
    token = MagicMock()
    token.credentials = MagicMock()
    logger = MagicMock()
    with patch("gcal.gcal_service.build", return_value=api):
        service = GoogleService(
            dict(USER_SETTING),
            token,
            logger,
            mutation_guard=guard,
        )
    service.make_event_body = MagicMock(return_value={"summary": "Task"})
    return service, api, logger


class GoogleCalendarTargetTests(unittest.TestCase):
    def test_validates_target_by_immutable_calendar_id(self):
        service, api, _ = _service()
        api.calendarList.return_value.get.return_value.execute.return_value = {
            "id": "calendar@example.com",
            "accessRole": "writer",
        }

        self.assertTrue(service.validate_calendar_access())
        api.calendarList.return_value.get.assert_called_once_with(
            calendarId="calendar@example.com"
        )

    def test_rejects_unexpected_calendar_identity(self):
        service, api, _ = _service()
        api.calendarList.return_value.get.return_value.execute.return_value = {
            "id": "other@example.com",
            "accessRole": "writer",
        }

        with self.assertRaisesRegex(SettingError, "unexpected Calendar ID"):
            service.validate_calendar_access()

    def test_rejects_calendar_that_is_no_longer_writable(self):
        service, api, _ = _service()
        api.calendarList.return_value.get.return_value.execute.return_value = {
            "id": "calendar@example.com",
            "accessRole": "reader",
        }

        with self.assertRaisesRegex(SettingError, "not writable"):
            service.validate_calendar_access()


class MappingScopedListTests(unittest.TestCase):
    def test_filters_provider_list_by_mapping_private_property(self):
        service, api, _ = _service()
        api.events.return_value.list.return_value.execute.return_value = {
            "items": [_owned_event()]
        }

        events = service.get_gcal_event()

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["_notica_calendar_id"], "calendar@example.com")
        _, kwargs = api.events.return_value.list.call_args
        self.assertEqual(kwargs["calendarId"], "calendar@example.com")
        self.assertEqual(
            kwargs["privateExtendedProperty"],
            ["noticaMapping=mapping-1"],
        )
        self.assertEqual(kwargs["timeMin"], USER_SETTING["google_timemin"])
        self.assertEqual(kwargs["timeMax"], USER_SETTING["google_timemax"])

    def test_ignores_cancelled_and_missing_start_rows(self):
        service, api, _ = _service()
        api.events.return_value.list.return_value.execute.return_value = {
            "items": [
                {**_owned_event(), "status": "cancelled"},
                {
                    "id": "missing-start",
                    "status": "confirmed",
                    "extendedProperties": {"private": {}},
                },
                _owned_event(),
            ]
        }

        events = service.get_gcal_event()

        self.assertEqual([event["id"] for event in events], [_projection()["event_id"]])


class ProjectionUpsertTests(unittest.TestCase):
    def test_missing_projection_inserts_deterministic_id_and_private_metadata(self):
        guard = MagicMock()
        service, api, _ = _service(guard=guard)
        projection = _projection()
        api.events.return_value.get.return_value.execute.side_effect = _http_error(404)
        api.events.return_value.insert.return_value.execute.return_value = _owned_event(projection)

        event_id = service.upsert_projection({"id": TASK_ID}, projection)

        self.assertEqual(event_id, projection["event_id"])
        guard.assert_called_once()
        _, kwargs = api.events.return_value.insert.call_args
        self.assertEqual(kwargs["calendarId"], "calendar@example.com")
        self.assertEqual(kwargs["body"]["id"], projection["event_id"])
        self.assertEqual(
            kwargs["body"]["extendedProperties"]["private"],
            projection["private"],
        )

    def test_owned_projection_patches_without_insert(self):
        guard = MagicMock()
        service, api, _ = _service(guard=guard)
        projection = _projection()
        api.events.return_value.get.return_value.execute.return_value = _owned_event(projection)
        api.events.return_value.patch.return_value.execute.return_value = _owned_event(projection)

        service.upsert_projection({"id": TASK_ID}, projection)

        guard.assert_called_once()
        api.events.return_value.patch.assert_called_once()
        api.events.return_value.insert.assert_not_called()

    def test_untagged_or_wrong_projection_is_never_adopted(self):
        guard = MagicMock()
        service, api, _ = _service(guard=guard)
        projection = _projection()
        api.events.return_value.get.return_value.execute.return_value = {
            "id": projection["event_id"],
            "extendedProperties": {"private": {}},
        }

        with self.assertRaises(ProjectionIdentityError):
            service.upsert_projection({"id": TASK_ID}, projection)

        guard.assert_not_called()
        api.events.return_value.patch.assert_not_called()
        api.events.return_value.insert.assert_not_called()

    def test_insert_conflict_reads_owned_event_then_converges_by_patch(self):
        guard = MagicMock()
        service, api, _ = _service(guard=guard)
        projection = _projection()
        api.events.return_value.get.return_value.execute.side_effect = [
            _http_error(404),
            _owned_event(projection),
        ]
        api.events.return_value.insert.return_value.execute.side_effect = _http_error(409)
        api.events.return_value.patch.return_value.execute.return_value = _owned_event(projection)

        event_id = service.upsert_projection({"id": TASK_ID}, projection)

        self.assertEqual(event_id, projection["event_id"])
        self.assertEqual(guard.call_count, 2)
        api.events.return_value.insert.assert_called_once()
        api.events.return_value.patch.assert_called_once()

    def test_ambiguous_insert_response_recovers_by_deterministic_readback(self):
        guard = MagicMock()
        service, api, _ = _service(guard=guard)
        projection = _projection()
        api.events.return_value.get.return_value.execute.side_effect = [
            _http_error(404),
            _owned_event(projection),
        ]
        api.events.return_value.insert.return_value.execute.side_effect = RuntimeError(
            "response lost after provider write"
        )

        event_id = service.upsert_projection({"id": TASK_ID}, projection)

        self.assertEqual(event_id, projection["event_id"])
        guard.assert_called_once()
        api.events.return_value.patch.assert_not_called()


class ProjectionDeleteTests(unittest.TestCase):
    def test_absent_projection_is_already_converged_without_write_guard(self):
        guard = MagicMock()
        service, api, _ = _service(guard=guard)
        api.events.return_value.get.return_value.execute.side_effect = _http_error(404)

        self.assertTrue(service.delete_projection(_projection()))

        guard.assert_not_called()
        api.events.return_value.delete.assert_not_called()

    def test_owned_projection_is_guarded_then_deleted(self):
        guard = MagicMock()
        service, api, _ = _service(guard=guard)
        projection = _projection()
        api.events.return_value.get.return_value.execute.return_value = _owned_event(projection)
        api.events.return_value.delete.return_value.execute.return_value = None

        self.assertTrue(service.delete_projection(projection))

        guard.assert_called_once()
        api.events.return_value.delete.assert_called_once_with(
            calendarId="calendar@example.com",
            eventId=projection["event_id"],
        )

    def test_wrong_metadata_blocks_delete(self):
        guard = MagicMock()
        service, api, _ = _service(guard=guard)
        projection = _projection()
        event = _owned_event(projection)
        event["extendedProperties"]["private"]["noticaSource"] = "other-source"
        api.events.return_value.get.return_value.execute.return_value = event

        with self.assertRaises(ProjectionIdentityError):
            service.delete_projection(projection)

        guard.assert_not_called()
        api.events.return_value.delete.assert_not_called()

    def test_provider_404_after_owned_read_is_converged(self):
        guard = MagicMock()
        service, api, _ = _service(guard=guard)
        projection = _projection()
        api.events.return_value.get.return_value.execute.return_value = _owned_event(projection)
        api.events.return_value.delete.return_value.execute.side_effect = _http_error(404)

        self.assertTrue(service.delete_projection(projection))
        guard.assert_called_once()


if __name__ == "__main__":
    unittest.main()
