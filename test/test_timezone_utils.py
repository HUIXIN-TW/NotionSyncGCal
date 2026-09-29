import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))

from utils.timezone_utils import (  # noqa: E402
    InvalidTimeZoneError,
    format_datetime_in_timezone,
    format_local_midnight,
    local_date_at,
    resolve_timezone,
)


class TimezoneUtilsTests(unittest.TestCase):
    def test_perth_offset_is_stable_across_seasons(self):
        self.assertEqual(
            format_local_midnight(date(2026, 1, 15), "Australia/Perth"),
            "2026-01-15T00:00:00+08:00",
        )
        self.assertEqual(
            format_local_midnight(date(2026, 7, 15), "Australia/Perth"),
            "2026-07-15T00:00:00+08:00",
        )

    def test_new_york_offset_changes_by_date(self):
        self.assertEqual(
            format_local_midnight(date(2026, 1, 15), "America/New_York"),
            "2026-01-15T00:00:00-05:00",
        )
        self.assertEqual(
            format_local_midnight(date(2026, 7, 15), "America/New_York"),
            "2026-07-15T00:00:00-04:00",
        )

    def test_sydney_offset_changes_by_date(self):
        self.assertEqual(
            format_local_midnight(date(2026, 1, 15), "Australia/Sydney"),
            "2026-01-15T00:00:00+11:00",
        )
        self.assertEqual(
            format_local_midnight(date(2026, 7, 15), "Australia/Sydney"),
            "2026-07-15T00:00:00+10:00",
        )

    def test_local_date_uses_configured_timezone(self):
        instant = datetime(2026, 1, 1, 18, 30, tzinfo=timezone.utc)

        self.assertEqual(local_date_at("Australia/Perth", instant), date(2026, 1, 2))

    def test_aware_datetime_is_converted_to_configured_timezone(self):
        instant = datetime(2026, 7, 1, 16, 0, tzinfo=timezone.utc)

        self.assertEqual(
            format_datetime_in_timezone(instant, "America/New_York"),
            "2026-07-01T12:00:00-04:00",
        )

    def test_naive_datetime_is_interpreted_as_configured_local_wall_time(self):
        local_wall_time = datetime(2026, 7, 1, 12, 0)

        self.assertEqual(
            format_datetime_in_timezone(local_wall_time, "America/New_York"),
            "2026-07-01T12:00:00-04:00",
        )

    def test_invalid_timezone_fails_clearly(self):
        with self.assertRaisesRegex(InvalidTimeZoneError, "unknown IANA time zone"):
            resolve_timezone("Mars/Olympus_Mons")


if __name__ == "__main__":
    unittest.main()
