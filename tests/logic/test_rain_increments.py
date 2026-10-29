"""Rain per local date from positive increments of a total_increasing sensor (round 3, item A1).

Real finding: the rain sensor resets at midnight UTC (02:00 local in summer, 01:00 in winter) and
shows the previous day's total until then.
"""

from datetime import date, datetime

from custom_components.rootine.logic.rain import add_reading, prefill_from_history

from ..conftest import TZ


def feed(readings, rain_days=None, base=None):
    rain_days = dict(rain_days or {})
    for ts, value in readings:
        rain_days, base = add_reading(rain_days, base, ts.astimezone(TZ).date(), value)
    return rain_days, base


def local(y, mo, d, h, mi=0, fold=0):
    return datetime(y, mo, d, h, mi, tzinfo=TZ).replace(fold=fold)


def test_reset_at_utc_midnight_is_no_rain():
    days, base = feed(
        [
            (local(2026, 7, 2, 0, 0), 4.0),  # still yesterday's total, only a base
            (local(2026, 7, 2, 1, 30), 4.0),
            (local(2026, 7, 2, 2, 0), 0.0),  # reset at 00:00 UTC
            (local(2026, 7, 2, 3, 0), 0.4),
        ]
    )
    assert days == {"2026-07-02": 0.4}
    assert base == 0.4


def test_rain_before_the_reset_counts_for_today():
    days, _ = feed(
        [
            (local(2026, 7, 2, 0, 10), 4.0),
            (local(2026, 7, 2, 1, 0), 4.6),  # it rains at 01:00 local, sensor still on yesterday
            (local(2026, 7, 2, 2, 0), 0.0),
            (local(2026, 7, 2, 5, 0), 0.3),
        ]
    )
    assert days == {"2026-07-02": 0.9}


def test_restart_shortly_after_midnight_only_sets_the_base():
    # Home Assistant restarts at 00:30: the first reading is yesterday's 6.2 mm
    days, base = feed([(local(2026, 7, 2, 0, 30), 6.2)])
    assert days == {}
    assert base == 6.2


def test_dst_end_assigns_increments_to_the_local_date():
    # 25.10.2026: 02:00-03:00 happens twice; reset at 00:00 UTC is 02:00 CEST (the first one)
    days, _ = feed(
        [
            (local(2026, 10, 25, 1, 0), 3.0),  # yesterday's total
            (local(2026, 10, 25, 1, 40), 3.5),  # +0.5 before the reset
            (local(2026, 10, 25, 2, 0, fold=0), 0.0),  # reset (CEST)
            (local(2026, 10, 25, 2, 20, fold=1), 0.2),  # repeated hour (CET)
            (local(2026, 10, 25, 23, 0), 1.0),
            (local(2026, 10, 26, 0, 30), 1.0),  # winter: reset only at 01:00 CET
            (local(2026, 10, 26, 0, 50), 1.3),  # +0.3 belongs to the 26th
            (local(2026, 10, 26, 1, 0), 0.0),
        ]
    )
    assert days == {"2026-10-25": 1.5, "2026-10-26": 0.3}


def test_unavailable_gap_and_lower_value_is_a_reset():
    days, base = feed([(local(2026, 7, 2, 8), 1.0), (local(2026, 7, 2, 9), 0.5)])
    assert days == {}
    assert base == 0.5


def test_keeps_60_days():
    days, base = {}, 0.0
    for i in range(70):
        days, base = add_reading(
            days, base, date.fromordinal(date(2026, 1, 1).toordinal() + i), base + 1
        )
    assert len(days) == 60


def test_prefill_from_daily_history_is_an_approximation():
    history = [{"date": "2026-07-01", "mm": 2.5}, {"date": "2026-07-02", "mm": 0}, {"bad": 1}]
    assert prefill_from_history(history) == {"2026-07-01": 2.5, "2026-07-02": 0.0}
    assert prefill_from_history(None) == {}
