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


def fmt_date_dmy(value: Any) -> str:
    """
    Format date/datetime/string to dd/mm/yyyy (VN style).
    """
    if value is None:
        return ""
    if isinstance(value, datetime):
        dt = value
    elif hasattr(value, "strftime"):
        # date object
        try:
            return value.strftime("%d/%m/%Y")  # type: ignore[no-any-return]
        except Exception:
            return str(value)
    elif isinstance(value, str):
        s = value.strip()
        if not s:
            return ""
        # try ISO date first
        try:
            if len(s) >= 10 and s[4] == "-" and s[7] == "-":
                return f"{s[8:10]}/{s[5:7]}/{s[0:4]}"
        except Exception:
            pass
        try:
            dt = datetime.fromisoformat(s)
        except Exception:
            return value
    else:
        return str(value)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(VN_TZ)
    return local.strftime("%d/%m/%Y")
