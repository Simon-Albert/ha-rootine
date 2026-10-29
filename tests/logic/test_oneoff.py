"""One-time tasks: status, reminder window, completing, yearly repeat (item B6)."""

from __future__ import annotations

from datetime import date

import pytest

from custom_components.rootine.logic.due import DueStatus
from custom_components.rootine.logic.oneoff import OneOff, complete, evaluate, from_dict, to_dict

TODAY = date(2026, 10, 29)


def make(due: date, **kw) -> OneOff:
    return OneOff(id="once_a", name="Umtopfen", due=due, **kw)


@pytest.mark.parametrize(
    ("due", "remind", "status", "days"),
    [
        (date(2026, 10, 20), 0, DueStatus.OVERDUE, -9),
        (date(2026, 10, 29), 0, DueStatus.DUE, 0),
        (date(2026, 10, 30), 0, DueStatus.SOON, 1),  # like timers: tomorrow is soon
        (date(2026, 11, 2), 0, DueStatus.OK, 4),
        (date(2026, 11, 2), 5, DueStatus.SOON, 4),  # inside the reminder window
        (date(2026, 11, 3), 5, DueStatus.SOON, 5),
        (date(2026, 11, 4), 5, DueStatus.OK, 6),
    ],
)
def test_status(due, remind, status, days):
    result = evaluate(make(due, remind_days=remind), TODAY)
    assert (result.status, result.days, result.next_due) == (status, days, due)
    assert result.reason == "oneoff"


def test_one_time_task_is_gone_after_completing():
    assert complete(make(date(2026, 10, 29)), TODAY) is None


def test_yearly_moves_to_next_year():
    nxt = complete(make(date(2026, 10, 29), yearly=True, remind_days=3), TODAY)
    assert nxt == make(date(2027, 10, 29), yearly=True, remind_days=3)


def test_yearly_completed_early_still_moves_one_year():
    nxt = complete(make(date(2026, 11, 2), yearly=True), TODAY)
    assert nxt.due == date(2027, 11, 2)


def test_yearly_far_overdue_lands_in_the_future():
    nxt = complete(make(date(2024, 3, 1), yearly=True), TODAY)
    assert nxt.due == date(2027, 3, 1)


def test_yearly_on_29_february():
    nxt = complete(make(date(2028, 2, 29), yearly=True), date(2028, 2, 29))
    assert nxt.due == date(2029, 2, 28)


def test_round_trip():
    item = make(date(2026, 12, 1), yearly=True, remind_days=7)
    assert from_dict(to_dict(item)) == item
    assert to_dict(item) == {
        "id": "once_a",
        "name": "Umtopfen",
        "due": "2026-12-01",
        "yearly": True,
        "remind_days": 7,
    }


def test_from_dict_defaults():
    assert from_dict({"id": "once_b", "name": "Schneiden", "due": "2027-02-01"}) == OneOff(
        "once_b", "Schneiden", date(2027, 2, 1)
    )
