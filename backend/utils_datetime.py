from datetime import datetime, timedelta, timezone


IST_OFFSET = timedelta(hours=5, minutes=30)
IST_TZ = timezone(IST_OFFSET, name="IST")


def to_utc_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    s = dt.isoformat()
    if s.endswith("Z") or "+" in s[-7:] or (len(s) > 10 and s[10] in "+-"):
        return s
    return s + "Z"


def to_ist(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST_TZ)


def to_ist_iso(dt: datetime | None) -> str | None:
    ist = to_ist(dt)
    return ist.isoformat() if ist else None


def format_ist_datetime(dt: datetime | None) -> str:
    ist = to_ist(dt)
    return ist.strftime("%Y-%m-%d %H:%M:%S") if ist else ""


def format_ist_date(dt: datetime | None) -> str:
    ist = to_ist(dt)
    return ist.strftime("%Y-%m-%d") if ist else ""


def format_ist_time(dt: datetime | None) -> str:
    ist = to_ist(dt)
    return ist.strftime("%H:%M:%S") if ist else ""
