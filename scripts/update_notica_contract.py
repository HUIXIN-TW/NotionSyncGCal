import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.generate_notica_mapping_contract import (  # noqa: E402
    ARTIFACT_PATH,
    EXPECTED_DISTRIBUTION_REPOSITORY,
    EXPECTED_MANIFEST_ASSET,
    EXPECTED_PRODUCER_REPOSITORY,
    EXPECTED_RELEASE_ASSET,
    LOCK_PATH,
    OUTPUT_PATH,
    SUPPORTED_SCHEMA_VERSION,
    build_output,
)

RELEASE_TAG_PATTERN = re.compile(r"^mapping-domain-v([0-9]+\.[0-9]+\.[0-9]+)$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
RELEASE_BASE_URL = (
    f"https://github.com/{EXPECTED_DISTRIBUTION_REPOSITORY}/releases/download"
)
TAG_BASE_URL = f"https://raw.githubusercontent.com/{EXPECTED_DISTRIBUTION_REPOSITORY}"


def _fetch_bytes(url):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "NotionSyncGCal-contract-updater"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def _load_json_bytes(content, label):
    try:
        value = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not valid UTF-8 JSON.") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object.")
    return value


def _sha256(content):
    return hashlib.sha256(content).hexdigest()


def _serialize_lock(lock):
    return json.dumps(lock, indent=2) + "\n"


def build_lock_from_release(release_tag, manifest_bytes, artifact_bytes):
    match = RELEASE_TAG_PATTERN.fullmatch(release_tag)
    if not match:
        raise ValueError("Release tag must use mapping-domain-vX.Y.Z form.")
    release_version = match.group(1)

    manifest = _load_json_bytes(manifest_bytes, "Release manifest")
    artifact = _load_json_bytes(artifact_bytes, "Release mapping-domain artifact")

    if manifest.get("artifactKind") != "notica-public-contract-release":
        raise ValueError("Unexpected public release manifest kind.")
    if manifest.get("releaseTag") != release_tag:
        raise ValueError("Release manifest tag does not match requested tag.")
    if manifest.get("releaseVersion") != release_version:
        raise ValueError("Release manifest version does not match requested tag.")
    if manifest.get("producerRepository") != EXPECTED_PRODUCER_REPOSITORY:
        raise ValueError("Release producer repository is not approved.")

    producer_commit = manifest.get("producerCommit")
    if not isinstance(producer_commit, str) or not COMMIT_PATTERN.fullmatch(
        producer_commit
    ):
        raise ValueError("Release producer commit is invalid.")

    modules = manifest.get("modules")
    if not isinstance(modules, dict) or set(modules) != {"mappingDomain"}:
        raise ValueError("Release manifest must contain only the mappingDomain module.")
    mapping_domain = modules["mappingDomain"]
    if not isinstance(mapping_domain, dict):
        raise ValueError("Release mappingDomain descriptor must be an object.")
    if mapping_domain.get("path") != "mapping-domain/v1.json":
        raise ValueError("Release mapping-domain path is not approved.")

    schema_version = mapping_domain.get("schemaVersion")
    if schema_version != SUPPORTED_SCHEMA_VERSION:
        raise ValueError("Release mapping-domain schema version is unsupported.")

    expected_digest = mapping_domain.get("sha256")
    source_digest = mapping_domain.get("sourceMappingDomainSha256")
    if not isinstance(expected_digest, str) or not SHA256_PATTERN.fullmatch(
        expected_digest
    ):
        raise ValueError("Release mapping-domain SHA-256 is invalid.")
    if not isinstance(source_digest, str) or not SHA256_PATTERN.fullmatch(
        source_digest
    ):
        raise ValueError("Release source mapping-domain SHA-256 is invalid.")

    actual_digest = _sha256(artifact_bytes)
    if actual_digest != expected_digest:
        raise ValueError("Downloaded mapping-domain artifact digest does not match manifest.")
    if artifact.get("schemaVersion") != schema_version:
        raise ValueError("Downloaded mapping-domain schema version does not match manifest.")
    if artifact.get("sourceArtifact", {}).get("sha256") != source_digest:
        raise ValueError("Downloaded mapping-domain source digest does not match manifest.")
    if artifact.get("artifactSetVersion") != manifest.get("artifactSetVersion"):
        raise ValueError("Downloaded mapping-domain artifact-set version does not match manifest.")

    artifact_set_version = manifest.get("artifactSetVersion")
    if not isinstance(artifact_set_version, str) or not artifact_set_version:
        raise ValueError("Release artifact-set version is invalid.")

    return {
        "distributionRepository": EXPECTED_DISTRIBUTION_REPOSITORY,
        "releaseTag": release_tag,
        "releaseVersion": release_version,
        "releaseAsset": EXPECTED_RELEASE_ASSET,
        "manifestAsset": EXPECTED_MANIFEST_ASSET,
        "artifactSetVersion": artifact_set_version,
        "schemaVersion": schema_version,
        "sha256": actual_digest,
        "sourceMappingDomainSha256": source_digest,
        "producerRepository": EXPECTED_PRODUCER_REPOSITORY,
        "producerCommit": producer_commit,
    }


