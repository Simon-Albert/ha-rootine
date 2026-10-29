"""Plan section 7 against the synthetic fixtures (always present, run in CI).

Expected values come from the independent oracle tests/fixtures_synthetic/reference.py, not from
the integration. Regenerate data with scripts/make_synthetic_fixtures.py and the expectations with
the oracle; never adapt a constant to make a test pass.
"""

import csv
import itertools
from datetime import date, datetime, timedelta

import pytest

from custom_components.rootine.logic import moisture as m
from custom_components.rootine.logic import rain, valve
from custom_components.rootine.logic.climate import Protect, evaluate_protect
from custom_components.rootine.logic.due import TaskState, compute_due
from custom_components.rootine.logic.schedule import parse_schedule

from ..conftest import SYNTHETIC, TZ, load_series, load_states


def dt(month, day, hour=0, minute=0, second=0):
    return datetime(2030, month, day, hour, minute, second, tzinfo=TZ)


def fmt(ts):
    return ts.astimezone(TZ).strftime("%d.%m. %H:%M")


def series(name):
    return load_series(f"{name}_moisture.csv", SYNTHETIC)


def rain_days():
    with (SYNTHETIC / "rain_daily.csv").open(newline="") as handle:
        return {date.fromisoformat(r["date"]): float(r["mm"]) for r in csv.DictReader(handle)}


# --- 7.4 ---------------------------------------------------------------------------------------

EVALUATION = {
    (55, "raw"): ["12.04. 11:45↓", "12.04. 16:15↑", "12.04. 23:45↓"],
    (55, "median_24h"): ["13.04. 07:00↓"],
    (55, "max_24h"): ["13.04. 23:30↓"],
    (45, "raw"): ["13.04. 12:30↓", "13.04. 15:15↑", "14.04. 07:00↓"],
    (45, "median_24h"): ["14.04. 18:45↓"],
    (45, "max_24h"): [],
}


@pytest.mark.parametrize(("threshold", "method"), list(EVALUATION))
def test_evaluation_crossings(threshold, method):
    data = series("plant_b")
    out, previous, t = [], None, dt(4, 11)
    while t < dt(4, 14, 23, 20):
        value = m.evaluate(data, t, method)
        below = value is not None and value < threshold
        if previous is not None and below != previous:
            out.append(fmt(t) + ("↓" if below else "↑"))
        previous, t = below, t + timedelta(minutes=15)
    assert out == EVALUATION[(threshold, method)]


# --- 7.5 / 7.6 / 7.6.1 -------------------------------------------------------------------------

WATER = {
    "plant_a": [("03.04. 18:05", "rain"), ("21.04. 22:07", "valve")],
    "plant_b": [
        ("06.04. 13:37", "valve"),
        ("09.04. 10:45", "rain"),
        ("14.04. 23:25", "valve"),
        ("19.04. 18:51", "rain"),
    ],
}
VALVE = {
    1: ["06.04. 13:36:56", "14.04. 23:25:02"],
    2: [
        "05.04. 13:58:33",
        "14.04. 23:25:31",
        "18.04. 15:09:19",
        "18.04. 15:24:11",
        "18.04. 16:15:14",
        "21.04. 22:07:07",
    ],
}
CHANNEL = {"plant_a": 2, "plant_b": 1}


@pytest.mark.parametrize("channel", [1, 2])
def test_valve_events(channel):
    events = valve.valve_events(load_states(f"valve_{channel}.csv", SYNTHETIC))
    assert [e.start.astimezone(TZ).strftime("%d.%m. %H:%M:%S") for e in events] == VALVE[channel]


