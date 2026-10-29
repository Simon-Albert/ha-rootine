from datetime import date, datetime

from custom_components.rootine.logic.due import (
    DueStatus,
    TaskState,
    compute_due,
    worst_status,
)
from custom_components.rootine.logic.schedule import parse_schedule

from ..conftest import TZ

SEASONAL = parse_schedule("01.03.–31.10.: 6\n01.11.–28.02.: 8")
FERT = parse_schedule("01.03.–31.08.: 14\n01.09.–28.02.: Pause")


def state(y, m, d, **kw):
    return TaskState(datetime(y, m, d, 12, tzinfo=TZ), "button", **kw)


def test_status_progression():
    last = state(2026, 6, 1)  # +6 = 07.06.
    assert compute_due(date(2026, 6, 5), last, SEASONAL).status == DueStatus.OK
    r = compute_due(date(2026, 6, 6), last, SEASONAL)
    assert (r.status, r.days) == (DueStatus.SOON, 1)
    assert compute_due(date(2026, 6, 7), last, SEASONAL).status == DueStatus.DUE
    r = compute_due(date(2026, 6, 9), last, SEASONAL)
    assert (r.status, r.days, r.next_due) == (DueStatus.OVERDUE, -2, date(2026, 6, 7))
    assert r.reason == "timer"


def test_year_wrap_interval_switch():
    # period change while overdue: stays overdue, interval of the last time done
    r = compute_due(date(2026, 11, 3), state(2026, 10, 25), SEASONAL)
    assert r.interval == 8
    assert r.next_due == date(2026, 11, 2)  # 25.10. + 8
    assert r.status == DueStatus.OVERDUE


def test_leap_year():
    r = compute_due(date(2028, 2, 29), state(2028, 2, 25), SEASONAL)
    assert r.next_due == date(2028, 3, 4)  # 25.02. + 8: 29.02. still belongs to the winter plan
    assert r.status == DueStatus.OK


def test_season_start_after_pause():
    last = state(2026, 8, 28)
    r = compute_due(date(2027, 3, 1), last, FERT)
    assert (r.status, r.next_due, r.reason) == (DueStatus.DUE, date(2027, 3, 1), "season_start")
    # Vorher: Pause
    r = compute_due(date(2027, 1, 10), last, FERT)
    assert (r.status, r.next_due, r.days) == (DueStatus.REST, date(2027, 3, 1), 50)


def test_season_start_not_triggered_if_done_in_season():
    r = compute_due(date(2027, 3, 5), state(2027, 3, 3), FERT)
    assert r.reason == "timer"
    assert r.next_due == date(2027, 3, 17)


def test_postpone_over_pause():
    # 20.08. + 14 = 03.09. (pause) + 5 days = 08.09. -> first day after the pause
    r = compute_due(date(2026, 8, 25), state(2026, 8, 20, postponed_days=5), FERT)
    assert r.next_due == date(2027, 3, 1)
    assert r.after_pause
    assert r.status == DueStatus.OK


def test_postpone_moves_date():
    r = compute_due(date(2026, 6, 7), state(2026, 6, 1, postponed_days=2), SEASONAL)
    assert r.next_due == date(2026, 6, 9)
    assert r.status == DueStatus.OK


def test_last_done_in_future():
    r = compute_due(date(2026, 6, 7), state(2026, 6, 20), SEASONAL)
    assert r.status == DueStatus.OK
    assert r.days == 19


def test_empty_schedule():
    r = compute_due(date(2026, 6, 7), state(2026, 6, 1), parse_schedule(""))
    assert (r.status, r.next_due, r.days) == (DueStatus.REST, None, None)


def test_old_next_due_in_pause_stays_overdue():
    r = compute_due(date(2026, 8, 31), state(2026, 8, 1), parse_schedule("01.03.–31.08.: 14"))
    assert r.status == DueStatus.OVERDUE


def test_worst_status():
    S = DueStatus
    assert worst_status([S.OK, S.OVERDUE, S.DUE]) == S.OVERDUE
    assert worst_status([S.OVERDUE, S.PROTECT]) == S.PROTECT
    assert worst_status([S.REST, S.UNKNOWN, S.OK]) == S.OK
    assert worst_status([S.SOON, S.CHECK_SENSOR, S.TOO_WET]) == S.TOO_WET
    assert worst_status([]) == S.UNKNOWN
