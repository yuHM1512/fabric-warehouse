from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def fmt_gmt7(value: Any) -> str:
    if value is None:
        return ""

    dt: datetime | None = None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        s = value.strip()
        if not s:
            return ""
        try:
            dt = datetime.fromisoformat(s)
        except Exception:
            return value
    else:
        return str(value)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    local = dt.astimezone(VN_TZ)
    return local.strftime("%Y-%m-%d %H:%M")


def clean_note(value: Any) -> str:
    """
    Hide internal migration markers from UI.
    """
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    if s.lower() == "migrated_from_sqlite":
        return ""
    return s
