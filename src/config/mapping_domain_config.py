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
    "googleCalendarEndDate": ("GCal_End_Date_Notion_Name", "formula"),
    "googleCalendarDeleted": ("Delete_Notion_Name", "checkbox"),
    "googleCalendarIcon": ("CompleteIcon_Notion_Name", "formula"),
}

DOMAIN_REQUIRED_PROPERTIES = frozenset({"task", "date"})
SYNC_REQUIRED_PROPERTIES = frozenset({"googleCalendarEndDate"})


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


def _normalize_routing(value, label):
    routing = _require_dict(value, label)
    mode = _require_string(routing.get("mode"), f"{label}.mode")
    if mode == "all":
        if "value" in routing:
            raise SettingError(f"{label}.value is not valid for all routing.")
        return {"mode": "all"}
    if mode == "notion_calendar_value":
        return {
            "mode": mode,
            "value": _require_string(routing.get("value"), f"{label}.value"),
        }
    raise SettingError(f"{label}.mode is invalid: {mode}.")


def _validate_active_mapping_set(source, mappings):
    source_id = _require_string(source.get("id"), "taskSource.id")
    if not mappings:
        raise SettingError(
            f"Task source {source_id} requires at least one active Calendar mapping for sync."
        )

    modes = {mapping["routing"]["mode"] for mapping in mappings}
    if len(modes) != 1:
        raise SettingError(f"Task source {source_id} cannot mix Calendar routing modes.")

    mode = next(iter(modes))
    if mode == "all":
        if len(mappings) != 1:
            raise SettingError(
                f"Task source {source_id} all routing requires exactly one active Calendar mapping."
            )
        return

    property_mappings = _require_dict(
        source.get("propertyMappings"),
        f"taskSource[{source_id}].propertyMappings",
    )
    if "calendarName" not in property_mappings:
        raise SettingError(
            f"Task source {source_id} notion_calendar_value routing requires calendarName."
        )

    seen_values = set()
    for mapping in mappings:
        value = mapping["routing"]["value"]
        if value in seen_values:
            raise SettingError(
                f"Task source {source_id} has duplicate Notion Calendar routing value: {value}."
            )
        seen_values.add(value)


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
    """Loads and validates the current settings/source/calendar-routing contract."""

    def __init__(self, config, logger, execution_fence=None):
        self.config = _require_dict(config, "configuration")
        self.logger = logger
        self.mode = config.get("mode")
        self.owner_user_uuid = config.get("uuid") if self.mode == "cloud" else "local-user"
        self.execution_fence = execution_fence
        self.source_settings = self._format_contract(self._load_contract())

    def _load_contract(self):
        if self.mode == "cloud":
            from utils.dynamodb_utils import (
                get_mapping_domain_settings,
                list_mapping_domain_calendar_mappings_for_owner,
                list_mapping_domain_task_sources,
            )

            owner = _require_string(self.config.get("uuid"), "uuid")
            settings = get_mapping_domain_settings(owner)
            sources = list_mapping_domain_task_sources(owner)
            mappings = list_mapping_domain_calendar_mappings_for_owner(owner)
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
        settings_version = _require_int(settings.get("version"), "settings.version", minimum=1)
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
            source["version"] = _require_int(
                source.get("version"),
                f"taskSource[{source_id}].version",
                minimum=1,
            )
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
            mapping["routing"] = _normalize_routing(
                mapping.get("routing"),
                f"calendarMapping[{mapping_id}].routing",
            )
            mapping["version"] = _require_int(
                mapping.get("version"),
                f"calendarMapping[{mapping_id}].version",
                minimum=1,
            )
            mappings_by_source[source_id].append(mapping)

        active_sources = []
        for source in validated_sources:
            source_id = _require_string(source.get("id"), "taskSource.id")
            if source.get("lifecycle") != "active":
                continue

            active_mappings = sorted(
                [
                    mapping
                    for mapping in mappings_by_source[source_id]
                    if mapping["lifecycle"] == "active"
                ],
                key=lambda mapping: mapping["id"],
            )
            _validate_active_mapping_set(source, active_mappings)
            active_sources.append(
                self._to_source_setting(
                    source,
                    active_mappings,
                    timezone,
                    settings_version,
                )
            )

        if not active_sources:
            raise SettingError("No active Task source was found.")

        self._validate_execution_fence(settings_version, active_sources)
        return active_sources

    def _to_source_setting(self, source, mappings, timezone, settings_version):
        source_id = source["id"]
        database = _require_dict(source.get("database"), f"taskSource[{source_id}].database")
        defaults = _require_dict(source.get("defaults"), f"taskSource[{source_id}].defaults")
        property_mappings = _require_dict(
            source.get("propertyMappings"),
            f"taskSource[{source_id}].propertyMappings",
        )

        required = DOMAIN_REQUIRED_PROPERTIES | SYNC_REQUIRED_PROPERTIES
        missing = sorted(required - property_mappings.keys())
        if missing:
            raise SettingError(
                f"Task source {source_id} is not sync-ready; missing semantic mappings: {missing}"
            )

        page_property = {}
        for semantic_key, raw_mapping in property_mappings.items():
            if semantic_key not in TASK_PROPERTY_POLICY:
                continue
            runtime_key, expected_type = TASK_PROPERTY_POLICY[semantic_key]
            property_mapping = _require_dict(
                raw_mapping,
                f"propertyMappings.{semantic_key}",
            )
            property_id = _require_string(
                property_mapping.get("propertyId"),
                f"propertyMappings.{semantic_key}.propertyId",
            )
            property_type = _require_string(
                property_mapping.get("propertyType"),
                f"propertyMappings.{semantic_key}.propertyType",
            )
            if property_type != expected_type:
                raise SettingError(
                    f"propertyMappings.{semantic_key} must be {expected_type}, got {property_type}."
                )
            page_property[runtime_key] = property_id

        runtime_mappings = [
            {
                "mapping_id": _require_string(
                    mapping.get("id"),
                    "calendarMapping.id",
                ),
                "mapping_version": _require_int(
                    mapping.get("version"),
                    "calendarMapping.version",
                    minimum=1,
                ),
                "calendar_id": _require_string(
                    mapping.get("calendarId"),
                    "calendarMapping.calendarId",
                ),
                "routing": deepcopy(mapping["routing"]),
            }
            for mapping in mappings
        ]

        setting = {
            "owner_user_uuid": self.owner_user_uuid,
            "settings_version": settings_version,
            "source_id": source_id,
            "source_version": source["version"],
            "calendar_mappings": runtime_mappings,
            "database_id": _require_string(
                database.get("externalId"),
                "taskSource.database.externalId",
            ),
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
            "page_property": page_property,
            "notion_api_version": "2022-06-28",
        }
        return apply_date_range(
            setting,
            defaults.get("goBackDays"),
            defaults.get("goForwardDays"),
        )

    def _validate_execution_fence(self, settings_version, active_sources):
        if self.execution_fence is None:
            return

        fence = _require_dict(self.execution_fence, "execution")
        contract_version = _require_int(
            fence.get("contractVersion"),
            "execution.contractVersion",
            minimum=1,
        )
        if contract_version != 3:
            raise SettingError(
                f"Unsupported sync execution contract version: {contract_version}."
            )

        admission_started_at_ms = _require_int(
            fence.get("admissionStartedAtMs"),
            "execution.admissionStartedAtMs",
            minimum=0,
        )

        owner = _require_string(
            fence.get("ownerUserUuid"),
            "execution.ownerUserUuid",
        )
        if owner != self.owner_user_uuid:
            raise SettingError("Sync execution fence belongs to a different owner.")

        expected_settings_version = _require_int(
            fence.get("settingsVersion"),
            "execution.settingsVersion",
            minimum=1,
        )
        if expected_settings_version != settings_version:
            raise SettingError(
                "Notion settings changed after the sync job was admitted."
            )

        operation_id = _require_string(
            fence.get("operationId"),
            "execution.operationId",
        )
        task_fences = _require_list(
            fence.get("taskSources"),
            "execution.taskSources",
        )
        by_source = {}
        for raw_fence in task_fences:
            task_fence = _require_dict(raw_fence, "execution.taskSource")
            source_id = _require_string(
                task_fence.get("sourceId"),
                "execution.taskSource.sourceId",
            )
            if source_id in by_source:
                raise SettingError(
                    f"Duplicate execution fence for Task source {source_id}."
                )
            by_source[source_id] = task_fence

        active_by_source = {
            setting["source_id"]: setting for setting in active_sources
        }
        if set(by_source) != set(active_by_source):
            raise SettingError(
                "Active Task sources changed after the sync job was admitted."
            )

        for source_id, setting in active_by_source.items():
            task_fence = by_source[source_id]
            actual_source_version = _require_int(
                task_fence.get("sourceVersion"),
                f"execution.taskSource[{source_id}].sourceVersion",
                minimum=1,
            )
            if actual_source_version != setting["source_version"]:
                raise SettingError(
                    f"Task source {source_id} changed after the sync job was admitted."
                )

            raw_mapping_fences = _require_list(
                task_fence.get("mappings"),
                f"execution.taskSource[{source_id}].mappings",
            )
            fence_mappings = {}
            for raw_mapping_fence in raw_mapping_fences:
                mapping_fence = _require_dict(
                    raw_mapping_fence,
                    f"execution.taskSource[{source_id}].mapping",
                )
                mapping_id = _require_string(
                    mapping_fence.get("mappingId"),
                    f"execution.taskSource[{source_id}].mapping.mappingId",
                )
                if mapping_id in fence_mappings:
                    raise SettingError(
                        f"Duplicate execution mapping fence: {mapping_id}."
                    )
                fence_mappings[mapping_id] = {
                    "mapping_version": _require_int(
                        mapping_fence.get("mappingVersion"),
                        f"execution.mapping[{mapping_id}].mappingVersion",
                        minimum=1,
                    ),
                    "calendar_id": _require_string(
                        mapping_fence.get("calendarId"),
                        f"execution.mapping[{mapping_id}].calendarId",
                    ),
                    "routing": _normalize_routing(
                        mapping_fence.get("routing"),
                        f"execution.mapping[{mapping_id}].routing",
                    ),
                }

            expected_mappings = {
                mapping["mapping_id"]: mapping
                for mapping in setting["calendar_mappings"]
            }
            if set(fence_mappings) != set(expected_mappings):
                raise SettingError(
                    f"Calendar mapping set for Task source {source_id} changed after admission."
                )

            for mapping_id, expected in expected_mappings.items():
                actual = fence_mappings[mapping_id]
                if (
                    actual["mapping_version"] != expected["mapping_version"]
                    or actual["calendar_id"] != expected["calendar_id"]
                    or actual["routing"] != expected["routing"]
                ):
                    raise SettingError(
                        f"Calendar mapping {mapping_id} changed after the sync job was admitted."
                    )

            setting["operation_id"] = operation_id
            setting["execution_contract_version"] = contract_version
            setting["admission_started_at_ms"] = admission_started_at_ms

    def revalidate_source(self, setting):
        """Strongly re-read the complete source execution snapshot before mutation."""
        if self.mode != "cloud":
            return

        from utils.dynamodb_utils import (
            get_mapping_domain_settings,
            get_mapping_domain_task_source,
            list_mapping_domain_calendar_mappings_for_owner,
        )

        owner = _require_string(
            setting.get("owner_user_uuid"),
            "owner_user_uuid",
        )
        if owner != self.owner_user_uuid:
            raise SettingError(
                "Source execution snapshot belongs to a different owner."
            )

        source_id = _require_string(setting.get("source_id"), "source_id")

        try:
            settings = _require_dict(
                get_mapping_domain_settings(owner),
                "settings",
            )
            source = _require_dict(
                get_mapping_domain_task_source(owner, source_id),
                "taskSource",
            )
            owner_mappings = list_mapping_domain_calendar_mappings_for_owner(
                owner
            )
        except ValueError as exc:
            raise SettingError(
                "Authoritative sync configuration disappeared while the job was running."
            ) from exc

        _validate_owner(settings, owner, "settings")
        if (
            _require_int(
                settings.get("version"),
                "settings.version",
                minimum=1,
            )
            != setting.get("settings_version")
        ):
            raise SettingError(
                "Notion settings changed while the sync job was running."
            )
        if (
            _require_string(
                settings.get("timeZone"),
                "settings.timeZone",
            )
            != setting.get("timezone")
        ):
            raise SettingError(
                "Notion timezone changed while the sync job was running."
            )

        _validate_owner(source, owner, "taskSource")
        if _require_string(source.get("id"), "taskSource.id") != source_id:
            raise SettingError(
                "Task source identity changed while the sync job was running."
            )
        if (
            _require_string(source.get("lifecycle"), "taskSource.lifecycle")
            != "active"
        ):
            raise SettingError("Task source is no longer active.")
        if (
            _require_int(
                source.get("version"),
                "taskSource.version",
                minimum=1,
            )
            != setting.get("source_version")
        ):
            raise SettingError(
                "Task source changed while the sync job was running."
            )

        database = _require_dict(
            source.get("database"),
            "taskSource.database",
        )
        if (
            _require_string(
                database.get("externalId"),
                "taskSource.database.externalId",
            )
            != setting.get("database_id")
        ):
            raise SettingError(
                "Task source database changed while the sync job was running."
            )

        current_mappings = []
        for raw_mapping in owner_mappings:
            candidate = _require_dict(raw_mapping, "calendarMapping")
            if (
                candidate.get("sourceId") != source_id
                or candidate.get("lifecycle") != "active"
            ):
                continue
            _validate_owner(candidate, owner, "calendarMapping")
            mapping_id = _require_string(
                candidate.get("id"),
                "calendarMapping.id",
            )
            current_mappings.append(
                {
                    "id": mapping_id,
                    "sourceId": source_id,
                    "calendarId": _require_string(
                        candidate.get("calendarId"),
                        f"calendarMapping[{mapping_id}].calendarId",
                    ),
                    "version": _require_int(
                        candidate.get("version"),
                        f"calendarMapping[{mapping_id}].version",
                        minimum=1,
                    ),
                    "routing": _normalize_routing(
                        candidate.get("routing"),
                        f"calendarMapping[{mapping_id}].routing",
                    ),
                    "lifecycle": "active",
                }
            )

        current_mappings.sort(key=lambda mapping: mapping["id"])
        _validate_active_mapping_set(source, current_mappings)

        expected_mappings = {
            mapping["mapping_id"]: mapping
            for mapping in setting["calendar_mappings"]
        }
        current_by_id = {
            mapping["id"]: mapping
            for mapping in current_mappings
        }
        if set(current_by_id) != set(expected_mappings):
            raise SettingError(
                "Task source Calendar mapping set changed while the sync job was running."
            )

        for mapping_id, expected in expected_mappings.items():
            current = current_by_id[mapping_id]
            if (
                current["version"] != expected["mapping_version"]
                or current["calendarId"] != expected["calendar_id"]
                or current["routing"] != expected["routing"]
            ):
                raise SettingError(
                    f"Calendar mapping {mapping_id} changed while the sync job was running."
                )

    def get(self):
        return deepcopy(self.source_settings)
