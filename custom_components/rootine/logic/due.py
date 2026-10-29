"""Compute when a task is due (7.2)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum

from .schedule import (
    Period,
    Schedule,
    TaskKind,
    WaterMode,
    first_active_day,
    occurrence_start,
    period_for,
)

__all__ = [
    "CARE_RANK",
    "DueResult",
    "DueStatus",
    "TaskConfig",
    "TaskState",
    "compute_due",
    "worst_status",
]


class DueStatus(StrEnum):
    OK = "ok"
    SOON = "soon"
    DUE = "due"
    OVERDUE = "overdue"
    REST = "rest"
    UNKNOWN = "unknown"
    PROTECT = "protect"
    TOO_WET = "too_wet"
    CHECK_SENSOR = "check_sensor"


# order for the care status: first = worst (8.3).
CARE_RANK: tuple[DueStatus, ...] = (
    DueStatus.PROTECT,
    DueStatus.OVERDUE,
    DueStatus.DUE,
    DueStatus.TOO_WET,
    DueStatus.CHECK_SENSOR,
    DueStatus.SOON,
    DueStatus.OK,
    DueStatus.REST,
    DueStatus.UNKNOWN,
)


def worst_status(statuses: list[DueStatus]) -> DueStatus:
    if not statuses:
        return DueStatus.UNKNOWN
    return min(statuses, key=CARE_RANK.index)


@dataclass(frozen=True)
class TaskConfig:
    key: str  # "water", "fertilize" or a slug
    kind: TaskKind
    name: str
    schedule: Schedule
    mode: WaterMode = WaterMode.TIMER


@dataclass
class TaskState:
    last_done: datetime
    last_source: str  # button|todo|service|date_edit|sensor|valve|rain|setup
    postponed_days: int = 0
    sensor_due_latched: bool = False
    rain_at_done: float | None = None
    latched_since: datetime | None = None  # when the sensor latch was set (plan 7.3)


@dataclass(frozen=True)
class DueResult:
    status: DueStatus
    next_due: date | None
    days: int | None
    interval: int | None
    period: Period | None
    reason: str
    after_pause: bool = False


def compute_due(today: date, state: TaskState, schedule: Schedule) -> DueResult:
    period = period_for(schedule, today)
    if period is None or period.interval_days is None:
        next_start = first_active_day(schedule, today)
        days = None if next_start is None else (next_start - today).days
        return DueResult(DueStatus.REST, next_start, days, None, period, "timer")

    interval = period.interval_days
    season_start = occurrence_start(period, today)
    last = state.last_done.date()

    reason = "timer"
    day_before = season_start - timedelta(days=1)
    before = period_for(schedule, day_before)
    if (before is None or before.interval_days is None) and last < season_start:
        next_due = max(last + timedelta(days=interval), season_start)
        reason = "season_start"
    else:
        next_due = last + timedelta(days=interval)

    next_due += timedelta(days=state.postponed_days)

    after_pause = False
    landing = period_for(schedule, next_due)
    if next_due >= today and (landing is None or landing.interval_days is None):
        moved = first_active_day(schedule, next_due)
        if moved is not None:
            next_due = moved
            after_pause = True

    days = (next_due - today).days
    if days > 1:
        status = DueStatus.OK
    elif days == 1:
        status = DueStatus.SOON
    elif days == 0:
        status = DueStatus.DUE
    else:
        status = DueStatus.OVERDUE
    return DueResult(status, next_due, days, interval, period, reason, after_pause)
