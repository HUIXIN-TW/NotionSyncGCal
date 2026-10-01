import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))

from sync.mapping_write_fence import (  # noqa: E402
    MappingWriteFenceError,
    assert_current_google_write_route,
)


def setting():
    return {
        "mapping_domain_mode": "cloud",
        "owner_user_uuid": "user-1",
        "source_id": "source-1",
        "source_version": 3,
        "gcal_route_by_name": {
            "Learning": {
                "mapping_id": "mapping-1",
                "mapping_version": 7,
                "calendar_id": "learning@example.com",
            }
        },
    }


def current_source():
    return {
        "id": "source-1",
        "ownerUserUuid": "user-1",
        "lifecycle": "active",
        "version": 3,
    }


def current_mapping():
    return {
        "id": "mapping-1",
        "ownerUserUuid": "user-1",
        "sourceId": "source-1",
        "calendarId": "learning@example.com",
        "lifecycle": "active",
        "version": 7,
    }


class MappingWriteFenceTests(unittest.TestCase):
    def assert_blocked(self, expected_reason, source=None, mapping=None, *, calendar_id="learning@example.com"):
        source = current_source() if source is None else source
        mapping = current_mapping() if mapping is None else mapping

        with patch(
            "sync.mapping_write_fence.get_mapping_domain_task_source",
            return_value=source,
        ), patch(
            "sync.mapping_write_fence.get_mapping_domain_calendar_mapping",
            return_value=mapping,
        ):
            with self.assertRaises(MappingWriteFenceError) as raised:
                assert_current_google_write_route(
                    setting(),
                    "Learning",
                    calendar_id,
                )

        self.assertEqual(raised.exception.reason, expected_reason)

    def test_matching_current_route_is_allowed(self):
        with patch(
            "sync.mapping_write_fence.get_mapping_domain_task_source",
            return_value=current_source(),
        ) as get_source, patch(
            "sync.mapping_write_fence.get_mapping_domain_calendar_mapping",
            return_value=current_mapping(),
        ) as get_mapping:
            assert_current_google_write_route(
                setting(),
                "Learning",
                "learning@example.com",
            )

        get_source.assert_called_once_with("user-1", "source-1")
        get_mapping.assert_called_once_with("user-1", "mapping-1")

    def test_source_version_change_is_blocked(self):
        source = current_source()
        source["version"] = 4
        self.assert_blocked("source_version_changed", source=source)

    def test_mapping_version_change_is_blocked(self):
        mapping = current_mapping()
        mapping["version"] = 8
        self.assert_blocked("mapping_version_changed", mapping=mapping)

    def test_mapping_disable_is_blocked(self):
        mapping = current_mapping()
        mapping["lifecycle"] = "disabled"
        self.assert_blocked("mapping_inactive", mapping=mapping)

    def test_mapping_source_change_is_blocked(self):
        mapping = current_mapping()
        mapping["sourceId"] = "source-2"
        self.assert_blocked("mapping_source_changed", mapping=mapping)

    def test_mapping_owner_mismatch_is_blocked(self):
        mapping = current_mapping()
        mapping["ownerUserUuid"] = "user-2"
        self.assert_blocked("mapping_owner_mismatch", mapping=mapping)

    def test_target_change_is_blocked_before_reads(self):
        with patch(
            "sync.mapping_write_fence.get_mapping_domain_task_source"
        ) as get_source, patch(
            "sync.mapping_write_fence.get_mapping_domain_calendar_mapping"
        ) as get_mapping:
            with self.assertRaises(MappingWriteFenceError) as raised:
                assert_current_google_write_route(
                    setting(),
                    "Learning",
                    "other@example.com",
                )

        self.assertEqual(raised.exception.reason, "calendar_target_changed")
        get_source.assert_not_called()
        get_mapping.assert_not_called()

    def test_missing_mapping_is_blocked(self):
        with patch(
            "sync.mapping_write_fence.get_mapping_domain_task_source",
            return_value=current_source(),
        ), patch(
            "sync.mapping_write_fence.get_mapping_domain_calendar_mapping",
            side_effect=ValueError("missing"),
        ):
            with self.assertRaises(MappingWriteFenceError) as raised:
                assert_current_google_write_route(
                    setting(),
                    "Learning",
                    "learning@example.com",
                )

        self.assertEqual(raised.exception.reason, "mapping_missing")

    def test_local_mode_does_not_query_cloud_mapping_domain(self):
        local_setting = setting()
        local_setting["mapping_domain_mode"] = "local"

        with patch(
            "sync.mapping_write_fence.get_mapping_domain_task_source"
        ) as get_source, patch(
            "sync.mapping_write_fence.get_mapping_domain_calendar_mapping"
        ) as get_mapping:
            assert_current_google_write_route(
                local_setting,
                "Learning",
                "learning@example.com",
            )

        get_source.assert_not_called()
        get_mapping.assert_not_called()


if __name__ == "__main__":
    unittest.main()
