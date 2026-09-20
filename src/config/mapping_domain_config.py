import json
from copy import deepcopy
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


TASK_PROPERTY_POLICY = {
    "task": ("Task_Notion_Name", "title"),
    "date": ("Date_Notion_Name", "date"),
    "initiative": ("Initiative_Notion_Name", "multi_select"),
    "status": ("Status_Notion_Name", "status"),
    "location": ("Location_Notion_Name", "place"),
    "extraInfo": ("ExtraInfo_Notion_Name", "rich_text"),
    "sprint": ("Sprint_Notion_Name", "select"),
    "calendarName": ("GCal_Name_Notion_Name", "select"),
    "googleCalendarEventId": ("GCal_EventId_Notion_Name", "rich_text"),
    "googleCalendarSyncTime": ("GCal_Sync_Time_Notion_Name", "rich_text"),
    "googleCalendarEndDate": ("GCal_End_Date_Notion_Name", "formula"),
    "googleCalendarDeleted": ("Delete_Notion_Name", "checkbox"),
    "googleCalendarIcon": ("CompleteIcon_Notion_Name", "formula"),
}

DOMAIN_REQUIRED_PROPERTIES = frozenset({"task", "date"})
SYNC_REQUIRED_PROPERTIES = frozenset(
    {
        "calendarName",
        "googleCalendarEventId",
        "googleCalendarSyncTime",
        "googleCalendarEndDate",
    }
)


class SettingError(Exception):
    """Raised when mapping-domain configuration cannot safely drive sync."""


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


def _validate_owner(record, owner_user_uuid, label):
    owner = _require_string(record.get("ownerUserUuid"), f"{label}.ownerUserUuid")
    if owner != owner_user_uuid:
        raise SettingError(f"{label} does not belong to the requested owner.")


def apply_date_range(setting, go_back_days, go_forward_days, *, now=None):
    """Apply an IANA-zone-aware date window to one source setting."""
    zone_name = _require_string(setting.get("timezone"), "timezone")
    try:
        zone = ZoneInfo(zone_name)
    except ZoneInfoNotFoundError as exc:
        raise SettingError(f"timezone is not a valid IANA time zone: {zone_name}") from exc

    go_back_days = _require_int(go_back_days, "goBackDays", minimum=0, maximum=365)
    go_forward_days = _require_int(go_forward_days, "goForwardDays", minimum=0, maximum=365)
    current = now.astimezone(zone) if now else datetime.now(zone)
    after_date = current.date() - timedelta(days=go_back_days)
    before_date = current.date() + timedelta(days=go_forward_days)
    after_datetime = datetime.combine(after_date, time.min, tzinfo=zone)
    before_datetime = datetime.combine(before_date, time.min, tzinfo=zone)

    setting["goback_days"] = go_back_days
    setting["goforward_days"] = go_forward_days
    setting["after_date"] = after_date.isoformat()
    setting["before_date"] = before_date.isoformat()
    setting["google_timemin"] = after_datetime.isoformat(timespec="milliseconds")
    setting["google_timemax"] = before_datetime.isoformat(timespec="milliseconds")
    return setting


