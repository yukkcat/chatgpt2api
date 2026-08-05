from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable

BEIJING_TZ = timezone(timedelta(hours=8), "Asia/Shanghai")
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
TIME_FORMAT = "%H:%M:%S"


def beijing_now() -> datetime:
    return datetime.now(BEIJING_TZ)


def beijing_now_str(fmt: str = DATETIME_FORMAT) -> str:
    return beijing_now().strftime(fmt)


def beijing_from_timestamp(timestamp: float, fmt: str = DATETIME_FORMAT) -> str:
    return datetime.fromtimestamp(timestamp, tz=BEIJING_TZ).strftime(fmt)


def beijing_datetime_from_timestamp(timestamp: float) -> datetime:
    return datetime.fromtimestamp(timestamp, tz=BEIJING_TZ)


def beijing_naive_from_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(BEIJING_TZ).replace(tzinfo=None)


def parse_to_beijing_naive(value: object, formats: Iterable[str] | None = None) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return beijing_naive_from_datetime(datetime.fromisoformat(raw.replace("Z", "+00:00")))
    except ValueError:
        pass
    for fmt in formats or (DATETIME_FORMAT, "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None
