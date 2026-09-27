import json
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal

from contracts.notica_mapping_domain import (
    CALENDAR_MAPPING_FIELD_SPECS,
    CONFIG_LIFECYCLES,
    NOTION_SETTINGS_FIELD_SPECS,
    TASK_SOURCE_DATABASE_FIELD_SPECS,
    TASK_SOURCE_DEFAULT_FIELD_SPECS,
    TASK_SOURCE_FIELD_SPECS,
    TASK_SOURCE_PROPERTY_MAPPING_FIELD_SPECS,
    TASK_SOURCE_SEMANTIC_PROPERTY_SPECS,
)


TASK_PROPERTY_POLICY = {
    "task": ("Task_Notion_Name", "title"),
    "date": ("Date_Notion_Name", "date"),
    "initiative": ("Initiative_Notion_Name", "multi_select"),
    "status": ("Status_Notion_Name", "status"),
    "location": ("Location_Notion_Name", "place"),
    "extraInfo": ("ExtraInfo_Notion_Name", "rich_text"),
    "sprint": ("Sprint_Notion_Name", "select"),
    "calendarName": ("GCal_Name_Notion_Name", "select"),
    "googleCalendarEndDate": ("GCal_End_Date_Notion_Name", "formula"),
    "googleCalendarDeleted": ("Delete_Notion_Name", "checkbox"),
    "googleCalendarEventId": ("GCal_EventId_Notion_Name", "rich_text"),
    "googleCalendarSyncTime": ("GCal_Sync_Time_Notion_Name", "rich_text"),
    "googleCalendarIcon": ("CompleteIcon_Notion_Name", "formula"),
}

SYNC_REQUIRED_PROPERTIES = frozenset(
    {
        "task",
        "date",
        "calendarName",
        "location",
        "extraInfo",
        "googleCalendarEndDate",
        "googleCalendarDeleted",
        "googleCalendarEventId",
        "googleCalendarSyncTime",
        "googleCalendarIcon",
    }
)


class SettingError(Exception):
    """Raised when mapping-domain configuration cannot reproduce worker settings safely."""


def _require_dict(value, label):
    if not isinstance(value, dict):
        raise SettingError(f"{label} must be an object.")
    return value


def _require_list(value, label):
    if not isinstance(value, list):
        raise SettingError(f"{label} must be an array.")
    return value


def _require_string(value, label):
    if not isinstance(value, str) or not value.strip():
        raise SettingError(f"{label} must be a non-empty string.")
    return value.strip()


def _require_int(value, label, *, minimum=None, maximum=None):
    if isinstance(value, bool):
        raise SettingError(f"{label} must be an integer.")
    if isinstance(value, Decimal):
        if value != value.to_integral_value():
            raise SettingError(f"{label} must be an integer.")
        value = int(value)
    elif not isinstance(value, int):
        raise SettingError(f"{label} must be an integer.")

    if minimum is not None and value < minimum:
        raise SettingError(f"{label} must be at least {minimum}.")
    if maximum is not None and value > maximum:
        raise SettingError(f"{label} must be at most {maximum}.")
    return value


def _validate_contract_value(value, expected_type, label):
    if expected_type == "string":
        valid = isinstance(value, str)
    elif expected_type == "object":
        valid = isinstance(value, dict)
    elif expected_type == "number":
        valid = not isinstance(value, bool) and isinstance(value, (int, float, Decimal))
    else:
        raise SettingError(f"{label} uses unsupported contract type '{expected_type}'.")

    if not valid:
        raise SettingError(f"{label} must match contract type {expected_type}.")


def _validate_contract_fields(record, field_specs, label):
    for field_name, (expected_type, required) in field_specs.items():
        field_label = f"{label}.{field_name}"
        if field_name not in record:
            if required:
                raise SettingError(f"{field_label} is required by the mapping-domain contract.")
            continue
        _validate_contract_value(record[field_name], expected_type, field_label)


def _validate_task_source_contract(source, label):
    _validate_contract_fields(source, TASK_SOURCE_FIELD_SPECS, label)

    database = _require_dict(source.get("database"), f"{label}.database")
    _validate_contract_fields(
        database,
        TASK_SOURCE_DATABASE_FIELD_SPECS,
        f"{label}.database",
    )

    defaults = _require_dict(source.get("defaults"), f"{label}.defaults")
    _validate_contract_fields(
        defaults,
        TASK_SOURCE_DEFAULT_FIELD_SPECS,
        f"{label}.defaults",
    )

    property_mappings = _require_dict(
        source.get("propertyMappings"),
        f"{label}.propertyMappings",
    )
    for semantic_key, (expected_type, required) in TASK_SOURCE_SEMANTIC_PROPERTY_SPECS.items():
        mapping_label = f"{label}.propertyMappings.{semantic_key}"
        if semantic_key not in property_mappings:
            if required:
                raise SettingError(
                    f"{mapping_label} is required by the mapping-domain contract."
                )
            continue

        raw_mapping = property_mappings[semantic_key]
        _validate_contract_value(raw_mapping, expected_type, mapping_label)
        mapping = _require_dict(raw_mapping, mapping_label)
        _validate_contract_fields(
            mapping,
            TASK_SOURCE_PROPERTY_MAPPING_FIELD_SPECS,
            mapping_label,
        )


