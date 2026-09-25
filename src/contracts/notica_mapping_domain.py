"""Generated Notica mapping-domain contract adapter. Do not edit by hand."""

from urllib.parse import quote

MAPPING_DOMAIN_SCHEMA_VERSION = 1
PUBLIC_PROJECTION_SHA256 = "1567a118085ec48668409a786fba9efe0ee948a5f1b42ab270c4f204133f170a"
SOURCE_MAPPING_DOMAIN_SHA256 = "2c3bacf9f59c4d88509742b26f8d447ae656266736864e078f97130d834587c6"
CONFIG_LIFECYCLES = frozenset(
    (
        "active",
        "disabled",
    )
)
PARTITION_KEY_ATTRIBUTE = "pk"
SORT_KEY_ATTRIBUTE = "sk"
OWNER_PARTITION_KEY_PATTERN = "USER#{userUuid}"
NOTION_SETTINGS_SORT_KEY = "NOTION_SETTINGS"
TASK_SOURCE_SORT_KEY_PREFIX = "NOTION_TASK_SOURCE#"
CALENDAR_MAPPING_SORT_KEY_PREFIX = "CALENDAR_MAPPING#"
TASK_SOURCE_REQUIRED_FIELDS = frozenset(
    (
        "database",
        "defaults",
        "id",
        "lifecycle",
        "ownerUserUuid",
        "propertyMappings",
    )
)
CALENDAR_MAPPING_REQUIRED_FIELDS = frozenset(
    (
        "calendarId",
        "calendarName",
        "id",
        "lifecycle",
        "ownerUserUuid",
        "sourceId",
    )
)
NOTION_SETTINGS_REQUIRED_FIELDS = frozenset(
    (
        "ownerUserUuid",
        "timeCode",
        "timeZone",
    )
)


def _encode_component(value: str) -> str:
    return quote(value, safe="-_.!~*'()")


def owner_partition_key(user_uuid: str) -> str:
    return OWNER_PARTITION_KEY_PATTERN.replace(
        "{userUuid}", _encode_component(user_uuid)
    )


def task_source_sort_key(source_id: str) -> str:
    return f"{TASK_SOURCE_SORT_KEY_PREFIX}{_encode_component(source_id)}"


def calendar_mapping_sort_key(mapping_id: str) -> str:
    return f"{CALENDAR_MAPPING_SORT_KEY_PREFIX}{_encode_component(mapping_id)}"
