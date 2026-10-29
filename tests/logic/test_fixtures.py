"""Pflichttests gegen anonymisierte Echtdaten (Plan 7.4–7.11).

Laufen erst, wenn tests/fixtures/*.csv vorhanden sind; bis dahin werden sie übersprungen.
Die erwarteten Werte stammen aus dem Plan und dürfen nicht an die Implementierung angepasst
werden. Weichen sie ab, zuerst tests/fixtures/reference.py gegen die Implementierung prüfen.
"""

import csv
import itertools
from datetime import date, datetime, timedelta

import pytest

from custom_components.rootine.logic import moisture as m
from custom_components.rootine.logic import valve

from ..conftest import FIXTURES, TZ, load_series, load_states


def _min(ts):
    return ts.replace(second=0, microsecond=0)


def dt(month, day, hour=0, minute=0, second=0):
    return datetime(2025, month, day, hour, minute, second, tzinfo=TZ)


def test_water_events_satsuma():
    events = m.detect_water_events(load_series("satsuma_moisture.csv"))
    assert [_min(e.ts) for e in events] == [dt(10, 2, 18, 5), dt(10, 21, 22, 7)]


def test_water_events_nektarine():
    events = m.detect_water_events(load_series("nektarine_moisture.csv"))
    assert [_min(e.ts) for e in events] == [
        dt(10, 6, 13, 37),
        dt(10, 9, 10, 45),
        dt(10, 14, 23, 25),
        dt(10, 19, 18, 51),
    ]


def test_valve_events():
    one = valve.valve_events(load_states("valve_1.csv"))
    assert [e.start.replace(microsecond=0) for e in one] == [
        dt(10, 6, 13, 36, 56),
        dt(10, 14, 23, 25, 2),
    ]
    two = valve.valve_events(load_states("valve_2.csv"))
    assert [e.start.replace(microsecond=0) for e in two] == [
        dt(10, 5, 13, 58, 33),
        dt(10, 14, 23, 25, 31),
        dt(10, 18, 15, 9, 19),
        dt(10, 18, 15, 24, 11),
        dt(10, 18, 16, 15, 14),
        dt(10, 21, 22, 7, 7),
    ]


def _transitions(series, threshold, method, start, end):
    changes = []
    previous = None
    t = start
    while t <= end:
        value = m.evaluate(series, t, method)
        below = None if value is None else value < threshold
        if previous is not None and below is not None and below != previous:
            changes.append((t, "down" if below else "up"))
        if below is not None:
            previous = below
        t += timedelta(minutes=15)
    return changes


@pytest.mark.parametrize(
    ("threshold", "method", "expected"),
    [
        (55, "median_24h", [(dt(10, 13, 12, 30), "down")]),
        (55, "max_24h", [(dt(10, 14, 7, 0), "down")]),
        (50, "median_24h", [(dt(10, 13, 22, 30), "down")]),
        (50, "max_24h", [(dt(10, 14, 10, 30), "down")]),
        (
            55,
            "raw",
            [
                (dt(10, 12, 13, 0), "down"),
                (dt(10, 12, 13, 30), "up"),
                (dt(10, 12, 14, 30), "down"),
                (dt(10, 12, 20, 30), "up"),
                (dt(10, 13, 7, 15), "down"),
            ],
        ),
        (
            50,
            "raw",
            [(dt(10, 12, 15, 0), "down"), (dt(10, 12, 15, 30), "up"), (dt(10, 13, 10, 45), "down")],
        ),
    ],
)
def test_evaluation_tables(threshold, method, expected):
    series = load_series("nektarine_moisture.csv")
    got = _transitions(series, threshold, method, dt(10, 10), dt(10, 14, 23, 15))
    assert got == expected


def test_implausible_drop_satsuma():
    valid = m.valid_samples(load_series("satsuma_moisture.csv"))
    drops = [_min(b[0]) for a, b in itertools.pairwise(valid) if m.is_implausible_drop(a[1], b[1])]
    assert drops == [dt(10, 21, 8, 33)]


def test_no_stale_in_replay():
    for name in ("satsuma_moisture.csv", "nektarine_moisture.csv"):
        valid = m.valid_samples(load_series(name))
        for a, b in itertools.pairwise(valid):
            assert not m.is_stale(b[0], a[0]), (name, a[0])


