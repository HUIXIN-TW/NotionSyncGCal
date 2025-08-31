from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict

import pytz


def get_timestamp(perth_tz_name: str = "Australia/Perth") -> Dict[str, Any]:
    """Return a timestamp dict with UTC and Australia/Perth times plus epoch ms.

    Keys:
    - utc_date, utc_time, utc_time_zone
    - perth_date, perth_time, perth_time_zone
    - epoch_ms
    """
    now_utc = datetime.now(timezone.utc)
    utc_date = now_utc.strftime("%Y-%m-%d")
    utc_time = now_utc.strftime("%H:%M:%S")
    utc_zone = now_utc.tzname()

    perth_tz = pytz.timezone(perth_tz_name)
    now_perth = datetime.now(perth_tz)
    perth_date = now_perth.strftime("%Y-%m-%d")
    perth_time = now_perth.strftime("%H:%M:%S")
    perth_zone = now_perth.tzname()

    return {
        "utc_date": utc_date,
        "utc_time": utc_time,
        "utc_time_zone": utc_zone,
        "perth_date": perth_date,
        "perth_time": perth_time,
        "perth_time_zone": perth_zone,
        "epoch_ms": int(now_utc.timestamp() * 1000),
    }


__all__ = ["get_timestamp"]
