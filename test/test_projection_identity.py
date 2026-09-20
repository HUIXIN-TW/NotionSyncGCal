import sys
import unittest
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))

from sync.projection_identity import (  # noqa: E402
    ProjectionIdentityError,
    assert_projection_ownership,
    build_projection_identity,
)


BASE_SETTING = {
    "owner_user_uuid": "11111111-1111-4111-8111-111111111111",
    "source_id": "source-1",
    "mapping_id": "mapping-1",
    "calendar_id": "calendar@example.com",
}
TASK_ID = "22222222-2222-4222-8222-222222222222"


class ProjectionIdentityTests(unittest.TestCase):
    def test_identity_is_deterministic_and_google_event_id_safe(self):
        first = build_projection_identity(dict(BASE_SETTING), TASK_ID)
        second = build_projection_identity(dict(BASE_SETTING), TASK_ID)

        self.assertEqual(first, second)
        self.assertRegex(first["event_id"], r"^[0-9a-v]{5,1024}$")

    def test_hyphenated_and_compact_notion_ids_are_same_identity(self):
        hyphenated = build_projection_identity(dict(BASE_SETTING), TASK_ID)
        compact = build_projection_identity(
            dict(BASE_SETTING),
            TASK_ID.replace("-", ""),
        )

        self.assertEqual(hyphenated["event_id"], compact["event_id"])
        self.assertEqual(hyphenated["task_id"], compact["task_id"])

    def test_each_materialization_dimension_changes_event_identity(self):
        base = build_projection_identity(dict(BASE_SETTING), TASK_ID)["event_id"]

        variants = []
        for key, value in (
            ("owner_user_uuid", "33333333-3333-4333-8333-333333333333"),
            ("source_id", "source-2"),
            ("mapping_id", "mapping-2"),
            ("calendar_id", "other@example.com"),
        ):
            setting = dict(BASE_SETTING)
            setting[key] = value
            variants.append(build_projection_identity(setting, TASK_ID)["event_id"])
        variants.append(
            build_projection_identity(
                dict(BASE_SETTING),
                "44444444-4444-4444-8444-444444444444",
            )["event_id"]
        )

        self.assertNotIn(base, variants)
        self.assertEqual(len(set(variants)), len(variants))

    def test_private_metadata_does_not_expose_raw_owner_or_calendar(self):
        projection = build_projection_identity(dict(BASE_SETTING), TASK_ID)
        values = set(projection["private"].values())

        self.assertNotIn(BASE_SETTING["owner_user_uuid"], values)
        self.assertNotIn(BASE_SETTING["calendar_id"], values)
        self.assertEqual(projection["private"]["noticaSource"], "source-1")
        self.assertEqual(projection["private"]["noticaMapping"], "mapping-1")

    def test_invalid_notion_task_identity_fails_closed(self):
        with self.assertRaises(ProjectionIdentityError):
            build_projection_identity(dict(BASE_SETTING), "not-a-page-uuid")

    def test_ownership_requires_exact_event_and_private_metadata(self):
        projection = build_projection_identity(dict(BASE_SETTING), TASK_ID)
        event = {
            "id": projection["event_id"],
            "extendedProperties": {"private": dict(projection["private"])},
        }

        assert_projection_ownership(event, projection)

        bad = {
            **event,
            "extendedProperties": {
                "private": {
                    **projection["private"],
                    "noticaMapping": "other-mapping",
                }
            },
        }
        with self.assertRaises(ProjectionIdentityError):
            assert_projection_ownership(bad, projection)


if __name__ == "__main__":
    unittest.main()
