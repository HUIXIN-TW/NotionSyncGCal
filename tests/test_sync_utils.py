import os
import sys
import unittest

# Add the src directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from sync.sync import get_gcal_event_from_list # noqa: E402


class TestGetGcalEventFromList(unittest.TestCase):
    def test_empty_list_returns_none(self):
        result = get_gcal_event_from_list([], "nonexistent-id")
        self.assertIsNone(result)

    def test_event_found_in_list(self):
        event = {"id": "123", "summary": "My Event"}
        result = get_gcal_event_from_list([event], "123")
        self.assertEqual(result, event)


if __name__ == "__main__":
    unittest.main()
