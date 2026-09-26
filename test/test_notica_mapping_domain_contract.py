import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from contracts.notica_mapping_domain import (
    CALENDAR_MAPPING_FIELD_SPECS,
    CALENDAR_MAPPING_REQUIRED_FIELDS,
    CALENDAR_MAPPING_SORT_KEY_PREFIX,
    CONFIG_LIFECYCLES,
    MAPPING_DOMAIN_SCHEMA_VERSION,
    NOTION_SETTINGS_FIELD_SPECS,
    NOTION_SETTINGS_REQUIRED_FIELDS,
    NOTION_SETTINGS_SORT_KEY,
    PARTITION_KEY_ATTRIBUTE,
    PUBLIC_PROJECTION_SHA256,
    SORT_KEY_ATTRIBUTE,
    SOURCE_MAPPING_DOMAIN_SHA256,
    TASK_SOURCE_DATABASE_FIELD_SPECS,
    TASK_SOURCE_DEFAULT_FIELD_SPECS,
    TASK_SOURCE_FIELD_SPECS,
    TASK_SOURCE_PROPERTY_MAPPING_FIELD_SPECS,
    TASK_SOURCE_REQUIRED_FIELDS,
    TASK_SOURCE_SEMANTIC_PROPERTY_SPECS,
    TASK_SOURCE_SORT_KEY_PREFIX,
    calendar_mapping_sort_key,
    owner_partition_key,
    task_source_sort_key,
)
from scripts.generate_notica_mapping_contract import build_output


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_PATH = ROOT / "contracts" / "notica-mapping-domain-v1.json"
META_PATH = ROOT / "contracts" / "notica-mapping-domain-v1.meta.json"


class NoticaMappingDomainContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifact_bytes = ARTIFACT_PATH.read_bytes()
        cls.artifact = json.loads(cls.artifact_bytes)
        cls.meta = json.loads(META_PATH.read_text(encoding="utf-8"))

    def test_pins_public_projection_identity(self):
        digest = hashlib.sha256(self.artifact_bytes).hexdigest()

        self.assertEqual(digest, PUBLIC_PROJECTION_SHA256)
        self.assertEqual(digest, self.meta["publicProjectionSha256"])
        self.assertEqual(
            self.artifact["sourceArtifact"]["sha256"],
            SOURCE_MAPPING_DOMAIN_SHA256,
        )
        self.assertEqual(
            SOURCE_MAPPING_DOMAIN_SHA256,
            self.meta["sourceMappingDomainSha256"],
        )
        self.assertEqual(
            self.artifact["schemaVersion"],
            MAPPING_DOMAIN_SCHEMA_VERSION,
        )

    def test_runtime_lifecycle_values_match_projection(self):
        self.assertEqual(
            CONFIG_LIFECYCLES,
            frozenset(self.artifact["domain"]["lifecycleValues"]),
        )

    def test_generated_logical_field_specs_match_projection(self):
        entities = self.artifact["domain"]["entities"]
        task_source = entities["taskSource"]

        def specs(fields):
            return {
                name: (definition["type"], definition["required"])
                for name, definition in fields.items()
            }

        self.assertEqual(TASK_SOURCE_FIELD_SPECS, specs(task_source["fields"]))
        self.assertEqual(
            TASK_SOURCE_DATABASE_FIELD_SPECS,
            specs(task_source["databaseFields"]),
        )
        self.assertEqual(
            TASK_SOURCE_DEFAULT_FIELD_SPECS,
            specs(task_source["defaultFields"]),
        )
        self.assertEqual(
            TASK_SOURCE_PROPERTY_MAPPING_FIELD_SPECS,
            specs(task_source["propertyMappingFields"]),
        )
        self.assertEqual(
            TASK_SOURCE_SEMANTIC_PROPERTY_SPECS,
            specs(task_source["semanticPropertyMappings"]),
        )
        self.assertEqual(
            CALENDAR_MAPPING_FIELD_SPECS,
            specs(entities["calendarMapping"]["fields"]),
        )
        self.assertEqual(
            NOTION_SETTINGS_FIELD_SPECS,
            specs(entities["notionSettings"]["fields"]),
        )

    def test_runtime_storage_read_contract_matches_projection(self):
        storage = self.artifact["workerStorageRead"]

        self.assertEqual(
            storage["keyAttributes"]["partitionKey"],
            PARTITION_KEY_ATTRIBUTE,
        )
        self.assertEqual(
            storage["keyAttributes"]["sortKey"],
            SORT_KEY_ATTRIBUTE,
        )
        self.assertEqual(storage["notionSettingsSortKey"], NOTION_SETTINGS_SORT_KEY)
        self.assertEqual(
            storage["taskSourceSortKeyPrefix"],
            TASK_SOURCE_SORT_KEY_PREFIX,
        )
        self.assertEqual(
            storage["calendarMappingSortKeyPrefix"],
            CALENDAR_MAPPING_SORT_KEY_PREFIX,
        )
        self.assertEqual(
            frozenset(storage["requiredRecordFields"]["taskSource"]),
            TASK_SOURCE_REQUIRED_FIELDS,
        )
        self.assertEqual(
            frozenset(storage["requiredRecordFields"]["calendarMapping"]),
            CALENDAR_MAPPING_REQUIRED_FIELDS,
        )
        self.assertEqual(
            frozenset(storage["requiredRecordFields"]["notionSettings"]),
            NOTION_SETTINGS_REQUIRED_FIELDS,
        )

    def test_metadata_pins_immutable_backend_merge_sha(self):
        self.assertEqual(
            self.meta["producerHead"],
            "5eaedc3c60e942d4f022616fa32fb9e7832cf4b7",
        )

    def test_generator_rejects_schema_drift_even_with_updated_public_digest(self):
        artifact = copy.deepcopy(self.artifact)
        artifact["schemaVersion"] = 2

        with tempfile.TemporaryDirectory() as tmp:
            artifact_path = Path(tmp) / "artifact.json"
            meta_path = Path(tmp) / "meta.json"
            artifact_path.write_text(
                json.dumps(artifact, separators=(",", ":")),
                encoding="utf-8",
            )
            meta = dict(self.meta)
            meta["publicProjectionSha256"] = hashlib.sha256(
                artifact_path.read_bytes()
            ).hexdigest()
            meta_path.write_text(json.dumps(meta), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "schema version"):
                build_output(artifact_path, meta_path)

    def test_generator_rejects_source_contract_drift(self):
        artifact = copy.deepcopy(self.artifact)
        artifact["sourceArtifact"]["sha256"] = "0" * 64

        with tempfile.TemporaryDirectory() as tmp:
            artifact_path = Path(tmp) / "artifact.json"
            meta_path = Path(tmp) / "meta.json"
            artifact_path.write_text(
                json.dumps(artifact, separators=(",", ":")),
                encoding="utf-8",
            )
            meta = dict(self.meta)
            meta["publicProjectionSha256"] = hashlib.sha256(
                artifact_path.read_bytes()
            ).hexdigest()
            meta_path.write_text(json.dumps(meta), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "source digest"):
                build_output(artifact_path, meta_path)

    def test_generated_key_builders_follow_backend_encoding_contract(self):
        self.assertEqual(owner_partition_key("user/1"), "USER#user%2F1")
        self.assertEqual(
            task_source_sort_key("source with space"),
            "NOTION_TASK_SOURCE#source%20with%20space",
        )
        self.assertEqual(
            calendar_mapping_sort_key("mapping/1"),
            "CALENDAR_MAPPING#mapping%2F1",
        )


if __name__ == "__main__":
    unittest.main()
