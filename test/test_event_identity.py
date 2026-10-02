import re
import sys
import unittest
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))

from gcal.event_identity import (  # noqa: E402
    build_google_private_metadata,
    deterministic_google_event_id,
)


class DeterministicGoogleEventIdentityTests(unittest.TestCase):
    def test_same_source_and_page_produce_same_id(self):
        first = deterministic_google_event_id("source-1", "page-1")
        second = deterministic_google_event_id("source-1", "page-1")
        self.assertEqual(first, second)

    def test_source_and_page_both_contribute_to_identity(self):
        base = deterministic_google_event_id("source-1", "page-1")
        self.assertNotEqual(base, deterministic_google_event_id("source-2", "page-1"))
        self.assertNotEqual(base, deterministic_google_event_id("source-1", "page-2"))

    def test_length_prefixed_framing_prevents_ambiguous_concatenation(self):
        self.assertNotEqual(
            deterministic_google_event_id("ab", "c"),
            deterministic_google_event_id("a", "bc"),
        )

    def test_event_id_matches_google_base32hex_constraints(self):
        event_id = deterministic_google_event_id(
            "source-1",
            "05482e3c-4aca-40e0-9527-9ff2f2630e66",
        )
        self.assertEqual(len(event_id), 52)
        self.assertRegex(event_id, re.compile(r"^[0-9a-v]{52}$"))

    def test_private_metadata_contains_only_routing_identity(self):
        metadata = build_google_private_metadata(
            "source-1",
            "mapping-1",
            7,
        )
        self.assertEqual(
            metadata,
            {
                "noticaSourceId": "source-1",
                "noticaMappingId": "mapping-1",
                "noticaMappingVersion": "7",
            },
        )
        serialized = repr(metadata).lower()
        self.assertNotIn("owner", serialized)
        self.assertNotIn("title", serialized)
        self.assertNotIn("token", serialized)


if __name__ == "__main__":
    unittest.main()
