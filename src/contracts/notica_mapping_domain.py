"""Generated Notica mapping-domain contract adapter. Do not edit by hand."""

from urllib.parse import quote

MAPPING_DOMAIN_SCHEMA_VERSION = 1
PUBLIC_PROJECTION_SHA256 = "d806144c1db5c5b726dacf18ce28b50ba3fbe415d998a15775bd4988b57fbe74"
SOURCE_MAPPING_DOMAIN_SHA256 = "e29f2d82eeb7d4ed440803ad8f6936963dcdc987ee26b06714f260a510d33a05"
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
        "updatedAtMs",
        "version",
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
        "updatedAtMs",
        "version",
    )
)
NOTION_SETTINGS_REQUIRED_FIELDS = frozenset(
    (
        "ownerUserUuid",
        "timeCode",
        "timeZone",
        "updatedAtMs",
        "version",
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
