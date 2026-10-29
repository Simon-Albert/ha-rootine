from datetime import date

import pytest

from custom_components.rootine.logic.schedule import (
    Period,
    ScheduleError,
    first_active_day,
    format_schedule,
    interval_for,
    occurrence_start,
    parse_schedule,
    period_for,
)

PLAN = "01.03.–31.10.: 6\n01.11.–28.02.: 8"


def test_parse_basic():
    s = parse_schedule(PLAN)
    assert s.periods == (Period((1, 3), (31, 10), 6), Period((1, 11), (28, 2), 8))


@pytest.mark.parametrize(
    "text",
    [
        "01.03.-31.10.: 6",
        "1.3. bis 31.10.: 6 Tage",
        "01.03 — 31.10: 6",
        "  01.03.–31.10. :  6  ",
    ],
)
def test_parse_tolerant(text):
    assert parse_schedule(text).periods == (Period((1, 3), (31, 10), 6),)


def test_parse_pause_and_yearlong():
    s = parse_schedule("01.03.-31.08.: 14\n01.09.-28.02.: Pause")
    assert s.periods[1].interval_days is None
    assert parse_schedule("ganzjährig: 7").periods == (Period((1, 1), (31, 12), 7),)
    assert parse_schedule("Ganzjaehrig: 1 Tag").periods[0].interval_days == 1


def test_empty_is_always_rest():
    s = parse_schedule("\n  \n")
    assert s.periods == ()
    assert period_for(s, date(2026, 5, 5)) is None


@pytest.mark.parametrize(
    ("text", "key", "line"),
    [
        ("blabla", "invalid_line", 1),
        ("01.03.–31.10.: 6\nunsinn: 3", "invalid_line", 2),
        ("32.03.–31.10.: 6", "invalid_date", 1),
        ("01.13.–31.10.: 6", "invalid_date", 1),
        ("01.03.–31.10.: 0", "invalid_interval", 1),
        ("01.03.–31.10.: 366", "invalid_interval", 1),
        ("01.03.–31.10.: oft", "invalid_interval", 1),
        ("01.03.–30.06.: 6\n01.06.–31.10.: 7", "overlap", 2),
        ("ganzjährig: 6\n01.06.–31.10.: 7", "overlap", 2),
    ],
)
def test_parse_errors(text, key, line):
    with pytest.raises(ScheduleError) as err:
        parse_schedule(text)
    assert err.value.key == key
    assert err.value.placeholders["line"] == line


def test_roundtrip():
    for text in (PLAN, "ganzjährig: 7", "01.03.–31.08.: 14\n01.09.–28.02.: Pause", ""):
        s = parse_schedule(text)
        assert parse_schedule(format_schedule(s)) == s
    assert format_schedule(parse_schedule(PLAN)) == "01.03.–31.10.: 6\n01.11.–28.02.: 8"


def test_year_wrap_period():
    s = parse_schedule(PLAN)
    assert interval_for(s, date(2026, 12, 31)) == 8
    assert interval_for(s, date(2027, 1, 1)) == 8
    assert interval_for(s, date(2027, 2, 28)) == 8
    assert interval_for(s, date(2027, 3, 1)) == 6
    assert interval_for(s, date(2026, 10, 31)) == 6


def test_leap_day_end():
    s = parse_schedule("01.11.–29.02.: 8\n01.03.–31.10.: 6")
    assert interval_for(s, date(2028, 2, 29)) == 8
    assert interval_for(s, date(2027, 2, 28)) == 8  # Nicht-Schaltjahr: 29.02. = 28.02.
    assert interval_for(s, date(2027, 3, 1)) == 6


def test_gap_is_rest():
    s = parse_schedule("01.03.–31.08.: 14")
    assert period_for(s, date(2026, 10, 1)) is None
    assert first_active_day(s, date(2026, 10, 1)) == date(2027, 3, 1)


def test_occurrence_start():
    p = Period((1, 11), (28, 2), 8)
    assert occurrence_start(p, date(2027, 1, 15)) == date(2026, 11, 1)
    assert occurrence_start(p, date(2026, 11, 1)) == date(2026, 11, 1)
    assert occurrence_start(Period((1, 3), (31, 8), 14), date(2026, 5, 5)) == date(2026, 3, 1)


def test_first_active_day_never():
    assert first_active_day(parse_schedule(""), date(2026, 1, 1)) is None


def test_feb_28_end_includes_leap_day():
    s = parse_schedule(PLAN)
    assert interval_for(s, date(2028, 2, 29)) == 8
