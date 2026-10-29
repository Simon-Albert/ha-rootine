"""Replay of fixture data through Home Assistant (plan M5 acceptance).

Runs against the synthetic fixtures always (CI) and against the anonymized real data when those
files are present locally.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from ..conftest import FIXTURES, SYNTHETIC, TZ
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


SYNTHETIC_DATA = Dataset(
    SYNTHETIC,
    "plant_a",
    "plant_b",
    [("03.04. 18:05", "rain"), ("21.04. 22:07", "valve")],
    [
        ("06.04. 13:37", "valve"),
        ("09.04. 10:45", "rain"),
        ("14.04. 23:25", "valve"),
        ("19.04. 18:51", "rain"),
    ],
    "21.04.",
    {"06.04.", "07.04."},
)
REAL_DATA = Dataset(
    FIXTURES,
    "satsuma",
    "nektarine",
    [("02.10. 18:05", "rain"), ("21.10. 22:07", "valve")],
    [
        ("06.10. 13:37", "valve"),
        ("09.10. 10:45", "rain"),
        ("14.10. 23:25", "valve"),
        ("19.10. 18:51", "rain"),
    ],
    "21.10.",
    {"05.10.", "06.10.", "07.10."},
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


async def test_replay_synthetic(hass, freezer):
    await _replay(hass, freezer, SYNTHETIC_DATA)


async def test_replay_real_data(hass, freezer):
    if not (FIXTURES / "satsuma_moisture.csv").exists():
        pytest.skip("anonymized real data only available locally")
    await _replay(hass, freezer, REAL_DATA)
