"""
Tests for recurring Google Calendar event handling and API pagination.

Covers:
- singleEvents=True / orderBy=startTime are sent to the GCal API
- Multi-page responses are fully consumed via nextPageToken
- Cancelled recurring exceptions and missing-start events are filtered
- get_event_time always uses event["start"], never originalStartTime
- Each expanded recurring instance is treated as an independent event
  identified by its own instance ID (not recurringEventId)
- Multiple instances from the same series do not overwrite each other
- No N+1 Notion queries per recurring instance
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from googleapiclient.errors import HttpError

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))

from gcal.gcal_service import GoogleService  # noqa: E402
from notion.notion_service import NotionService  # noqa: E402


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

MINIMAL_USER_SETTING = {
    "page_property": {
        "Task_Notion_Name": "Name",
        "Date_Notion_Name": "Date",
        "GCal_End_Date_Notion_Name": "GCal End Date",
        "GCal_EventId_Notion_Name": "GCal Event ID",
        "GCal_Name_Notion_Name": "Calendar",
        "GCal_Sync_Time_Notion_Name": "Last Sync",
        "Delete_Notion_Name": "Delete",
        "ExtraInfo_Notion_Name": "Extra Info",
        "Location_Notion_Name": "Location",
        "CompleteIcon_Notion_Name": "Complete Icon",
    },
    "gcal_name_dict": {"My Calendar": "cal@group.calendar.google.com"},
    "gcal_id_dict": {"cal@group.calendar.google.com": "My Calendar"},
    "gcal_default_name": "My Calendar",
    "gcal_default_id": "cal@group.calendar.google.com",
    "google_timemin": "2026-05-01T00:00:00+08:00",
    "google_timemax": "2026-06-01T00:00:00+08:00",
    "timezone": "Australia/Perth",
    "timecode": "+08:00",
    "database_id": "db-id",
    "default_event_length": 60,
}

SINGLE_TIMED_EVENT = {
    "kind": "calendar#event",
    "id": "single001",
    "status": "confirmed",
    "summary": "One-off meeting",
    "start": {"dateTime": "2026-05-15T10:00:00+08:00", "timeZone": "Australia/Perth"},
    "end": {"dateTime": "2026-05-15T11:00:00+08:00", "timeZone": "Australia/Perth"},
}

SINGLE_ALLDAY_EVENT = {
    "kind": "calendar#event",
    "id": "allday001",
    "status": "confirmed",
    "summary": "Holiday",
    "start": {"date": "2026-05-25"},
    "end": {"date": "2026-05-26"},
}

RECURRING_MASTER_EVENT = {
    "kind": "calendar#event",
    "id": "abc123",
    "status": "confirmed",
    "summary": "Weekly planning",
    "start": {"dateTime": "2026-04-26T10:00:00+08:00", "timeZone": "Australia/Perth"},
    "end": {"dateTime": "2026-04-26T11:00:00+08:00", "timeZone": "Australia/Perth"},
    "recurrence": ["RRULE:FREQ=WEEKLY;COUNT=10"],
}

RECURRING_EXPANDED_INSTANCE = {
    "kind": "calendar#event",
    "id": "abc123_20260530T020000Z",
    "status": "confirmed",
    "summary": "Weekly planning",
    "recurringEventId": "abc123",
    "originalStartTime": {"dateTime": "2026-05-30T10:00:00+08:00", "timeZone": "Australia/Perth"},
    "start": {"dateTime": "2026-05-30T10:00:00+08:00", "timeZone": "Australia/Perth"},
    "end": {"dateTime": "2026-05-30T11:00:00+08:00", "timeZone": "Australia/Perth"},
}

RECURRING_MOVED_INSTANCE = {
    "kind": "calendar#event",
    "id": "abc123_20260530T020000Z",
    "status": "confirmed",
    "summary": "Weekly planning",
    "recurringEventId": "abc123",
    "originalStartTime": {"dateTime": "2026-05-30T10:00:00+08:00", "timeZone": "Australia/Perth"},
    # Moved to 2026-05-31
    "start": {"dateTime": "2026-05-31T14:00:00+08:00", "timeZone": "Australia/Perth"},
    "end": {"dateTime": "2026-05-31T15:00:00+08:00", "timeZone": "Australia/Perth"},
}

CANCELLED_EXCEPTION = {
    "kind": "calendar#event",
    "id": "abc123_20260530T020000Z",
    "status": "cancelled",
    "recurringEventId": "abc123",
    "originalStartTime": {"dateTime": "2026-05-30T10:00:00+08:00", "timeZone": "Australia/Perth"},
    # No start/end — cancelled exceptions may omit these
}

# Second instance of the same recurring series — different event ID, later date.
RECURRING_INSTANCE_JUN6 = {
    "kind": "calendar#event",
    "id": "abc123_20260606T020000Z",
    "status": "confirmed",
    "summary": "Weekly planning",
    "recurringEventId": "abc123",
    "originalStartTime": {"dateTime": "2026-06-06T10:00:00+08:00", "timeZone": "Australia/Perth"},
    "start": {"dateTime": "2026-06-06T10:00:00+08:00", "timeZone": "Australia/Perth"},
    "end": {"dateTime": "2026-06-06T11:00:00+08:00", "timeZone": "Australia/Perth"},
    "organizer": {"email": "cal@group.calendar.google.com"},
    "updated": "2026-05-01T00:00:00.000Z",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_google_service(api_items):
    """Build a GoogleService with a mocked Google API client."""
    mock_service = MagicMock()
    mock_service.events.return_value.list.return_value.execute.return_value = {"items": api_items}
    logger = MagicMock()

    with patch("gcal.gcal_service.build", return_value=mock_service):
        gs = GoogleService(MINIMAL_USER_SETTING, MagicMock(), logger)
    gs.service = mock_service
    gs.logger = logger
    return gs, mock_service, logger


def _make_notion_service():
    """Build a NotionService with a mocked Notion client."""
    logger = MagicMock()
    mock_client = MagicMock()
    with patch("notion.notion_service.Client", return_value=mock_client):
        ns = NotionService("fake-token", MINIMAL_USER_SETTING, logger)
    return ns


def _make_notion_task(gcal_event_id, last_edited_time="2026-04-01T00:00:00.000Z"):
    """Return a minimal Notion task dict whose GCal event ID matches gcal_event_id."""
    pp = MINIMAL_USER_SETTING["page_property"]
    return {
        "id": f"notion-page-{gcal_event_id}",
        "last_edited_time": last_edited_time,
        "properties": {
            pp["GCal_EventId_Notion_Name"]: {"rich_text": [{"plain_text": gcal_event_id}]},
            pp["GCal_Name_Notion_Name"]: {"select": {"name": "My Calendar"}},
            pp["Delete_Notion_Name"]: {"checkbox": False},
            pp["Task_Notion_Name"]: {"title": [{"plain_text": "Weekly planning"}]},
            pp["GCal_Sync_Time_Notion_Name"]: {"rich_text": []},
        },
    }


# ---------------------------------------------------------------------------
# Tests: events().list() call parameters
# ---------------------------------------------------------------------------


class TestGetGcalEventApiParams(unittest.TestCase):
    """Verify that the correct API parameters are passed to events().list()."""

    def test_single_events_true_and_order_by_start_time(self):
        gs, mock_service, _ = _make_google_service([SINGLE_TIMED_EVENT])
        gs.get_gcal_event()

        _, kwargs = mock_service.events.return_value.list.call_args
        self.assertTrue(kwargs.get("singleEvents"), "singleEvents must be True")
        self.assertEqual(kwargs.get("orderBy"), "startTime")

    def test_time_min_and_max_are_passed(self):
        gs, mock_service, _ = _make_google_service([])
        gs.get_gcal_event()

        _, kwargs = mock_service.events.return_value.list.call_args
        self.assertEqual(kwargs["timeMin"], MINIMAL_USER_SETTING["google_timemin"])
        self.assertEqual(kwargs["timeMax"], MINIMAL_USER_SETTING["google_timemax"])


# ---------------------------------------------------------------------------
# Tests: get_event_time — date extraction from GCal payloads
# ---------------------------------------------------------------------------


class TestGetEventTime(unittest.TestCase):
    """Verify that get_event_time returns the correct field for each event shape."""

    def setUp(self):
        self.ns = _make_notion_service()

    def test_single_timed_event_returns_datetime(self):
        result = self.ns.get_event_time(SINGLE_TIMED_EVENT, "start")
        self.assertEqual(result, "2026-05-15T10:00:00+08:00")

    def test_single_allday_event_returns_date(self):
        result = self.ns.get_event_time(SINGLE_ALLDAY_EVENT, "start")
        self.assertEqual(result, "2026-05-25")

    def test_recurring_expanded_instance_returns_start_not_original(self):
        # Expanded instance: start == originalStartTime in this case, but we
        # must read event["start"], not event["originalStartTime"].
        result = self.ns.get_event_time(RECURRING_EXPANDED_INSTANCE, "start")
        self.assertEqual(result, "2026-05-30T10:00:00+08:00")

    def test_recurring_moved_instance_uses_actual_start_not_original(self):
        # The instance was moved from 2026-05-30 to 2026-05-31.
        # We must use start.dateTime (2026-05-31), not originalStartTime (2026-05-30).
        result = self.ns.get_event_time(RECURRING_MOVED_INSTANCE, "start")
        self.assertEqual(result, "2026-05-31T14:00:00+08:00")
        # Confirm we are NOT accidentally using originalStartTime
        self.assertNotEqual(result, "2026-05-30T10:00:00+08:00")

    def test_missing_start_returns_none(self):
        event_no_start = {"id": "x", "summary": "broken"}
        result = self.ns.get_event_time(event_no_start, "start")
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# Tests: get_gcal_event — filtering behaviour
# ---------------------------------------------------------------------------


class TestGetGcalEventFiltering(unittest.TestCase):

    def test_normal_single_event_is_returned(self):
        gs, _, _ = _make_google_service([SINGLE_TIMED_EVENT])
        result = gs.get_gcal_event()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "single001")

    def test_allday_single_event_is_returned(self):
        gs, _, _ = _make_google_service([SINGLE_ALLDAY_EVENT])
        result = gs.get_gcal_event()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["start"]["date"], "2026-05-25")

    def test_recurring_expanded_instance_is_returned_with_correct_date(self):
        gs, _, _ = _make_google_service([RECURRING_EXPANDED_INSTANCE])
        result = gs.get_gcal_event()
        self.assertEqual(len(result), 1)
        # The occurrence date must be 2026-05-30, NOT the master's 2026-04-26
        self.assertEqual(result[0]["start"]["dateTime"], "2026-05-30T10:00:00+08:00")

    def test_recurring_master_event_not_returned_with_single_events(self):
        # With singleEvents=True the API never sends master events.
        # This test verifies that if (hypothetically) one appeared in the response,
        # our code would still surface it (it is not cancelled / has a start field).
        # The prevention is at the API call level (singleEvents=True), not by
        # post-filtering on the recurrence key.
        gs, _, _ = _make_google_service([RECURRING_MASTER_EVENT])
        result = gs.get_gcal_event()
        # Master event has a valid start → it passes the filters.
        # Real protection comes from singleEvents=True being set (see TestGetGcalEventApiParams).
        self.assertEqual(len(result), 1)

    def test_cancelled_recurring_exception_is_skipped(self):
        gs, _, logger = _make_google_service([CANCELLED_EXCEPTION])
        result = gs.get_gcal_event()
        self.assertEqual(result, [])
        # Confirm it was logged
        logger.debug.assert_called()
        debug_calls = " ".join(str(c) for c in logger.debug.call_args_list)
        self.assertIn("cancelled", debug_calls)

    def test_event_with_missing_start_is_skipped_with_warning(self):
        malformed = {"id": "bad001", "status": "confirmed", "summary": "No start"}
        gs, _, logger = _make_google_service([malformed])
        result = gs.get_gcal_event()
        self.assertEqual(result, [])
        logger.warning.assert_called()
        warning_calls = " ".join(str(c) for c in logger.warning.call_args_list)
        self.assertIn("missing start", warning_calls)

    def test_cancelled_and_valid_event_mixed(self):
        gs, _, _ = _make_google_service([CANCELLED_EXCEPTION, RECURRING_EXPANDED_INSTANCE])
        result = gs.get_gcal_event()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "abc123_20260530T020000Z")
        self.assertEqual(result[0]["start"]["dateTime"], "2026-05-30T10:00:00+08:00")

    def test_moved_instance_uses_start_not_original_start_time(self):
        gs, _, _ = _make_google_service([RECURRING_MOVED_INSTANCE])
        result = gs.get_gcal_event()
        self.assertEqual(len(result), 1)
        # The Notion task date will use result[0]["start"]["dateTime"]
        self.assertEqual(result[0]["start"]["dateTime"], "2026-05-31T14:00:00+08:00")
        # Sanity: originalStartTime is different (2026-05-30) and must NOT be used as the task date
        self.assertEqual(result[0]["originalStartTime"]["dateTime"], "2026-05-30T10:00:00+08:00")


# ---------------------------------------------------------------------------
# Tests: pagination — nextPageToken
# ---------------------------------------------------------------------------


class TestGetGcalEventPagination(unittest.TestCase):
    """Verify that get_gcal_event follows nextPageToken until exhausted."""

    def _make_paginated_service(self, pages):
        """
        Build a GoogleService whose events().list(**params).execute() returns
        pages[0], pages[1], … in sequence.

        Assigns execute.side_effect via return_value chains to avoid polluting
        list.call_args_list before the real code runs.
        """
        mock_service = MagicMock()
        # Wire up without calling .list() so call_args_list stays clean
        mock_service.events.return_value.list.return_value.execute.side_effect = pages
        logger = MagicMock()
        with patch("gcal.gcal_service.build", return_value=mock_service):
            gs = GoogleService(MINIMAL_USER_SETTING, MagicMock(), logger)
        gs.service = mock_service
        gs.logger = logger
        return gs, mock_service

    def test_single_page_no_token(self):
        gs, _ = self._make_paginated_service([{"items": [SINGLE_TIMED_EVENT]}])
        result = gs.get_gcal_event()
        self.assertEqual(len(result), 1)

    def test_two_pages_all_items_fetched(self):
        page1_event = {**SINGLE_TIMED_EVENT, "id": "evt001"}
        page2_event = {**SINGLE_TIMED_EVENT, "id": "evt002"}
        gs, mock_service = self._make_paginated_service(
            [
                {"items": [page1_event], "nextPageToken": "tok-page2"},
                {"items": [page2_event]},
            ]
        )
        result = gs.get_gcal_event()
        self.assertEqual(len(result), 2)
        ids = {e["id"] for e in result}
        self.assertEqual(ids, {"evt001", "evt002"})

    def test_second_page_request_includes_page_token(self):
        page1_event = {**SINGLE_TIMED_EVENT, "id": "evt001"}
        page2_event = {**SINGLE_TIMED_EVENT, "id": "evt002"}
        gs, mock_service = self._make_paginated_service(
            [
                {"items": [page1_event], "nextPageToken": "tok-page2"},
                {"items": [page2_event]},
            ]
        )
        gs.get_gcal_event()

        calls = mock_service.events.return_value.list.call_args_list
        # Two list() calls were made (one per page)
        self.assertEqual(len(calls), 2)
        first_kwargs = calls[0][1]
        second_kwargs = calls[1][1]
        self.assertNotIn("pageToken", first_kwargs)
        self.assertEqual(second_kwargs.get("pageToken"), "tok-page2")

    def test_three_pages_all_items_fetched(self):
        events = [{**SINGLE_TIMED_EVENT, "id": f"evt{i:03d}"} for i in range(6)]
        gs, _ = self._make_paginated_service(
            [
                {"items": events[0:2], "nextPageToken": "tok-2"},
                {"items": events[2:4], "nextPageToken": "tok-3"},
                {"items": events[4:6]},
            ]
        )
        result = gs.get_gcal_event()
        self.assertEqual(len(result), 6)

    def test_cancelled_events_filtered_across_pages(self):
        page1_event = {**SINGLE_TIMED_EVENT, "id": "good001"}
        gs, _ = self._make_paginated_service(
            [
                {"items": [CANCELLED_EXCEPTION], "nextPageToken": "tok-2"},
                {"items": [page1_event]},
            ]
        )
        result = gs.get_gcal_event()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "good001")

    def test_empty_response_returns_empty_list(self):
        gs, _ = self._make_paginated_service([{"items": []}])
        result = gs.get_gcal_event()
        self.assertEqual(result, [])

    def test_missing_items_key_returns_empty_list(self):
        gs, _ = self._make_paginated_service([{}])
        result = gs.get_gcal_event()
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# Tests: recurring-event identity in the sync engine
# ---------------------------------------------------------------------------


class TestRecurringEventIdentity(unittest.TestCase):
    """
    Each expanded GCal recurring instance is an independent event identified
    by its own instance ID.  recurringEventId must never be used as the sync
    key, and no extra Notion queries may be issued per recurring instance.
    """

    def _run_sync(self, gcal_events, notion_tasks=None):
        """Drive synchronize_notion_and_google_calendar and return (notion_service, result)."""
        import sync.sync as sync_module
        from sync.sync import synchronize_notion_and_google_calendar

        if notion_tasks is None:
            notion_tasks = []

        notion_service = MagicMock()
        google_service = MagicMock()
        notion_service.get_notion_task.return_value = ({}, notion_tasks)
        google_service.get_gcal_event.return_value = gcal_events

        for ev in gcal_events:
            ev.setdefault("organizer", {"email": "cal@group.calendar.google.com"})

        orig_logger = sync_module.logger
        sync_module.logger = MagicMock()
        try:
            result = synchronize_notion_and_google_calendar(
                user_setting={**MINIMAL_USER_SETTING},
                notion_service=notion_service,
                google_service=google_service,
                compare_time=True,
                should_update_notion_tasks=True,
                should_update_google_events=True,
            )
        finally:
            sync_module.logger = orig_logger
        return notion_service, result

    # --- date correctness ---

    def test_single_event_creates_task_with_correct_date(self):
        ns, result = self._run_sync([{**SINGLE_TIMED_EVENT}])
        ns.create_notion_task.assert_called_once()
        passed_event = ns.create_notion_task.call_args[0][0]
        self.assertEqual(passed_event["start"]["dateTime"], "2026-05-15T10:00:00+08:00")

    def test_recurring_expanded_instance_creates_task_with_occurrence_date(self):
        # Must use 2026-05-30, not the master's first-occurrence 2026-04-26.
        ns, _ = self._run_sync([{**RECURRING_EXPANDED_INSTANCE}])
        ns.create_notion_task.assert_called_once()
        passed_event = ns.create_notion_task.call_args[0][0]
        self.assertEqual(passed_event["start"]["dateTime"], "2026-05-30T10:00:00+08:00")

    def test_moved_recurring_instance_creates_task_with_actual_start_not_original(self):
        # Instance moved from 2026-05-30 to 2026-05-31; must use the rescheduled start.
        ns, _ = self._run_sync([{**RECURRING_MOVED_INSTANCE}])
        ns.create_notion_task.assert_called_once()
        passed_event = ns.create_notion_task.call_args[0][0]
        self.assertEqual(passed_event["start"]["dateTime"], "2026-05-31T14:00:00+08:00")
        self.assertNotEqual(passed_event["start"]["dateTime"], "2026-05-30T10:00:00+08:00")

    # --- identity: instance IDs, not master ID ---

    def test_two_instances_same_series_create_two_separate_tasks(self):
        # Two instances share recurringEventId "abc123" but have distinct instance IDs.
        # Each must become its own Notion task.
        ns, result = self._run_sync([{**RECURRING_EXPANDED_INSTANCE}, {**RECURRING_INSTANCE_JUN6}])
        self.assertEqual(ns.create_notion_task.call_count, 2)
        created_events = [c[0][0] for c in ns.create_notion_task.call_args_list]
        created_ids = {e["id"] for e in created_events}
        self.assertEqual(created_ids, {"abc123_20260530T020000Z", "abc123_20260606T020000Z"})

    def test_instance_matched_by_instance_id_not_master_id(self):
        # One Notion task already exists, keyed by the instance ID of the may-30 occurrence.
        # The may-30 GCal instance should trigger an update (not a create); the jun-6
        # instance has no match and should be created.
        may30_task = _make_notion_task(
            "abc123_20260530T020000Z",
            last_edited_time="2026-04-01T00:00:00.000Z",  # older than GCal updated below
        )
        # GCal may30 is newer → update_notion path
        may30_gcal = {
            **RECURRING_EXPANDED_INSTANCE,
            "organizer": {"email": "cal@group.calendar.google.com"},
            "updated": "2026-05-01T00:00:00.000Z",
        }
        jun6_gcal = {**RECURRING_INSTANCE_JUN6}

        ns, result = self._run_sync(
            gcal_events=[may30_gcal, jun6_gcal],
            notion_tasks=[may30_task],
        )
        # The matched may-30 instance → update_notion (GCal is newer)
        ns.update_notion_task.assert_called_once()
        updated_page_id = ns.update_notion_task.call_args[0][0]
        self.assertEqual(updated_page_id, may30_task["id"])
        # The unmatched jun-6 instance → create
        ns.create_notion_task.assert_called_once()
        created_event = ns.create_notion_task.call_args[0][0]
        self.assertEqual(created_event["id"], "abc123_20260606T020000Z")
        self.assertEqual(result["statusCode"], 200)

    # --- no N+1 queries ---

    def test_no_notion_query_per_recurring_instance(self):
        # get_notion_task_by_gcal_event_id must NOT be called for recurring instances
        # that arrive in the create_notion path — only event["id"] matching is used.
        ns, _ = self._run_sync([{**RECURRING_EXPANDED_INSTANCE}, {**RECURRING_INSTANCE_JUN6}])
        ns.get_notion_task_by_gcal_event_id.assert_not_called()

    def test_no_notion_query_for_non_recurring_event_either(self):
        ns, _ = self._run_sync([{**SINGLE_TIMED_EVENT}])
        ns.get_notion_task_by_gcal_event_id.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: per-calendar event limit (MAX_GCAL_EVENTS_PER_CALENDAR)
# ---------------------------------------------------------------------------


class TestGetGcalEventLimit(unittest.TestCase):
    """Verify the per-calendar event cap: exactly MAX events succeeds, MAX+1 raises."""

    def _make_n_events(self, n):
        return [{**SINGLE_TIMED_EVENT, "id": f"evt{i:04d}"} for i in range(n)]

    def _make_service_with_items(self, items):
        mock_service = MagicMock()
        mock_service.events.return_value.list.return_value.execute.return_value = {"items": items}
        logger = MagicMock()
        with patch("gcal.gcal_service.build", return_value=mock_service):
            gs = GoogleService(MINIMAL_USER_SETTING, MagicMock(), logger)
        gs.service = mock_service
        gs.logger = logger
        return gs

    def test_exactly_max_events_is_accepted(self):
        from gcal.gcal_service import MAX_GCAL_EVENTS_PER_CALENDAR

        gs = self._make_service_with_items(self._make_n_events(MAX_GCAL_EVENTS_PER_CALENDAR))
        result = gs.get_gcal_event()
        self.assertEqual(len(result), MAX_GCAL_EVENTS_PER_CALENDAR)

    def test_one_over_max_raises_runtime_error(self):
        from gcal.gcal_service import MAX_GCAL_EVENTS_PER_CALENDAR

        gs = self._make_service_with_items(self._make_n_events(MAX_GCAL_EVENTS_PER_CALENDAR + 1))
        with self.assertRaises(RuntimeError) as ctx:
            gs.get_gcal_event()
        self.assertIn(str(MAX_GCAL_EVENTS_PER_CALENDAR), str(ctx.exception))

    def test_over_limit_event_is_not_appended(self):
        from gcal.gcal_service import MAX_GCAL_EVENTS_PER_CALENDAR

        gs = self._make_service_with_items(self._make_n_events(MAX_GCAL_EVENTS_PER_CALENDAR + 1))
        with self.assertRaises(RuntimeError):
            gs.get_gcal_event()


class TestDeleteHandling(unittest.TestCase):
    def _make_delete_task(self):
        notion_task = _make_notion_task("abc123_20260530T020000Z")
        notion_task["properties"][MINIMAL_USER_SETTING["page_property"]["Delete_Notion_Name"]] = {"checkbox": True}
        return notion_task

    def test_delete_failure_preserves_notion_linkage_and_reports_error(self):
        from sync.sync import synchronize_notion_and_google_calendar

        notion_service = MagicMock()
        google_service = MagicMock()
        notion_task = self._make_delete_task()

        notion_service.get_notion_task.return_value = ({}, [notion_task])
        google_service.get_gcal_event.return_value = []
        google_service.delete_gcal_event.side_effect = RuntimeError("google delete failed")

        result = synchronize_notion_and_google_calendar(
            user_setting={**MINIMAL_USER_SETTING},
            notion_service=notion_service,
            google_service=google_service,
            compare_time=True,
            should_update_notion_tasks=True,
            should_update_google_events=True,
        )

        google_service.delete_gcal_event.assert_called_once_with(
            "cal@group.calendar.google.com",
            "abc123_20260530T020000Z",
        )
        notion_service.delete_notion_task.assert_not_called()
        notion_service.get_notion_task_by_gcal_event_id.assert_not_called()
        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(result["body"]["status"], "sync_success")
        self.assertEqual(len(result["body"]["message"]["errors"]), 1)
        error = result["body"]["message"]["errors"][0]
        self.assertEqual(error["action"], "delete_gcal")
        self.assertEqual(error["error_code"], "runtime_error")
        self.assertEqual(
            error["error_message"],
            "Sync failed. See Lambda logs with aws_request_id for details.",
        )
        self.assertTrue(error["retriable"])
        self.assertEqual(error["notion_task_id"], notion_task["id"])
        self.assertEqual(error["gcal_event_id"], "abc123_20260530T020000Z")


class TestDeleteGcalEventApiErrors(unittest.TestCase):
    def _make_service(self):
        mock_service = MagicMock()
        logger = MagicMock()
        with patch("gcal.gcal_service.build", return_value=mock_service):
            gs = GoogleService(MINIMAL_USER_SETTING, MagicMock(), logger)
        gs.service = mock_service
        gs.logger = logger
        return gs, mock_service, logger

    def test_404_is_treated_as_delete_converged(self):
        gs, mock_service, logger = self._make_service()

        class _Resp:
            status = 404
            reason = "Not Found"

        mock_service.events.return_value.delete.return_value.execute.side_effect = HttpError(
            _Resp(),
            b'{"error":{"message":"Not found"}}',
        )

        result = gs.delete_gcal_event("cal@group.calendar.google.com", "evt-404")

        self.assertTrue(result)
        logger.warning.assert_called_once()

    def test_non_404_delete_error_is_raised(self):
        gs, mock_service, logger = self._make_service()

        class _Resp:
            status = 403
            reason = "Forbidden"

        http_error = HttpError(_Resp(), b'{"error":{"message":"Forbidden"}}')
        mock_service.events.return_value.delete.return_value.execute.side_effect = http_error

        with self.assertRaises(HttpError):
            gs.delete_gcal_event("cal@group.calendar.google.com", "evt-403")

        logger.error.assert_called_once()


if __name__ == "__main__":
    unittest.main()
