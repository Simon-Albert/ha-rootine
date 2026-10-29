"""Parse and format the schedule notation, find periods (7.1)."""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

DayMonth = tuple[int, int]  # (day, month)


class TaskKind(StrEnum):
    WATER = "water"
    FERTILIZE = "fertilize"
    CUSTOM = "custom"


class WaterMode(StrEnum):
    TIMER = "timer"
    RAIN = "rain"
    SENSOR = "sensor"


@dataclass(frozen=True)
class Period:
    start: DayMonth  # inklusive
    end: DayMonth  # inclusive, may span the turn of the year
    interval_days: int | None  # None = Pause


@dataclass(frozen=True)
class Schedule:
    periods: tuple[Period, ...]  # gaps mean pause


class ScheduleError(ValueError):
    """Schedule error with translation key and placeholders."""

    def __init__(self, key: str, **placeholders: str | int) -> None:
        super().__init__(key)
        self.key = key
        self.placeholders = placeholders


_DATE = r"(\d{1,2})\.\s*(\d{1,2})\.?"
_RANGE_RE = re.compile(rf"^\s*{_DATE}\s*(?:-|–|—|bis)\s*{_DATE}\s*$", re.IGNORECASE)
_YEARLONG_RE = re.compile(r"^\s*ganzj(?:ä|ae)hrig\s*$", re.IGNORECASE)
_VALUE_RE = re.compile(r"^\s*(?:(\d+)\s*(?:tage|tag)?|(pause))\s*$", re.IGNORECASE)

_LEAP_YEAR = 2024


def _valid_day_month(day: int, month: int) -> bool:
    if not 1 <= month <= 12:
        return False
    return 1 <= day <= calendar.monthrange(_LEAP_YEAR, month)[1]


def parse_schedule(text: str) -> Schedule:
    """Turn schedule text into a Schedule. Raises ScheduleError with the line number."""
    periods: list[tuple[int, Period]] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        if ":" not in raw:
            raise ScheduleError("invalid_line", line=number)
        range_text, value_text = raw.split(":", 1)

        if _YEARLONG_RE.match(range_text):
            start, end = (1, 1), (31, 12)
        else:
            match = _RANGE_RE.match(range_text)
            if not match:
                raise ScheduleError("invalid_line", line=number)
            d1, m1, d2, m2 = (int(g) for g in match.groups())
            if not _valid_day_month(d1, m1) or not _valid_day_month(d2, m2):
                raise ScheduleError("invalid_date", line=number)
            start, end = (d1, m1), (d2, m2)

        value = _VALUE_RE.match(value_text)
        if not value:
            raise ScheduleError("invalid_interval", line=number)
        if value.group(2):
            interval = None
        else:
            interval = int(value.group(1))
            if not 1 <= interval <= 365:
                raise ScheduleError("invalid_interval", line=number)
        periods.append((number, Period(start, end, interval)))

    _check_overlaps(periods)
    return Schedule(tuple(p for _, p in periods))


def _check_overlaps(periods: list[tuple[int, Period]]) -> None:
    owner: dict[DayMonth, int] = {}
    for number, period in periods:
        for key in _days_of(period):
            if key in owner:
                raise ScheduleError("overlap", line=number, other=owner[key])
            owner[key] = number


def _days_of(period: Period) -> list[DayMonth]:
    """All (day, month) of the period, counted in a leap year."""
    day = date(_LEAP_YEAR, period.start[1], period.start[0])
    end = date(_LEAP_YEAR, period.end[1], period.end[0])
    result: list[DayMonth] = []
    while True:
        result.append((day.day, day.month))
        if day == end:
            return result
        day += timedelta(days=1)
        if day.year != _LEAP_YEAR:
            day = date(_LEAP_YEAR, 1, 1)


def format_schedule(schedule: Schedule) -> str:
    """Schedule back to text (round trip with parse_schedule)."""
    lines = []
    for p in schedule.periods:
        value = "Pause" if p.interval_days is None else str(p.interval_days)
        if p.start == (1, 1) and p.end == (31, 12):
            lines.append(f"ganzjährig: {value}")
        else:
            lines.append(
                f"{p.start[0]:02d}.{p.start[1]:02d}.–{p.end[0]:02d}.{p.end[1]:02d}.: {value}"
            )
    return "\n".join(lines)


def _key(d: date) -> DayMonth:
    return (d.day, d.month)


def _normalize(point: DayMonth, year: int, *, is_end: bool) -> DayMonth:
    """29.02. in non-leap years: as an end the 28.02., as a start the 01.03."""
    if point == (29, 2) and not calendar.isleap(year):
        return (28, 2) if is_end else (1, 3)
    return point


def _contains(period: Period, d: date) -> bool:
    start = _normalize(period.start, d.year, is_end=False)
    end = _normalize(period.end, d.year, is_end=True)
    if end == (28, 2) and calendar.isleap(d.year):
        end = (29, 2)  # "until 28.02." includes 29.02. in a leap year
    k = (d.month, d.day)
    s, e = (start[1], start[0]), (end[1], end[0])
    if s <= e:
        return s <= k <= e
    return k >= s or k <= e


def period_for(schedule: Schedule, d: date) -> Period | None:
    """Period containing d. None = gap (pause)."""
    for period in schedule.periods:
        if _contains(period, d):
            return period
    return None


def interval_for(schedule: Schedule, d: date) -> int | None:
    """Interval on day d. None during a pause or gap."""
    period = period_for(schedule, d)
    return None if period is None else period.interval_days


def occurrence_start(period: Period, d: date) -> date:
    """Start date of the occurrence of period that contains d."""
    day, month = _normalize(period.start, d.year, is_end=False)
    candidate_year = d.year
    if (month, day) > (d.month, d.day):
        candidate_year -= 1
    day, month = _normalize(period.start, candidate_year, is_end=False)
    return date(candidate_year, month, day)


def first_active_day(schedule: Schedule, d: date) -> date | None:
    """First day from d (inclusive) with an interval. None if there never is one."""
    for offset in range(367):
        day = d + timedelta(days=offset)
        if interval_for(schedule, day) is not None:
            return day
    return None
