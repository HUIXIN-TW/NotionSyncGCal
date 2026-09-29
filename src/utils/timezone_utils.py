from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class InvalidTimeZoneError(ValueError):
    """Raised when an IANA timezone cannot be resolved safely."""


def resolve_timezone(time_zone_name: str) -> ZoneInfo:
    """Resolve an IANA timezone name or fail with a stable configuration error."""
    if not isinstance(time_zone_name, str) or not time_zone_name.strip():
        raise InvalidTimeZoneError("time zone must be a non-empty IANA timezone name")

    normalized = time_zone_name.strip()
    try:
        return ZoneInfo(normalized)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise InvalidTimeZoneError(f"unknown IANA time zone: {normalized}") from exc


def local_date_at(time_zone_name: str, instant: datetime | None = None) -> date:
    """Return the configured local calendar date for an aware instant."""
    zone = resolve_timezone(time_zone_name)
    current_instant = instant or datetime.now(timezone.utc)
    if current_instant.tzinfo is None:
        raise ValueError("instant must be timezone-aware")
    return current_instant.astimezone(zone).date()


def local_midnight(local_date: date, time_zone_name: str) -> datetime:
    """Return local midnight for a calendar date using that date's actual offset."""
    zone = resolve_timezone(time_zone_name)
    return datetime.combine(local_date, time.min, tzinfo=zone)


def format_local_midnight(
    local_date: date | str,
    time_zone_name: str,
    *,
    milliseconds: bool = False,
) -> str:
    """Serialize local midnight with the offset that applies on that date."""
    if isinstance(local_date, str):
        try:
            local_date = date.fromisoformat(local_date)
        except ValueError as exc:
            raise ValueError(f"invalid ISO calendar date: {local_date}") from exc

    midnight = local_midnight(local_date, time_zone_name)
    timespec = "milliseconds" if milliseconds else "seconds"
    return midnight.isoformat(timespec=timespec)


def format_datetime_in_timezone(value: datetime, time_zone_name: str) -> str:
    """Serialize a datetime in the configured zone using its date-specific offset.

    Naive datetimes are interpreted as wall-clock values in the configured zone.
    Aware datetimes are converted from their existing instant into the configured zone.
    """
    zone = resolve_timezone(time_zone_name)
    if value.tzinfo is None:
        localized = value.replace(tzinfo=zone)
    else:
        localized = value.astimezone(zone)
    return localized.isoformat(timespec="seconds")


__all__ = [
    "InvalidTimeZoneError",
    "format_datetime_in_timezone",
    "format_local_midnight",
    "local_date_at",
    "local_midnight",
    "resolve_timezone",
]
