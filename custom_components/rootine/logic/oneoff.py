"""One-time tasks per plant: a name and a date, optionally repeated every year.

A one-time task is due on its date, overdue afterwards and "soon" from `remind_days`
before (at least the day before, like the scheduled tasks). Completing it removes it,
a yearly one moves to the next year instead.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from typing import Any

from .due import DueResult, DueStatus

REMIND_MAX = 60
PREFIX = "once_"  # ids never collide with task keys


@dataclass(frozen=True)
class OneOff:
    id: str
    name: str
    due: date
    yearly: bool = False
    remind_days: int = 0


def evaluate(item: OneOff, today: date) -> DueResult:
    days = (item.due - today).days
    if days < 0:
        status = DueStatus.OVERDUE
    elif days == 0:
        status = DueStatus.DUE
    elif days <= max(1, item.remind_days):
        status = DueStatus.SOON
    else:
        status = DueStatus.OK
    return DueResult(status, item.due, days, None, None, "oneoff")


def _add_year(day: date) -> date:
    try:
        return day.replace(year=day.year + 1)
    except ValueError:  # 29 February
        return day.replace(year=day.year + 1, day=28)


def complete(item: OneOff, today: date) -> OneOff | None:
    """The task after completing it: None for a one-time task, next year's for a yearly."""
    if not item.yearly:
        return None
    due = _add_year(item.due)
    while due <= today:
        due = _add_year(due)
    return replace(item, due=due)


def to_dict(item: OneOff) -> dict[str, Any]:
    return {
        "id": item.id,
        "name": item.name,
        "due": item.due.isoformat(),
        "yearly": item.yearly,
        "remind_days": item.remind_days,
    }


def from_dict(data: dict[str, Any]) -> OneOff:
    return OneOff(
        id=data["id"],
        name=data["name"],
        due=date.fromisoformat(data["due"]),
        yearly=bool(data.get("yearly", False)),
        remind_days=int(data.get("remind_days", 0)),
    )
