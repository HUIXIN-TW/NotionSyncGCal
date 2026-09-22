import sys
import unittest
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))

from notion.notion_properties import (  # noqa: E402
    get_checkbox,
    get_rich_text,
    get_select,
    get_title,
)


class NotionPropertyIdTests(unittest.TestCase):
    def setUp(self):
        self.properties = {
            "Renamed Task": {
                "id": "task-id",
                "title": [{"plain_text": "Task value"}],
            },
            "Renamed Notes": {
                "id": "notes-id",
                "rich_text": [{"plain_text": "Notes value"}],
            },
            "Renamed Calendar": {
                "id": "calendar-id",
                "select": {"name": "Work"},
            },
            "Renamed Deleted": {"id": "deleted-id", "checkbox": True},
        }

    def test_reads_renamed_properties_by_stable_provider_id(self):
        self.assertEqual(get_title(self.properties, "task-id"), "Task value")
        self.assertEqual(get_rich_text(self.properties, "notes-id"), "Notes value")
        self.assertEqual(get_select(self.properties, "calendar-id"), "Work")
        self.assertTrue(get_checkbox(self.properties, "deleted-id"))

    def test_missing_optional_property_is_empty(self):
        self.assertIsNone(get_rich_text(self.properties, None))
        self.assertFalse(get_checkbox(self.properties, None))

    def test_does_not_fallback_to_mutable_property_name(self):
        properties = {
            "notes-id": {
                "rich_text": [{"plain_text": "Legacy fallback value"}],
            }
        }
        self.assertIsNone(get_rich_text(properties, "notes-id"))

    def test_provider_id_wins_when_mutable_name_shadows_it(self):
        properties = {
            "task-id": {
                "id": "different-id",
                "title": [{"plain_text": "Wrong property"}],
            },
            "Renamed Task": {
                "id": "task-id",
                "title": [{"plain_text": "Correct property"}],
            },
        }

        self.assertEqual(get_title(properties, "task-id"), "Correct property")


if __name__ == "__main__":
    unittest.main()
