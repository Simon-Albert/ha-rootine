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
    (55, "raw"): ["12.04. 12:00↓", "12.04. 16:00↑", "12.04. 23:45↓", "14.04. 22:00↑"],
    (55, "median_24h"): ["13.04. 07:30↓"],
    (55, "max_24h"): ["13.04. 23:30↓", "14.04. 22:00↑"],
    (45, "raw"): ["13.04. 12:45↓", "13.04. 15:00↑", "14.04. 09:00↓", "14.04. 22:00↑"],
    (45, "median_24h"): ["14.04. 20:45↓"],
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
    "plant_a": [("03.04. 16:40", "rain"), ("21.04. 20:48", "valve")],
    "plant_b": [
        ("06.04. 07:14", "valve"),
        ("09.04. 14:45", "rain"),
        ("14.04. 21:52", "valve"),
        ("19.04. 16:22", "rain"),
    ],
}
VALVE = {
    1: ["06.04. 07:13:48", "14.04. 21:51:41"],
    2: [
        "05.04. 09:41:12",
        "14.04. 21:52:40",
        "18.04. 11:31:07",
        "18.04. 11:46:02",
        "18.04. 12:37:44",
        "21.04. 20:48:03",
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
            recorded[d.isoformat()] = daily[d]  # daily totals per local date
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


GAUGE = {
    "2030-04-02": 0.1,
    "2030-04-03": 12.8,
    "2030-04-08": 0.5,
    "2030-04-09": 8.7,
    "2030-04-10": 0.5,
    "2030-04-11": 0.9,
    "2030-04-12": 0.2,
    "2030-04-13": 0.6,
    "2030-04-14": 0.4,
    "2030-04-15": 0.7,
    "2030-04-16": 0.9,
    "2030-04-17": 0.2,
    "2030-04-18": 1.6,
    "2030-04-19": 3.9,
}


def test_rain_gauge_with_utc_reset():
    """The gauge resets at 02:00 local time; day 8 rains before the reset (oracle: GAUGE)."""
    days: dict[str, float] = {}
    base = None
    for ts, state in load_states("rain_sensor.csv", SYNTHETIC):
        days, base = rain.add_reading(days, base, ts.astimezone(TZ).date(), float(state))
    assert {d: round(mm, 2) for d, mm in days.items()} == GAUGE


# --- 7.8 ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(("plant", "expected"), [("plant_a", ["21.04. 10:12"]), ("plant_b", [])])
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
        ("11.04. 00:00", "11.04. 10:00"),
        ("20.04. 07:00", "20.04. 09:00"),
        ("25.04. 00:00", "25.04. 11:00"),
        ("30.04. 01:00", None),
    ]


@pytest.mark.parametrize(
    ("plant", "expected"), [("plant_a", [("06.04. 05:00", "07.04. 19:00")]), ("plant_b", [])]
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