class MappingDomainConfig:
    """Loads and validates the v2 settings/source/calendar-mapping contract."""

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
                list_mapping_domain_calendar_mappings,
                list_mapping_domain_task_sources,
            )

            owner = _require_string(self.config.get("uuid"), "uuid")
            settings = get_mapping_domain_settings(owner)
            sources = list_mapping_domain_task_sources(owner)
            mappings = []
            for raw_source in sources:
                source = _require_dict(raw_source, "taskSource")
                source_id = _require_string(source.get("id"), "taskSource.id")
                for raw_mapping in list_mapping_domain_calendar_mappings(owner, source_id):
                    mapping = _require_dict(raw_mapping, "calendarMapping")
                    mapping_source_id = _require_string(mapping.get("sourceId"), "calendarMapping.sourceId")
                    if mapping_source_id != source_id:
                        raise SettingError(
                            f"Calendar mapping was queried for Task source {source_id} "
                            f"but declares sourceId {mapping_source_id}."
                        )
                    mappings.append(mapping)
            return {"settings": settings, "taskSources": sources, "calendarMappings": mappings}

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

        _validate_owner(settings, owner, "settings")
        timezone = _require_string(settings.get("timeZone"), "settings.timeZone")
        try:
            ZoneInfo(timezone)
        except ZoneInfoNotFoundError as exc:
            raise SettingError(f"settings.timeZone is not a valid IANA time zone: {timezone}") from exc

        validated_sources = []
        seen_source_ids = set()
        for raw_source in sources:
            source = _require_dict(raw_source, "taskSource")
            _validate_owner(source, owner, "taskSource")
            source_id = _require_string(source.get("id"), "taskSource.id")
            if source_id in seen_source_ids:
                raise SettingError(f"Duplicate Task source id: {source_id}")
            seen_source_ids.add(source_id)
            lifecycle = _require_string(source.get("lifecycle"), f"taskSource[{source_id}].lifecycle")
            if lifecycle not in {"active", "disabled"}:
                raise SettingError(f"taskSource[{source_id}].lifecycle must be active or disabled.")
            source["id"] = source_id
            source["lifecycle"] = lifecycle
            validated_sources.append(source)

        mappings_by_source = {source_id: [] for source_id in seen_source_ids}
        seen_mapping_ids = set()
        for raw_mapping in mappings:
            mapping = _require_dict(raw_mapping, "calendarMapping")
            _validate_owner(mapping, owner, "calendarMapping")
            mapping_id = _require_string(mapping.get("id"), "calendarMapping.id")
            if mapping_id in seen_mapping_ids:
                raise SettingError(f"Duplicate Calendar mapping id: {mapping_id}")
            seen_mapping_ids.add(mapping_id)
            source_id = _require_string(mapping.get("sourceId"), f"calendarMapping[{mapping_id}].sourceId")
            if source_id not in seen_source_ids:
                raise SettingError(f"Calendar mapping {mapping_id} references unknown Task source {source_id}.")
            lifecycle = _require_string(mapping.get("lifecycle"), f"calendarMapping[{mapping_id}].lifecycle")
            if lifecycle not in {"active", "disabled"}:
                raise SettingError(f"calendarMapping[{mapping_id}].lifecycle must be active or disabled.")
            calendar_id = _require_string(mapping.get("calendarId"), f"calendarMapping[{mapping_id}].calendarId")
            mapping["id"] = mapping_id
            mapping["sourceId"] = source_id
            mapping["lifecycle"] = lifecycle
            mapping["calendarId"] = calendar_id
            mappings_by_source[source_id].append(mapping)

        active_sources = []
        active_calendar_owners = {}
        for source in validated_sources:
            source_id = _require_string(source.get("id"), "taskSource.id")
            if source.get("lifecycle") != "active":
                continue

            source_mappings = []
            source_calendar_ids = set()
            for mapping in mappings_by_source[source_id]:
                if mapping["lifecycle"] != "active":
                    continue
                calendar_id = _require_string(mapping.get("calendarId"), "calendarMapping.calendarId")
                if calendar_id in source_calendar_ids:
                    raise SettingError(
                        f"Google Calendar {calendar_id} has multiple active mappings for Task source {source_id}."
                    )
                source_calendar_ids.add(calendar_id)
                previous_source = active_calendar_owners.get(calendar_id)
                if previous_source:
                    raise SettingError(f"Google Calendar {calendar_id} is assigned to multiple active Task sources.")
                active_calendar_owners[calendar_id] = source_id
                source_mappings.append(mapping)

            if not source_mappings:
                raise SettingError(f"Task source {source_id} is active but has no active Calendar mapping.")
            active_sources.append(self._to_source_setting(source, source_mappings, timezone))

        if not active_sources:
            raise SettingError("No active Task source was found.")
        return active_sources

    def _to_source_setting(self, source, mappings, timezone):
        source_id = source["id"]
        database = _require_dict(source.get("database"), f"taskSource[{source_id}].database")
        defaults = _require_dict(source.get("defaults"), f"taskSource[{source_id}].defaults")
        property_mappings = _require_dict(source.get("propertyMappings"), f"taskSource[{source_id}].propertyMappings")

        required = DOMAIN_REQUIRED_PROPERTIES | SYNC_REQUIRED_PROPERTIES
        missing = sorted(required - property_mappings.keys())
        if missing:
            raise SettingError(f"Task source {source_id} is not sync-ready; missing semantic mappings: {missing}")

        page_property = {}
        for semantic_key, raw_mapping in property_mappings.items():
            if semantic_key not in TASK_PROPERTY_POLICY:
                continue
            runtime_key, expected_type = TASK_PROPERTY_POLICY[semantic_key]
            mapping = _require_dict(raw_mapping, f"propertyMappings.{semantic_key}")
            property_id = _require_string(mapping.get("propertyId"), f"propertyMappings.{semantic_key}.propertyId")
            property_type = _require_string(
                mapping.get("propertyType"), f"propertyMappings.{semantic_key}.propertyType"
            )
            if property_type != expected_type:
                raise SettingError(f"propertyMappings.{semantic_key} must be {expected_type}, got {property_type}.")
            page_property[runtime_key] = property_id

        calendar_ids = sorted(
            {_require_string(mapping.get("calendarId"), "calendarMapping.calendarId") for mapping in mappings}
        )
        setting = {
            "source_id": source_id,
            "database_id": _require_string(database.get("externalId"), "taskSource.database.externalId"),
            "timezone": timezone,
            "default_event_length": _require_int(
                defaults.get("defaultEventLengthMinutes"),
                "taskSource.defaults.defaultEventLengthMinutes",
                minimum=1,
                maximum=1440,
            ),
            "default_start_time": _require_int(
                defaults.get("defaultStartHour"),
                "taskSource.defaults.defaultStartHour",
                minimum=0,
                maximum=23,
            ),
            "calendar_ids": calendar_ids,
            "page_property": page_property,
            "notion_api_version": "2022-06-28",
        }
        return apply_date_range(
            setting,
            defaults.get("goBackDays"),
            defaults.get("goForwardDays"),
        )

    def get(self):
        return deepcopy(self.source_settings)