def _run_contract_tests():
    env = os.environ.copy()
    src_path = str(ROOT / "src")
    current_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        f"{src_path}{os.pathsep}{current_pythonpath}"
        if current_pythonpath
        else src_path
    )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "test",
            "-p",
            "test_notica_mapping_domain_contract.py",
            "-v",
        ],
        cwd=ROOT,
        env=env,
        check=True,
    )


def update_contract(release_tag, fetch_bytes=_fetch_bytes, run_tests=True):
    tag_manifest_url = f"{TAG_BASE_URL}/{release_tag}/manifest.json"
    tag_artifact_url = f"{TAG_BASE_URL}/{release_tag}/mapping-domain/v1.json"
    release_manifest_url = (
        f"{RELEASE_BASE_URL}/{release_tag}/{EXPECTED_MANIFEST_ASSET}"
    )
    release_artifact_url = (
        f"{RELEASE_BASE_URL}/{release_tag}/{EXPECTED_RELEASE_ASSET}"
    )

    tag_manifest_bytes = fetch_bytes(tag_manifest_url)
    tag_artifact_bytes = fetch_bytes(tag_artifact_url)
    release_manifest_bytes = fetch_bytes(release_manifest_url)
    release_artifact_bytes = fetch_bytes(release_artifact_url)

    if release_manifest_bytes != tag_manifest_bytes:
        raise ValueError("Release manifest bytes differ from protected tag contents.")
    if release_artifact_bytes != tag_artifact_bytes:
        raise ValueError("Release artifact bytes differ from protected tag contents.")

    artifact_bytes = tag_artifact_bytes
    lock = build_lock_from_release(
        release_tag,
        tag_manifest_bytes,
        artifact_bytes,
    )
    lock_text = _serialize_lock(lock)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        artifact_path = tmp_root / "artifact.json"
        lock_path = tmp_root / "lock.json"
        artifact_path.write_bytes(artifact_bytes)
        lock_path.write_text(lock_text, encoding="utf-8")
        generated_adapter = build_output(artifact_path, lock_path)

    ARTIFACT_PATH.write_bytes(artifact_bytes)
    LOCK_PATH.write_text(lock_text, encoding="utf-8")
    OUTPUT_PATH.write_text(generated_adapter, encoding="utf-8")

    if run_tests:
        _run_contract_tests()

    return lock


def main():
    parser = argparse.ArgumentParser(
        description="Pin a published Notica mapping-domain release into the Worker."
    )
    parser.add_argument("release_tag")
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip the focused local compatibility test run.",
    )
    args = parser.parse_args()

    lock = update_contract(args.release_tag, run_tests=not args.skip_tests)
    print(
        "Pinned "
        f"{lock['distributionRepository']}@{lock['releaseTag']} "
        f"with SHA-256 {lock['sha256']}."
    )


if __name__ == "__main__":
    main()
