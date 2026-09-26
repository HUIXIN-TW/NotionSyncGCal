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


def build_output(artifact_path=ARTIFACT_PATH, meta_path=META_PATH):
    artifact = _load_json(artifact_path)
    meta = _load_json(meta_path)
    digest = _artifact_sha256(artifact_path)

    if digest != meta["publicProjectionSha256"]:
        raise ValueError(
            "Pinned public mapping-domain artifact digest does not match metadata."
        )
    if artifact["schemaVersion"] != meta["schemaVersion"]:
        raise ValueError("Pinned mapping-domain schema version does not match metadata.")
    if artifact["sourceArtifact"]["sha256"] != meta["sourceMappingDomainSha256"]:
        raise ValueError(
            "Pinned public projection source digest does not match metadata."
        )

    storage = artifact["workerStorageRead"]
    domain = artifact["domain"]
    entities = domain["entities"]
    task_source = entities["taskSource"]
    calendar_mapping = entities["calendarMapping"]
    notion_settings = entities["notionSettings"]
    required = storage["requiredRecordFields"]

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
            "    return OWNER_PARTITION_KEY_PATTERN.replace(",
            '        "{userUuid}", _encode_component(user_uuid)',
            "    )",
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
        print("Generated Notica mapping-domain adapter is current.")
        return

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(expected, encoding="utf-8")
    print(f"Generated {OUTPUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
