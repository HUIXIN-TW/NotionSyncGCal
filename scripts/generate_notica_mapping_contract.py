import argparse
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_PATH = ROOT / "contracts" / "notica-mapping-domain-v1.json"
LOCK_PATH = ROOT / "contracts" / "notica-mapping-domain.lock.json"
OUTPUT_PATH = ROOT / "src" / "contracts" / "notica_mapping_domain.py"

EXPECTED_DISTRIBUTION_REPOSITORY = "whatnow-studio/notica-public-contracts"
EXPECTED_PRODUCER_REPOSITORY = "whatnow-studio/notica-backend"
EXPECTED_RELEASE_ASSET = "mapping-domain-v1.json"
EXPECTED_MANIFEST_ASSET = "manifest.json"
SUPPORTED_SCHEMA_VERSION = 1
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
RELEASE_VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


def _load_json(path):
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def _artifact_sha256(path=ARTIFACT_PATH):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _py_string(value):
    return json.dumps(value)


def _frozenset_assignment(name, values):
    lines = [f"{name} = frozenset(", "    ("]
    lines.extend(f"        {_py_string(value)}," for value in values)
    lines.extend(["    )", ")"])
    return lines


def _field_specs_assignment(name, fields):
    lines = [f"{name} = {{"]
    for field_name in sorted(fields):
        field = fields[field_name]
        field_type = field.get("type")
        required = field.get("required")
        if not isinstance(field_type, str) or not isinstance(required, bool):
            raise ValueError(f"Invalid field contract for {field_name}.")
        lines.append(
            f"    {_py_string(field_name)}: "
            f"({_py_string(field_type)}, {required}),"
        )
    lines.append("}")
    return lines


def _require_string(lock, key):
    value = lock.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Invalid contract lock field: {key}.")
    return value


def _validate_lock(lock, artifact, digest):
    distribution_repository = _require_string(lock, "distributionRepository")
    release_tag = _require_string(lock, "releaseTag")
    release_version = _require_string(lock, "releaseVersion")
    release_asset = _require_string(lock, "releaseAsset")
    manifest_asset = _require_string(lock, "manifestAsset")
    artifact_set_version = _require_string(lock, "artifactSetVersion")
    artifact_sha256 = _require_string(lock, "sha256")
    source_sha256 = _require_string(lock, "sourceMappingDomainSha256")
    producer_repository = _require_string(lock, "producerRepository")
    producer_commit = _require_string(lock, "producerCommit")

    if distribution_repository != EXPECTED_DISTRIBUTION_REPOSITORY:
        raise ValueError("Pinned distribution repository is not approved.")
    if producer_repository != EXPECTED_PRODUCER_REPOSITORY:
        raise ValueError("Pinned producer repository is not approved.")
    if release_asset != EXPECTED_RELEASE_ASSET:
        raise ValueError("Pinned release asset is not approved.")
    if manifest_asset != EXPECTED_MANIFEST_ASSET:
        raise ValueError("Pinned manifest asset is not approved.")
    if not RELEASE_VERSION_PATTERN.fullmatch(release_version):
        raise ValueError("Pinned release version must use exact x.y.z form.")
    if release_tag != f"mapping-domain-v{release_version}":
        raise ValueError("Pinned release tag does not match release version.")
    if artifact.get("artifactSetVersion") != artifact_set_version:
        raise ValueError("Pinned artifact-set version does not match artifact.")
    if not SHA256_PATTERN.fullmatch(artifact_sha256):
        raise ValueError("Pinned public artifact SHA-256 is invalid.")
    if not SHA256_PATTERN.fullmatch(source_sha256):
        raise ValueError("Pinned source mapping-domain SHA-256 is invalid.")
    if not COMMIT_PATTERN.fullmatch(producer_commit):
        raise ValueError("Pinned producer commit must be an exact 40-character SHA.")

    schema_version = lock.get("schemaVersion")
    if schema_version != SUPPORTED_SCHEMA_VERSION:
        raise ValueError("Pinned mapping-domain schema version is unsupported.")
    if artifact.get("schemaVersion") != schema_version:
        raise ValueError("Pinned mapping-domain schema version does not match artifact.")
    if digest != artifact_sha256:
        raise ValueError("Pinned public mapping-domain artifact digest does not match lock.")
    if artifact.get("sourceArtifact", {}).get("sha256") != source_sha256:
        raise ValueError("Pinned public projection source digest does not match lock.")