@pytest.mark.parametrize("plant", ["plant_a", "plant_b"])
def test_water_events_and_classification(plant):
    events = m.detect_water_events(series(plant))
    runs = valve.valve_events(load_states(f"valve_{CHANNEL[plant]}.csv", SYNTHETIC))
    days = {d.isoformat(): mm for d, mm in rain_days().items()}
    got = [
        (
            fmt(e.ts),
            rain.classify_water_event(
                valve_match=valve.valve_matches(runs, e.ts),
                rain_today_and_yesterday=rain.recent_rain(days, e.ts.date()),
            ),
        )
        for e in events
    ]
    assert got == WATER[plant]


# --- 7.7 ---------------------------------------------------------------------------------------


def test_rain_mode():
    daily = rain_days()
    schedule = parse_schedule("ganzjährig: 3")
    state = TaskState(dt(4, 1, 20), "setup", rain_at_done=daily[date(2030, 4, 1)])
    recorded: dict[str, float] = {}
    resets, statuses = [], {}
    day = date(2030, 4, 2)
    while day <= date(2030, 4, 29):
        for d in (day - timedelta(days=1), day):
            recorded = rain.record_rain(recorded, d, daily[d])
        if rain.rain_resets(recorded, day, state.last_done, state.rain_at_done):
            resets.append(day.strftime("%d.%m."))
            state = TaskState(
                datetime(day.year, day.month, day.day, 0, 5, tzinfo=TZ),
                "rain",
                rain_at_done=daily[day],
            )
        result = compute_due(day, state, schedule)
        statuses[day.strftime("%d.%m.")] = (result.status.value, result.days)
        day += timedelta(days=1)
    assert resets == ["03.04.", "09.04.", "19.04."]
    expected = {
        "05.04.": ("soon", 1),
        "07.04.": ("overdue", -1),
        "10.04.": ("ok", 2),
        "13.04.": ("overdue", -1),
        "18.04.": ("overdue", -6),
        "20.04.": ("ok", 2),
    }
    assert {d: statuses[d] for d in expected} == expected


# --- 7.8 ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(("plant", "expected"), [("plant_a", ["21.04. 08:33"]), ("plant_b", [])])
def test_implausible_drop(plant, expected):
    valid = m.valid_samples(series(plant))
    drops = [fmt(b[0]) for a, b in itertools.pairwise(valid) if m.is_implausible_drop(a[1], b[1])]
    assert drops == expected


@pytest.mark.parametrize("plant", ["plant_a", "plant_b"])
def test_gaps_never_count_as_stale(plant):
    valid = m.valid_samples(series(plant))
    longest = max(b[0] - a[0] for a, b in itertools.pairwise(valid))
    assert timedelta(hours=29) < longest <= timedelta(hours=31)  # gap exists, but below 36 h
    for a, b in itertools.pairwise(valid):
        assert not m.is_stale(b[0], a[0])


def test_unavailable_phases_present():
    raw = series("plant_a")
    assert sum(1 for _, v in raw if v is None) >= 5


# --- 7.10 / 7.11 -------------------------------------------------------------------------------


def test_cold_episodes():
    with (SYNTHETIC / "plant_a_temperature_hourly.csv").open(newline="") as handle:
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
            episodes.append((fmt(since), fmt(t)))
        state = new
    if state.active:
        episodes.append((fmt(since), None))
    assert episodes == [
        ("12.04. 01:00", "12.04. 10:00"),
        ("21.04. 08:00", "21.04. 10:00"),
        ("26.04. 00:00", "26.04. 10:00"),
        ("30.04. 02:00", None),
    ]


@pytest.mark.parametrize(
    ("plant", "expected"), [("plant_a", [("06.04. 07:00", "07.04. 23:00")]), ("plant_b", [])]
)
def test_too_wet(plant, expected):
    data = series(plant)
    state, on, spans = m.WetState(), None, []
    t = dt(4, 1, 12)
    while t < dt(4, 30, 9):
        new = m.update_too_wet(state, m.evaluate(data, t), t, 95)
        if new.active and not state.active:
            on = t
        if state.active and not new.active:
            spans.append((fmt(on), fmt(t)))
        state = new
        t += timedelta(hours=1)
    assert spans == expected
