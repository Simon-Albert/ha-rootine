"""Rain sensor with a reset at midnight UTC (round 3, item A1)."""

import pytest

from .conftest import add_plant, setup_main


@pytest.fixture(autouse=True)
async def tz(hass, freezer):
    await hass.config.async_set_time_zone("Europe/Berlin")


async def test_restart_after_midnight_does_not_count_yesterdays_rain(hass, freezer):
    freezer.move_to("2026-07-02 00:30:00+02:00")
    hass.states.async_set("sensor.rain", "6.0")  # still yesterday's total
    entry = await setup_main(hass, {"rain_entity": "sensor.rain", "rain_threshold": 5.0})
    await add_plant(
        hass,
        entry,
        "Kirsche",
        location="outdoor",
        mode="rain",
        water="ganzjährig: 3",
        last_done="2026-06-28",
    )
    manager = entry.runtime_data
    assert hass.states.get("sensor.kirsche_watering").state == "overdue"
    assert manager.rain_days.get("2026-07-02", 0.0) == 0.0
    # the sensor resets at 02:00 local (00:00 UTC), then it really rains
    for clock, value in (("02:00", "0"), ("09:00", "2.5"), ("11:00", "5.5")):
        freezer.move_to(f"2026-07-02 {clock}:00+02:00")
        hass.states.async_set("sensor.rain", value)
        await hass.async_block_till_done()
    assert manager.rain_days["2026-07-02"] == 5.5
    state = hass.states.get("sensor.kirsche_watering")
    assert state.state == "ok" and state.attributes["last_source"] == "rain"


async def test_rain_before_the_utc_reset_belongs_to_today(hass, freezer):
    freezer.move_to("2026-07-01 22:00:00+02:00")
    hass.states.async_set("sensor.rain", "1.0")
    entry = await setup_main(hass, {"rain_entity": "sensor.rain"})
    manager = entry.runtime_data
    for moment, value in (
        ("2026-07-02 01:00", "4.0"),
        ("2026-07-02 02:00", "0"),
        ("2026-07-02 03:00", "0.5"),
    ):
        freezer.move_to(f"{moment}:00+02:00")
        hass.states.async_set("sensor.rain", value)
        await hass.async_block_till_done()
    assert manager.rain_days["2026-07-02"] == 3.5
    assert "2026-07-01" not in manager.rain_days  # the start value was only a base


async def test_prefill_from_daily_history(hass, freezer):
    freezer.move_to("2026-07-02 12:00:00+02:00")
    hass.states.async_set(
        "sensor.rain", "0.4", {"daily_history": [{"date": "2026-07-01", "mm": 7.2}]}
    )
    entry = await setup_main(hass, {"rain_entity": "sensor.rain"})
    assert entry.runtime_data.rain_days == {"2026-07-01": 7.2}
