from datetime import date, datetime
from zoneinfo import ZoneInfo

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
WEEKDAY_SHORT = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")


def format_date_with_weekday(value: date) -> str:
    return f"{value:%d.%m.%Y} ({WEEKDAY_SHORT[value.weekday()]})"


def format_time_msk(value: datetime) -> str:
    return f"{_to_moscow(value):%H:%M} МСК"


def format_datetime_msk(value: datetime) -> str:
    return f"{_to_moscow(value):%d.%m.%Y %H:%M} МСК"


def _to_moscow(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=MOSCOW_TZ)
    return value.astimezone(MOSCOW_TZ)
