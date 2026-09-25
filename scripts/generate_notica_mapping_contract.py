import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_PATH = ROOT / "contracts" / "notica-mapping-domain-v1.json"
META_PATH = ROOT / "contracts" / "notica-mapping-domain-v1.meta.json"
OUTPUT_PATH = ROOT / "src" / "contracts" / "notica_mapping_domain.py"


def _load_json(path):
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def _artifact_sha256():
    return hashlib.sha256(ARTIFACT_PATH.read_bytes()).hexdigest()


def _tuple_literal(values):
    return repr(tuple(values))


def build_output():
    artifact = _load_json(ARTIFACT_PATH)
    meta = _load_json(META_PATH)
    digest = _artifact_sha256()

    if digest != meta["publicProjectionSha256"]:
        raise ValueError(
            "Pinned public mapping-domain artifact digest does not match metadata."
        )
    if artifact["schemaVersion"] != meta["schemaVersion"]:
        raise ValueError("Pinned mapping-domain schema version does not match metadata.")
    if (
        artifact["sourceArtifact"]["sha256"]
        != meta["sourceMappingDomainSha256"]
    ):
        raise ValueError(
            "Pinned public projection source digest does not match metadata."
        )

    storage = artifact["workerStorageRead"]
    domain = artifact["domain"]
    required = storage["requiredRecordFields"]

    lines = [
        '"""Generated Notica mapping-domain contract adapter. Do not edit by hand."""',
        "",
        "from urllib.parse import quote",
        "",
        f"MAPPING_DOMAIN_SCHEMA_VERSION = {artifact['schemaVersion']!r}",
        f"PUBLIC_PROJECTION_SHA256 = {digest!r}",
        f"SOURCE_MAPPING_DOMAIN_SHA256 = {artifact['sourceArtifact']['sha256']!r}",
        f"CONFIG_LIFECYCLES = frozenset({_tuple_literal(domain['lifecycleValues'])})",
        f"PARTITION_KEY_ATTRIBUTE = {storage['keyAttributes']['partitionKey']!r}",
        f"SORT_KEY_ATTRIBUTE = {storage['keyAttributes']['sortKey']!r}",
        f"OWNER_PARTITION_KEY_PATTERN = {storage['ownerPartitionKeyPattern']!r}",
        f"NOTION_SETTINGS_SORT_KEY = {storage['notionSettingsSortKey']!r}",
        f"TASK_SOURCE_SORT_KEY_PREFIX = {storage['taskSourceSortKeyPrefix']!r}",
        f"CALENDAR_MAPPING_SORT_KEY_PREFIX = {storage['calendarMappingSortKeyPrefix']!r}",
        f"TASK_SOURCE_REQUIRED_FIELDS = frozenset({_tuple_literal(required['taskSource'])})",
        f"CALENDAR_MAPPING_REQUIRED_FIELDS = frozenset({_tuple_literal(required['calendarMapping'])})",
        f"NOTION_SETTINGS_REQUIRED_FIELDS = frozenset({_tuple_literal(required['notionSettings'])})",
        "",
        "",
        "def _encode_component(value: str) -> str:",
        "    return quote(value, safe=\"-_.!~*'()\")",
        "",
        "",
        "def owner_partition_key(user_uuid: str) -> str:",
        "    return OWNER_PARTITION_KEY_PATTERN.replace(",
        '        "{userUuid}", _encode_component(user_uuid)',
        "    )",
        "",
        "",
        "def task_source_sort_key(source_id: str) -> str:",
        "    return f\"{TASK_SOURCE_SORT_KEY_PREFIX}{_encode_component(source_id)}\"",
        "",
        "",
        "def calendar_mapping_sort_key(mapping_id: str) -> str:",
        "    return f\"{CALENDAR_MAPPING_SORT_KEY_PREFIX}{_encode_component(mapping_id)}\"",
        "",
        "",
    ]
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
        print("Generated Notica mapping-domain adapter is current.")
        return

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(expected, encoding="utf-8")
    print(f"Generated {OUTPUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
