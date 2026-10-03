import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import update_notica_contract
from scripts.update_notica_contract import build_lock_from_release


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_PATH = ROOT / "contracts" / "notica-mapping-domain-v1.json"


class NoticaContractUpdateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifact_bytes = ARTIFACT_PATH.read_bytes()
        cls.artifact = json.loads(cls.artifact_bytes)
        cls.digest = hashlib.sha256(cls.artifact_bytes).hexdigest()
        cls.manifest = {
            "artifactKind": "notica-public-contract-release",
            "artifactSetVersion": cls.artifact["artifactSetVersion"],
            "modules": {
                "mappingDomain": {
                    "path": "mapping-domain/v1.json",
                    "schemaVersion": cls.artifact["schemaVersion"],
                    "sha256": cls.digest,
                    "sourceMappingDomainSha256": cls.artifact["sourceArtifact"]["sha256"],
                }
            },
            "producerCommit": "07951b9746609868a7559d6a883337dd8513356c",
            "producerRepository": "whatnow-studio/notica-backend",
            "releaseTag": "mapping-domain-v1.0.0",
            "releaseVersion": "1.0.0",
        }

    def manifest_bytes(self, **updates):
        manifest = json.loads(json.dumps(self.manifest))
        manifest.update(updates)
        return json.dumps(manifest).encode("utf-8")

    def test_builds_lock_from_verified_release(self):
        lock = build_lock_from_release(
            "mapping-domain-v1.0.0",
            self.manifest_bytes(),
            self.artifact_bytes,
        )

        self.assertEqual(
            lock["distributionRepository"],
            "whatnow-studio/notica-public-contracts",
        )
        self.assertEqual(lock["releaseTag"], "mapping-domain-v1.0.0")
        self.assertEqual(lock["releaseVersion"], "1.0.0")
        self.assertEqual(lock["sha256"], self.digest)
        self.assertEqual(
            lock["producerCommit"],
            "07951b9746609868a7559d6a883337dd8513356c",
        )

    def test_rejects_non_versioned_release_tag(self):
        with self.assertRaisesRegex(ValueError, "mapping-domain-vX.Y.Z"):
            build_lock_from_release(
                "latest",
                self.manifest_bytes(),
                self.artifact_bytes,
            )

    def test_rejects_manifest_tag_mismatch(self):
        with self.assertRaisesRegex(ValueError, "tag"):
            build_lock_from_release(
                "mapping-domain-v1.0.1",
                self.manifest_bytes(),
                self.artifact_bytes,
            )

    def test_rejects_unapproved_producer_repository(self):
        with self.assertRaisesRegex(ValueError, "producer repository"):
            build_lock_from_release(
                "mapping-domain-v1.0.0",
                self.manifest_bytes(producerRepository="example/backend"),
                self.artifact_bytes,
            )

    def test_rejects_artifact_digest_mismatch(self):
        changed = self.artifact_bytes + b"\n"

        with self.assertRaisesRegex(ValueError, "digest"):
            build_lock_from_release(
                "mapping-domain-v1.0.0",
                self.manifest_bytes(),
                changed,
            )

    def test_rejects_unsupported_schema(self):
        manifest = json.loads(self.manifest_bytes())
        manifest["modules"]["mappingDomain"]["schemaVersion"] = 2

        with self.assertRaisesRegex(ValueError, "unsupported"):
            build_lock_from_release(
                "mapping-domain-v1.0.0",
                json.dumps(manifest).encode("utf-8"),
                self.artifact_bytes,
            )

    def test_rejects_source_digest_mismatch(self):
        artifact = json.loads(self.artifact_bytes)
        artifact["sourceArtifact"]["sha256"] = "0" * 64
        artifact_bytes = json.dumps(artifact, separators=(",", ":")).encode("utf-8")
        manifest = json.loads(self.manifest_bytes())
        manifest["modules"]["mappingDomain"]["sha256"] = hashlib.sha256(
            artifact_bytes
        ).hexdigest()

        with self.assertRaisesRegex(ValueError, "source digest"):
            build_lock_from_release(
                "mapping-domain-v1.0.0",
                json.dumps(manifest).encode("utf-8"),
                artifact_bytes,
            )

    def test_update_contract_writes_verified_release_without_network(self):
        manifest_bytes = self.manifest_bytes()
        requested_urls = []

        def fetch_bytes(url):
            requested_urls.append(url)
            return (
                manifest_bytes
                if url.endswith("/manifest.json")
                else self.artifact_bytes
            )

        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            artifact_path = tmp_root / "artifact.json"
            lock_path = tmp_root / "lock.json"
            output_path = tmp_root / "adapter.py"

            with (
                patch.object(update_notica_contract, "ARTIFACT_PATH", artifact_path),
                patch.object(update_notica_contract, "LOCK_PATH", lock_path),
                patch.object(update_notica_contract, "OUTPUT_PATH", output_path),
            ):
                lock = update_notica_contract.update_contract(
                    "mapping-domain-v1.0.0",
                    fetch_bytes=fetch_bytes,
                    run_tests=False,
                )

            self.assertEqual(artifact_path.read_bytes(), self.artifact_bytes)
            self.assertEqual(
                json.loads(lock_path.read_text(encoding="utf-8")),
                lock,
            )
            generated = output_path.read_text(encoding="utf-8")
            self.assertIn(
                'PUBLIC_CONTRACT_RELEASE_TAG = "mapping-domain-v1.0.0"',
                generated,
            )
            self.assertEqual(
                requested_urls,
                [
                    (
                        "https://raw.githubusercontent.com/whatnow-studio/"
                        "notica-public-contracts/mapping-domain-v1.0.0/manifest.json"
                    ),
                    (
                        "https://raw.githubusercontent.com/whatnow-studio/"
                        "notica-public-contracts/mapping-domain-v1.0.0/"
                        "mapping-domain/v1.json"
                    ),
                    (
                        "https://github.com/whatnow-studio/notica-public-contracts/"
                        "releases/download/mapping-domain-v1.0.0/manifest.json"
                    ),
                    (
                        "https://github.com/whatnow-studio/notica-public-contracts/"
                        "releases/download/mapping-domain-v1.0.0/mapping-domain-v1.json"
                    ),
                ],
            )

    def test_update_contract_does_not_write_before_release_validation(self):
        bad_artifact = self.artifact_bytes + b"\n"

        def fetch_bytes(url):
            if url.endswith("/manifest.json"):
                return self.manifest_bytes()
            if "releases/download" in url:
                return bad_artifact
            return self.artifact_bytes

        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            artifact_path = tmp_root / "artifact.json"
            lock_path = tmp_root / "lock.json"
            output_path = tmp_root / "adapter.py"

            with (
                patch.object(update_notica_contract, "ARTIFACT_PATH", artifact_path),
                patch.object(update_notica_contract, "LOCK_PATH", lock_path),
                patch.object(update_notica_contract, "OUTPUT_PATH", output_path),
            ):
                with self.assertRaisesRegex(ValueError, "protected tag"):
                    update_notica_contract.update_contract(
                        "mapping-domain-v1.0.0",
                        fetch_bytes=fetch_bytes,
                        run_tests=False,
                    )

            self.assertFalse(artifact_path.exists())
            self.assertFalse(lock_path.exists())
            self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()
