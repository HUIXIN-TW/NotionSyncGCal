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
    PUBLIC_CONTRACT_DISTRIBUTION_REPOSITORY,
    PUBLIC_CONTRACT_PRODUCER_COMMIT,
    PUBLIC_CONTRACT_PRODUCER_REPOSITORY,
    PUBLIC_CONTRACT_RELEASE_TAG,
    PUBLIC_CONTRACT_RELEASE_VERSION,
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
LOCK_PATH = ROOT / "contracts" / "notica-mapping-domain.lock.json"


class NoticaMappingDomainContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifact_bytes = ARTIFACT_PATH.read_bytes()
        cls.artifact = json.loads(cls.artifact_bytes)
        cls.lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))

    def test_pins_public_release_identity(self):
        digest = hashlib.sha256(self.artifact_bytes).hexdigest()

        self.assertEqual(
            self.lock["distributionRepository"],
            "whatnow-studio/notica-public-contracts",
        )
        self.assertEqual(self.lock["releaseTag"], "mapping-domain-v1.0.0")
        self.assertEqual(self.lock["releaseVersion"], "1.0.0")
        self.assertEqual(self.lock["releaseAsset"], "mapping-domain-v1.json")
        self.assertEqual(self.lock["manifestAsset"], "manifest.json")
        self.assertEqual(
            self.lock["artifactSetVersion"],
            self.artifact["artifactSetVersion"],
        )
        self.assertEqual(digest, PUBLIC_PROJECTION_SHA256)
        self.assertEqual(digest, self.lock["sha256"])
        self.assertEqual(
            self.artifact["sourceArtifact"]["sha256"],
            SOURCE_MAPPING_DOMAIN_SHA256,
        )
        self.assertEqual(
            SOURCE_MAPPING_DOMAIN_SHA256,
            self.lock["sourceMappingDomainSha256"],
        )
        self.assertEqual(
            self.artifact["schemaVersion"],
            MAPPING_DOMAIN_SCHEMA_VERSION,
        )
        self.assertEqual(
            self.lock["schemaVersion"],
            MAPPING_DOMAIN_SCHEMA_VERSION,
        )

    def test_generated_provenance_matches_release_lock(self):
        self.assertEqual(
            PUBLIC_CONTRACT_DISTRIBUTION_REPOSITORY,
            self.lock["distributionRepository"],
        )
        self.assertEqual(PUBLIC_CONTRACT_RELEASE_TAG, self.lock["releaseTag"])
        self.assertEqual(PUBLIC_CONTRACT_RELEASE_VERSION, self.lock["releaseVersion"])
        self.assertEqual(
            PUBLIC_CONTRACT_PRODUCER_REPOSITORY,
            self.lock["producerRepository"],
        )
        self.assertEqual(
            PUBLIC_CONTRACT_PRODUCER_COMMIT,
            self.lock["producerCommit"],
        )

    def test_event_id_semantic_mapping_is_preserved(self):
        self.assertIn("googleCalendarEventId", TASK_SOURCE_SEMANTIC_PROPERTY_SPECS)
        self.assertEqual(
            TASK_SOURCE_SEMANTIC_PROPERTY_SPECS["googleCalendarEventId"],
            ("object", False),
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

    def _build_with(self, artifact, lock):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_path = Path(tmp) / "artifact.json"
            lock_path = Path(tmp) / "lock.json"
            artifact_path.write_text(
                json.dumps(artifact, separators=(",", ":")),
                encoding="utf-8",
            )
            lock = dict(lock)
            lock["sha256"] = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
            lock_path.write_text(json.dumps(lock), encoding="utf-8")
            return build_output(artifact_path, lock_path)

    def test_generator_rejects_schema_drift_even_with_updated_public_digest(self):
        artifact = copy.deepcopy(self.artifact)
        artifact["schemaVersion"] = 2
        lock = dict(self.lock)
        lock["schemaVersion"] = 2

        with self.assertRaisesRegex(ValueError, "unsupported"):
            self._build_with(artifact, lock)

    def test_generator_rejects_source_contract_drift(self):
        artifact = copy.deepcopy(self.artifact)
        artifact["sourceArtifact"]["sha256"] = "0" * 64

        with self.assertRaisesRegex(ValueError, "source digest"):
            self._build_with(artifact, self.lock)

    def test_generator_rejects_distribution_repository_drift(self):
        lock = dict(self.lock)
        lock["distributionRepository"] = "example/other-contracts"

        with self.assertRaisesRegex(ValueError, "distribution repository"):
            build_output(ARTIFACT_PATH, self._write_lock(lock))

    def test_generator_rejects_release_tag_version_drift(self):
        lock = dict(self.lock)
        lock["releaseTag"] = "mapping-domain-v9.9.9"

        with self.assertRaisesRegex(ValueError, "release tag"):
            build_output(ARTIFACT_PATH, self._write_lock(lock))

    def test_generator_rejects_invalid_producer_commit(self):
        lock = dict(self.lock)
        lock["producerCommit"] = "not-a-commit"

        with self.assertRaisesRegex(ValueError, "producer commit"):
            build_output(ARTIFACT_PATH, self._write_lock(lock))

    def _write_lock(self, lock):
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        json.dump(lock, tmp)
        tmp.close()
        return Path(tmp.name)

    def test_generator_rejects_storage_required_field_drift(self):
        artifact = copy.deepcopy(self.artifact)
        artifact["workerStorageRead"]["requiredRecordFields"]["taskSource"].remove(
            "defaults"
        )

        with self.assertRaisesRegex(
            ValueError,
            "storage-read required fields for taskSource",
        ):
            self._build_with(artifact, self.lock)

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