def test_too_wet_satsuma_once():
    series = load_series("satsuma_moisture.csv")
    state = m.WetState()
    on = off = None
    t = dt(10, 1, 12)
    while t <= dt(10, 30, 9):
        new = m.update_too_wet(state, m.evaluate(series, t), t, 95)
        if new.active and not state.active:
            on = on or t
        if state.active and not new.active:
            off = t
        state = new
        t += timedelta(hours=1)
    assert (on, off) == (dt(10, 5, 7), dt(10, 7, 22))


def test_rain_mode_cherry():
    """7.7: Kirsche, Modus rain, ganzjährig alle 3 Tage, Regensensor um 00:05 auf Tagessumme."""
    from custom_components.rootine.logic import rain
    from custom_components.rootine.logic.due import TaskState, compute_due
    from custom_components.rootine.logic.schedule import parse_schedule

    path = FIXTURES / "rain_daily.csv"
    if not path.exists():
        pytest.skip("rain_daily.csv fehlt")
    with path.open(newline="") as handle:
        daily = {date.fromisoformat(r["date"]): float(r["mm"]) for r in csv.DictReader(handle)}
    schedule = parse_schedule("ganzjährig: 3")
    state = TaskState(dt(9, 30, 20), "setup", rain_at_done=daily[date(2025, 9, 30)])
    rain_days: dict[str, float] = {}
    resets, statuses = [], {}
    day = date(2025, 10, 1)
    while day <= date(2025, 10, 29):
        rain_days = rain.record_rain(
            rain_days, day - timedelta(days=1), daily[day - timedelta(days=1)]
        )
        rain_days = rain.record_rain(rain_days, day, daily[day])  # 00:05: volle Tagessumme
        if rain.rain_resets(rain_days, day, state.last_done, state.rain_at_done):
            resets.append(day)
            state = TaskState(
                datetime(day.year, day.month, day.day, 0, 5, tzinfo=TZ),
                "rain",
                rain_at_done=daily[day],
            )
        statuses[day] = compute_due(day, state, schedule)
        day += timedelta(days=1)
    assert resets == [date(2025, 10, 2), date(2025, 10, 9), date(2025, 10, 19)]
    expected = {
        date(2025, 10, 5): ("due", 0),
        date(2025, 10, 6): ("overdue", -1),
        date(2025, 10, 8): ("overdue", -3),
        date(2025, 10, 10): ("ok", 2),
        date(2025, 10, 13): ("overdue", -1),
        date(2025, 10, 18): ("overdue", -6),
        date(2025, 10, 20): ("ok", 2),
    }
    for d, (status, days) in expected.items():
        assert (statuses[d].status.value, statuses[d].days) == (status, days), d


def test_cold_episodes_satsuma():
    """7.10: Sensor zeigt zu Beginn jeder Stunde das Stundenminimum, temp_min 5."""
    from custom_components.rootine.logic.climate import Protect, evaluate_protect

    path = FIXTURES / "satsuma_temperature_hourly.csv"
    if not path.exists():
        pytest.skip("satsuma_temperature_hourly.csv fehlt")
    with path.open(newline="") as handle:
        rows = [
            (datetime.fromisoformat(r["hour_start"]), float(r["min"]))
            for r in csv.DictReader(handle)
        ]
    state, since, episodes = Protect(), None, []
    for t, value in rows:
        new = evaluate_protect(
            state,
            temp_min=5.0,
            temp_max=None,
            current_cold=value,
            current_heat=None,
            forecast_min=None,
            forecast_max=None,
            outdoor=True,
        )
        if new.active and not state.active:
            since = t
        if state.active and not new.active:
            episodes.append((since, t))
            since = None
        state = new
    if state.active:
        episodes.append((since, None))
    fmt = lambda x: None if x is None else x.astimezone(TZ).strftime("%d.%m. %H:%M")  # noqa: E731
    assert [(fmt(a), fmt(b)) for a, b in episodes] == [
        ("13.10. 02:00", "13.10. 09:00"),
        ("21.10. 08:00", "21.10. 10:00"),
        ("27.10. 02:00", "27.10. 09:00"),
        ("30.10. 02:00", None),
    ]