def build_output(artifact_path=ARTIFACT_PATH, lock_path=LOCK_PATH):
    artifact = _load_json(artifact_path)
    lock = _load_json(lock_path)
    digest = _artifact_sha256(artifact_path)
    _validate_lock(lock, artifact, digest)

    storage = artifact["workerStorageRead"]
    domain = artifact["domain"]
    entities = domain["entities"]
    task_source = entities["taskSource"]
    calendar_mapping = entities["calendarMapping"]
    notion_settings = entities["notionSettings"]
    required = storage["requiredRecordFields"]

    logical_required_fields = {
        "taskSource": {
            name
            for name, definition in task_source["fields"].items()
            if definition.get("required") is True
        },
        "calendarMapping": {
            name
            for name, definition in calendar_mapping["fields"].items()
            if definition.get("required") is True
        },
        "notionSettings": {
            name
            for name, definition in notion_settings["fields"].items()
            if definition.get("required") is True
        },
    }
    for entity_name, logical_fields in logical_required_fields.items():
        persisted_fields = required.get(entity_name)
        if not isinstance(persisted_fields, list) or not all(
            isinstance(field, str) for field in persisted_fields
        ):
            raise ValueError(
                f"Invalid Worker storage-read required fields for {entity_name}."
            )
        if len(persisted_fields) != len(set(persisted_fields)):
            raise ValueError(
                f"Duplicate Worker storage-read required fields for {entity_name}."
            )
        if set(persisted_fields) != logical_fields:
            raise ValueError(
                "Worker storage-read required fields for "
                f"{entity_name} must match required logical fields."
            )

    lines = [
        '"""Generated Notica mapping-domain contract adapter. Do not edit by hand."""',
        "",
        "from urllib.parse import quote",
        "",
        f"MAPPING_DOMAIN_SCHEMA_VERSION = {artifact['schemaVersion']}",
        f"PUBLIC_PROJECTION_SHA256 = {_py_string(digest)}",
        (
            "SOURCE_MAPPING_DOMAIN_SHA256 = "
            f"{_py_string(artifact['sourceArtifact']['sha256'])}"
        ),
        (
            "PUBLIC_CONTRACT_DISTRIBUTION_REPOSITORY = "
            f"{_py_string(lock['distributionRepository'])}"
        ),
        f"PUBLIC_CONTRACT_RELEASE_TAG = {_py_string(lock['releaseTag'])}",
        f"PUBLIC_CONTRACT_RELEASE_VERSION = {_py_string(lock['releaseVersion'])}",
        (
            "PUBLIC_CONTRACT_PRODUCER_REPOSITORY = "
            f"{_py_string(lock['producerRepository'])}"
        ),
        f"PUBLIC_CONTRACT_PRODUCER_COMMIT = {_py_string(lock['producerCommit'])}",
    ]
    lines.extend(
        _frozenset_assignment("CONFIG_LIFECYCLES", domain["lifecycleValues"])
    )
    lines.extend(
        _field_specs_assignment("TASK_SOURCE_FIELD_SPECS", task_source["fields"])
    )
    lines.extend(
        _field_specs_assignment(
            "TASK_SOURCE_DATABASE_FIELD_SPECS",
            task_source["databaseFields"],
        )
    )
    lines.extend(
        _field_specs_assignment(
            "TASK_SOURCE_DEFAULT_FIELD_SPECS",
            task_source["defaultFields"],
        )
    )
    lines.extend(
        _field_specs_assignment(
            "TASK_SOURCE_PROPERTY_MAPPING_FIELD_SPECS",
            task_source["propertyMappingFields"],
        )
    )
    lines.extend(
        _field_specs_assignment(
            "TASK_SOURCE_SEMANTIC_PROPERTY_SPECS",
            task_source["semanticPropertyMappings"],
        )
    )
    lines.extend(
        _field_specs_assignment(
            "CALENDAR_MAPPING_FIELD_SPECS",
            calendar_mapping["fields"],
        )
    )
    lines.extend(
        _field_specs_assignment(
            "NOTION_SETTINGS_FIELD_SPECS",
            notion_settings["fields"],
        )
    )
    lines.extend(
        [
            (
                "PARTITION_KEY_ATTRIBUTE = "
                f"{_py_string(storage['keyAttributes']['partitionKey'])}"
            ),
            (
                "SORT_KEY_ATTRIBUTE = "
                f"{_py_string(storage['keyAttributes']['sortKey'])}"
            ),
            (
                "OWNER_PARTITION_KEY_PATTERN = "
                f"{_py_string(storage['ownerPartitionKeyPattern'])}"
            ),
            (
                "NOTION_SETTINGS_SORT_KEY = "
                f"{_py_string(storage['notionSettingsSortKey'])}"
            ),
            (
                "TASK_SOURCE_SORT_KEY_PREFIX = "
                f"{_py_string(storage['taskSourceSortKeyPrefix'])}"
            ),
            (
                "CALENDAR_MAPPING_SORT_KEY_PREFIX = "
                f"{_py_string(storage['calendarMappingSortKeyPrefix'])}"
            ),
        ]
    )
    lines.extend(
        _frozenset_assignment(
            "TASK_SOURCE_REQUIRED_FIELDS", required["taskSource"]
        )
    )
    lines.extend(
        _frozenset_assignment(
            "CALENDAR_MAPPING_REQUIRED_FIELDS", required["calendarMapping"]
        )
    )
    lines.extend(
        _frozenset_assignment(
            "NOTION_SETTINGS_REQUIRED_FIELDS", required["notionSettings"]
        )
    )
    lines.extend(
        [
            "",
            "",
            "def _encode_component(value: str) -> str:",
            "    return quote(value, safe=\"-_.!~*'()\")",
            "",
            "",
            "def owner_partition_key(user_uuid: str) -> str:",
            '    return OWNER_PARTITION_KEY_PATTERN.replace("{userUuid}", _encode_component(user_uuid))',
            "",
            "",
            "def task_source_sort_key(source_id: str) -> str:",
            '    return f"{TASK_SOURCE_SORT_KEY_PREFIX}{_encode_component(source_id)}"',
            "",
            "",
            "def calendar_mapping_sort_key(mapping_id: str) -> str:",
            (
                '    return f"{CALENDAR_MAPPING_SORT_KEY_PREFIX}'
                '{_encode_component(mapping_id)}"'
            ),
            "",
        ]
    )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    expected = build_output()
    if args.check:
        actual = OUTPUT_PATH.read_text(encoding="utf-8") if OUTPUT_PATH.exists() else ""
        if actual != expected:
            raise SystemExit(
                "Generated Notica mapping-domain adapter is stale. "
                "Run python scripts/generate_notica_mapping_contract.py."
            )
        print("Pinned Notica release and generated mapping-domain adapter are current.")
        return

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(expected, encoding="utf-8")
    print(f"Generated {OUTPUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
