"""Replay of fixture data through Home Assistant (plan M5 acceptance).

Runs against the synthetic fixtures (always, also in CI). The replay of the anonymized real data
lives in a local, git-ignored test file next to this one and uses the same helpers.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from pytest_homeassistant_custom_component.common import async_fire_time_changed

from ..conftest import SYNTHETIC, TZ
from .conftest import add_plant, setup_main


@dataclass(frozen=True)
class Dataset:
    directory: Path
    plant_a: str  # file prefix of the plant on valve 2
    plant_b: str  # file prefix of the plant on valve 1
    water_a: list[tuple[str, str]]
    water_b: list[tuple[str, str]]
    drop_day: str  # day of the implausible drop of plant a, ended by the watering that evening
    wet_days: set[str]
    rain: dict[str, float] | None = None  # expected rain per local date (from the gauge)


SYNTHETIC_DATA = Dataset(
    SYNTHETIC,
    "plant_a",
    "plant_b",
    [("03.04. 16:40", "rain"), ("21.04. 20:48", "valve")],
    [
        ("06.04. 07:14", "valve"),
        ("09.04. 14:45", "rain"),
        ("14.04. 21:52", "valve"),
        ("19.04. 16:22", "rain"),
    ],
    "21.04.",
    {"06.04.", "07.04."},
    # oracle: reference.py, rain from the gauge that resets at midnight UTC
    {
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
    },
)


def _rows(path: Path) -> list[tuple[datetime, str]]:
    with path.open(newline="") as handle:
        return [
            (datetime.fromisoformat(r["timestamp"]).astimezone(TZ), r["state"])
            for r in csv.DictReader(handle)
        ]


def _timeline(data: Dataset) -> list[tuple[datetime, str, str]]:
    events: list[tuple[datetime, str, str]] = []
    for name, entity in (
        (f"{data.plant_a}_moisture.csv", "sensor.a_moisture"),
        (f"{data.plant_b}_moisture.csv", "sensor.b_moisture"),
        ("valve_1.csv", "switch.valve_1"),
        ("valve_2.csv", "switch.valve_2"),
    ):
        events += [(ts, entity, state) for ts, state in _rows(data.directory / name)]
    gauge = data.directory / "rain_sensor.csv"
    if gauge.exists():  # cumulative gauge as recorded (resets at midnight UTC)
        events += [(ts, "sensor.rain", state) for ts, state in _rows(gauge)]
    else:
        with (data.directory / "rain_daily.csv").open(newline="") as handle:
            for row in csv.DictReader(handle):
                day = datetime.fromisoformat(row["date"]).replace(tzinfo=TZ)
                # a daily-total sensor: reset, then the day's rain as one increment
                events.append((day.replace(hour=0, minute=5), "sensor.rain", "0"))
                events.append((day.replace(hour=0, minute=6), "sensor.rain", row["mm"]))
    events.sort(key=lambda e: e[0])
    return events


def _minute(ts: str) -> str:
    return datetime.fromisoformat(ts).astimezone(TZ).strftime("%d.%m. %H:%M")


async def _replay(hass, freezer, data: Dataset) -> None:
    await hass.config.async_set_time_zone("Europe/Berlin")
    timeline = _timeline(data)
    start = timeline[0][0]
    freezer.move_to(start)
    first_values = {}
    for ts, entity, state in timeline:
        if ts <= start + timedelta(minutes=1):
            first_values[entity] = state
    for entity, state in first_values.items():
        hass.states.async_set(entity, state)
    first_day = start.date().isoformat()
    entry = await setup_main(hass, {"rain_entity": "sensor.rain"})
    sid_a = await add_plant(
        hass,
        entry,
        "A",
        location="outdoor",
        mode="sensor",
        water="",
        sensors={"moisture_entity": "sensor.a_moisture", "valve_entity": "switch.valve_2"},
        water_extra={"moisture_threshold": 65, "valve_counts_as_watering": False},
        limits={"moisture_max": 95},
        last_done=first_day,
    )
    sid_b = await add_plant(
        hass,
        entry,
        "B",
        location="outdoor",
        mode="sensor",
        water="",
        sensors={"moisture_entity": "sensor.b_moisture", "valve_entity": "switch.valve_1"},
        water_extra={"moisture_threshold": 50, "valve_counts_as_watering": False},
        fertilize="",
        last_done=first_day,
    )
    manager = entry.runtime_data
    reasons: dict[str, set[str]] = {"a": set(), "b": set()}
    wet_days: set[str] = set()
    drop_span: list[str] = []
    last_hour = start.replace(minute=0, second=0, microsecond=0)

    def observe(now: datetime) -> None:
        for tag, sid in (("a", sid_a), ("b", sid_b)):
            warning = manager.plants[sid].warnings.get("sensor_check")
            if warning:
                reasons[tag].add(warning["reason"])
        if "too_wet" in manager.plants[sid_a].warnings:
            wet_days.add(now.strftime("%d.%m."))
        has_drop = manager.plants[sid_a].warnings.get("sensor_check", {}).get("reason") == "drop"
        if has_drop and not drop_span:
            drop_span.append(_minute(now.isoformat()))
        if not has_drop and len(drop_span) == 1:
            drop_span.append(_minute(now.isoformat()))

    for ts, entity, state in timeline:
        if ts <= start + timedelta(minutes=1):
            continue
        while last_hour + timedelta(hours=1) < ts:
            last_hour += timedelta(hours=1)
            freezer.move_to(last_hour)
            async_fire_time_changed(hass, last_hour)
            await hass.async_block_till_done()
            observe(last_hour)
        freezer.move_to(ts)
        hass.states.async_set(entity, state)
        await hass.async_block_till_done()
        observe(ts)

    def events(sid):
        return [
            (_minute(e["ts"]), e["source"])
            for e in manager.plants[sid].log
            if e["source"] in ("sensor", "valve", "rain") and e["task"] == "water"
        ]

    assert events(sid_a) == data.water_a
    assert events(sid_b) == data.water_b
    # plausibility: only the pulled sensor, ended by the watering that evening; never "stale"
    assert reasons["a"] == {"drop"}
    assert drop_span[0].startswith(data.drop_day) and drop_span[1].startswith(data.drop_day)
    assert reasons["b"] == set()
    assert wet_days == data.wet_days
    if data.rain is not None:
        assert {d: round(mm, 2) for d, mm in manager.rain_days.items() if mm} == data.rain


async def test_replay_synthetic(hass, freezer):
    await _replay(hass, freezer, SYNTHETIC_DATA)
