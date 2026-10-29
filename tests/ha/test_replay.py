"""Replay of the anonymized real fixtures through Home Assistant (plan M5 acceptance)."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta

import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from ..conftest import FIXTURES, TZ
from .conftest import add_plant, setup_main

START = datetime(2025, 9, 30, 10, 23, 53, tzinfo=TZ)


def _rows(name: str) -> list[tuple[datetime, str]]:
    with (FIXTURES / name).open(newline="") as handle:
        return [
            (datetime.fromisoformat(r["timestamp"]).astimezone(TZ), r["state"])
            for r in csv.DictReader(handle)
        ]


def _timeline() -> list[tuple[datetime, str, str]]:
    events: list[tuple[datetime, str, str]] = []
    for name, entity in (
        ("satsuma_moisture.csv", "sensor.sat_moisture"),
        ("nektarine_moisture.csv", "sensor.nek_moisture"),
        ("valve_1.csv", "switch.valve_1"),
        ("valve_2.csv", "switch.valve_2"),
    ):
        events += [(ts, entity, state) for ts, state in _rows(name)]
    with (FIXTURES / "rain_daily.csv").open(newline="") as handle:
        for row in csv.DictReader(handle):
            day = datetime.fromisoformat(row["date"]).replace(tzinfo=TZ)
            events.append((day.replace(hour=0, minute=5), "sensor.rain", row["mm"]))
    events.sort(key=lambda e: e[0])
    return events


def _minute(ts: str) -> str:
    return datetime.fromisoformat(ts).astimezone(TZ).strftime("%d.%m. %H:%M")


async def test_replay_events_and_warnings(hass, freezer):
    await hass.config.async_set_time_zone("Europe/Berlin")
    freezer.move_to(START)
    timeline = _timeline()
    first_values = {}
    for ts, entity, state in timeline:
        if ts <= START + timedelta(minutes=1):
            first_values[entity] = state
    for entity, state in first_values.items():
        hass.states.async_set(entity, state)
    entry = await setup_main(hass, {"rain_entity": "sensor.rain"})
    sat = await add_plant(
        hass,
        entry,
        "Satsuma",
        location="outdoor",
        mode="sensor",
        water="",
        sensors={"moisture_entity": "sensor.sat_moisture", "valve_entity": "switch.valve_2"},
        water_extra={"moisture_threshold": 65, "valve_counts_as_watering": False},
        limits={"moisture_max": 95},
        last_done="2025-09-30",
    )
    nek = await add_plant(
        hass,
        entry,
        "Nektarine",
        location="outdoor",
        mode="sensor",
        water="",
        sensors={"moisture_entity": "sensor.nek_moisture", "valve_entity": "switch.valve_1"},
        water_extra={"moisture_threshold": 50, "valve_counts_as_watering": False},
        fertilize="",
        last_done="2025-09-30",
    )
    manager = entry.runtime_data
    reasons: dict[str, set[str]] = {"sat": set(), "nek": set()}
    wet_days: set[str] = set()
    drop_span: list[str] = []
    last_hour = START.replace(minute=0, second=0, microsecond=0)

    async def observe(now: datetime) -> None:
        for tag, sid in (("sat", sat), ("nek", nek)):
            warning = manager.plants[sid].warnings.get("sensor_check")
            if warning:
                reasons[tag].add(warning["reason"])
        if "too_wet" in manager.plants[sat].warnings:
            wet_days.add(now.strftime("%d.%m."))
        has_drop = manager.plants[sat].warnings.get("sensor_check", {}).get("reason") == "drop"
        if has_drop and not drop_span:
            drop_span.append(_minute(now.isoformat()))
        if not has_drop and drop_span and len(drop_span) == 1:
            drop_span.append(_minute(now.isoformat()))

    for ts, entity, state in timeline:
        if ts <= START + timedelta(minutes=1):
            continue
        while last_hour + timedelta(hours=1) < ts:
            last_hour += timedelta(hours=1)
            freezer.move_to(last_hour)
            async_fire_time_changed(hass, last_hour)
            await hass.async_block_till_done()
            await observe(last_hour)
        freezer.move_to(ts)
        hass.states.async_set(entity, state)
        await hass.async_block_till_done()
        await observe(ts)

    def events(sid):
        return [
            (_minute(e["ts"]), e["source"])
            for e in manager.plants[sid].log
            if e["source"] in ("sensor", "valve", "rain") and e["task"] == "water"
        ]

    assert events(sat) == [("02.10. 18:05", "rain"), ("21.10. 22:07", "valve")]
    assert events(nek) == [
        ("06.10. 13:37", "valve"),
        ("09.10. 10:45", "rain"),
        ("14.10. 23:25", "valve"),
        ("19.10. 18:51", "rain"),
    ]
    # plausibility: only the 20.10. drop, ended by the watering at 22:07; never "stale"
    assert reasons["sat"] == {"drop"}
    assert drop_span[0].startswith("21.10. 08:") and drop_span[1].startswith("21.10. 22:")
    assert reasons["nek"] == set()
    # too wet: only between 04.10. and 06.10.
    assert wet_days == {"05.10.", "06.10.", "07.10."}


@pytest.fixture(autouse=True)
def _need_fixtures():
    if not (FIXTURES / "satsuma_moisture.csv").exists():
        pytest.skip("fixtures missing")