def _validate_owner(record, owner_user_uuid, label):
    owner = _require_string(record.get("ownerUserUuid"), f"{label}.ownerUserUuid")
    if owner != owner_user_uuid:
        raise SettingError(f"{label} does not belong to the requested owner.")


def apply_date_range(setting, goback_days, goforward_days):
    """Preserve the existing worker date-window calculation."""
    today = date.today()
    goback_days = _require_int(goback_days, "goBackDays", minimum=0)
    goforward_days = _require_int(goforward_days, "goForwardDays", minimum=0)
    timecode = _require_string(setting.get("timecode"), "timecode")

    setting["goback_days"] = goback_days
    setting["goforward_days"] = goforward_days
    setting["after_date"] = (today + timedelta(days=-goback_days)).strftime("%Y-%m-%d")
    setting["before_date"] = (today + timedelta(days=goforward_days)).strftime("%Y-%m-%d")
    setting["google_timemin"] = (today + timedelta(days=-goback_days)).strftime(f"%Y-%m-%dT%H:%M:%S{timecode}")
    setting["google_timemax"] = (today + timedelta(days=goforward_days)).strftime(f"%Y-%m-%dT%H:%M:%S{timecode}")
    return setting


class MappingDomainConfig:
    """Load normalized mapping-domain rows into the worker runtime setting."""

    def __init__(self, config, logger):
        self.config = _require_dict(config, "configuration")
        self.logger = logger
        self.mode = config.get("mode")
        self.owner_user_uuid = config.get("uuid") if self.mode == "cloud" else "local-user"
        self.source_settings = self._format_contract(self._load_contract())

    def _load_contract(self):
        if self.mode == "cloud":
            from utils.dynamodb_utils import (
                get_mapping_domain_settings,
                list_mapping_domain_calendar_mappings_for_owner,
                list_mapping_domain_task_sources,
            )

            owner = _require_string(self.config.get("uuid"), "uuid")
            return {
                "settings": get_mapping_domain_settings(owner),
                "taskSources": list_mapping_domain_task_sources(owner),
                "calendarMappings": list_mapping_domain_calendar_mappings_for_owner(owner),
            }

        if self.mode == "local":
            path = self.config.get("mapping_domain_config_path")
            try:
                with open(path, encoding="utf-8") as file:
                    return json.load(file)
            except FileNotFoundError as exc:
                raise SettingError(f"Local mapping-domain config file not found: {path}") from exc
            except json.JSONDecodeError as exc:
                raise SettingError(f"Local mapping-domain config file is not valid JSON: {exc}") from exc

        raise SettingError(f"Unknown config mode '{self.mode}'. Expected 'cloud' or 'local'.")

    def _format_contract(self, contract):
        contract = _require_dict(contract, "mapping-domain configuration")
        settings = _require_dict(contract.get("settings"), "settings")
        sources = _require_list(contract.get("taskSources"), "taskSources")
        mappings = _require_list(contract.get("calendarMappings"), "calendarMappings")
        owner = self.owner_user_uuid

        _validate_contract_fields(settings, NOTION_SETTINGS_FIELD_SPECS, "settings")
        _validate_owner(settings, owner, "settings")
        timezone = _require_string(settings.get("timeZone"), "settings.timeZone")
        timecode = _require_string(settings.get("timeCode"), "settings.timeCode")

        validated_sources = {}
        for raw_source in sources:
            source = _require_dict(raw_source, "taskSource")
            _validate_task_source_contract(source, "taskSource")
            _validate_owner(source, owner, "taskSource")
            source_id = _require_string(source.get("id"), "taskSource.id")
            if source_id in validated_sources:
                raise SettingError(f"Duplicate Task source id: {source_id}")
            lifecycle = _require_string(source.get("lifecycle"), f"taskSource[{source_id}].lifecycle")
            if lifecycle not in CONFIG_LIFECYCLES:
                raise SettingError(f"taskSource[{source_id}].lifecycle must be active or disabled.")
            source["id"] = source_id
            source["lifecycle"] = lifecycle
            validated_sources[source_id] = source

        mappings_by_source = {source_id: [] for source_id in validated_sources}
        seen_mapping_ids = set()
        for raw_mapping in mappings:
            mapping = _require_dict(raw_mapping, "calendarMapping")
            _validate_contract_fields(
                mapping,
                CALENDAR_MAPPING_FIELD_SPECS,
                "calendarMapping",
            )
            _validate_owner(mapping, owner, "calendarMapping")
            mapping_id = _require_string(mapping.get("id"), "calendarMapping.id")
            if mapping_id in seen_mapping_ids:
                raise SettingError(f"Duplicate Calendar mapping id: {mapping_id}")
            seen_mapping_ids.add(mapping_id)
            source_id = _require_string(mapping.get("sourceId"), f"calendarMapping[{mapping_id}].sourceId")
            if source_id not in validated_sources:
                raise SettingError(f"Calendar mapping {mapping_id} references unknown Task source {source_id}.")
            lifecycle = _require_string(mapping.get("lifecycle"), f"calendarMapping[{mapping_id}].lifecycle")
            if lifecycle not in CONFIG_LIFECYCLES:
                raise SettingError(f"calendarMapping[{mapping_id}].lifecycle must be active or disabled.")
            mapping["id"] = mapping_id
            mapping["sourceId"] = source_id
            mapping["calendarName"] = _require_string(
                mapping.get("calendarName"),
                f"calendarMapping[{mapping_id}].calendarName",
            )
            mapping["calendarId"] = _require_string(
                mapping.get("calendarId"),
                f"calendarMapping[{mapping_id}].calendarId",
            )
            mapping["lifecycle"] = lifecycle
            mappings_by_source[source_id].append(mapping)

        active_source_settings = []
        for source_id, source in validated_sources.items():
            if source["lifecycle"] != "active":
                continue
            active_mappings = [mapping for mapping in mappings_by_source[source_id] if mapping["lifecycle"] == "active"]
            if not active_mappings:
                raise SettingError(f"Task source {source_id} requires at least one active Calendar mapping.")
            active_source_settings.append(
                self._to_source_setting(
                    source,
                    active_mappings,
                    timezone,
                    timecode,
                )
            )

        if not active_source_settings:
            raise SettingError("No active Task source was found.")
        return active_source_settings

    def _to_source_setting(self, source, mappings, timezone, timecode):
        source_id = source["id"]
        database = _require_dict(source.get("database"), f"taskSource[{source_id}].database")
        defaults = _require_dict(source.get("defaults"), f"taskSource[{source_id}].defaults")
        property_mappings = _require_dict(
            source.get("propertyMappings"),
            f"taskSource[{source_id}].propertyMappings",
        )

        missing = sorted(SYNC_REQUIRED_PROPERTIES - property_mappings.keys())
        if missing:
            raise SettingError(f"Task source {source_id} is missing worker-required property mappings: {missing}")

        page_property = {}
        for semantic_key, raw_mapping in property_mappings.items():
            policy = TASK_PROPERTY_POLICY.get(semantic_key)
            if not policy:
                continue
            runtime_key, expected_type = policy
            property_mapping = _require_dict(raw_mapping, f"propertyMappings.{semantic_key}")
            property_type = _require_string(
                property_mapping.get("propertyType"),
                f"propertyMappings.{semantic_key}.propertyType",
            )
            if property_type != expected_type:
                raise SettingError(f"propertyMappings.{semantic_key} must be {expected_type}, got {property_type}.")
            page_property[runtime_key] = _require_string(
                property_mapping.get("propertyId"),
                f"propertyMappings.{semantic_key}.propertyId",
            )

        calendar_by_name = {}
        for mapping in mappings:
            calendar_name = _require_string(mapping.get("calendarName"), "calendarMapping.calendarName")
            if calendar_name in calendar_by_name:
                raise SettingError(f"Duplicate Calendar name for Task source {source_id}: {calendar_name}")
            calendar_by_name[calendar_name] = _require_string(mapping.get("calendarId"), "calendarMapping.calendarId")

        default_calendar_name = _require_string(
            defaults.get("defaultCalendarName"),
            f"taskSource[{source_id}].defaults.defaultCalendarName",
        )
        if default_calendar_name not in calendar_by_name:
            raise SettingError(
                f"Task source {source_id} defaultCalendarName does not match an active Calendar mapping."
            )

        ordered_calendar_names = [default_calendar_name] + sorted(
            name for name in calendar_by_name if name != default_calendar_name
        )
        gcal_name_dict = {name: calendar_by_name[name] for name in ordered_calendar_names}
        gcal_id_dict = {calendar_id: calendar_name for calendar_name, calendar_id in gcal_name_dict.items()}

        setting = {
            "owner_user_uuid": self.owner_user_uuid,
            "source_id": source_id,
            "database_id": _require_string(
                database.get("externalId"),
                "taskSource.database.externalId",
            ),
            "timezone": timezone,
            "timecode": timecode,
            "default_event_length": _require_int(
                defaults.get("defaultEventLengthMinutes"),
                "taskSource.defaults.defaultEventLengthMinutes",
                minimum=1,
            ),
            "default_start_time": _require_int(
                defaults.get("defaultStartHour"),
                "taskSource.defaults.defaultStartHour",
                minimum=0,
                maximum=23,
            ),
            "page_property": page_property,
            "gcal_name_dict": gcal_name_dict,
            "gcal_id_dict": gcal_id_dict,
            "gcal_default_name": default_calendar_name,
            "gcal_default_id": gcal_name_dict[default_calendar_name],
            "notion_api_version": "2022-06-28",
        }
        return apply_date_range(
            setting,
            defaults.get("goBackDays"),
            defaults.get("goForwardDays"),
        )

    def get(self):
        return deepcopy(self.source_settings)
