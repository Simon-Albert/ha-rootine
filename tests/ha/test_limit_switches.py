"""Limits can be switched off directly at the entity and come back with their value (A4)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.core import SupportsResponse
from homeassistant.util import dt as dt_util

from custom_components.rootine.logic.moisture import WetState

from .conftest import add_plant, setup_main


@pytest.fixture(autouse=True)
async def tz(hass, freezer):
    await hass.config.async_set_time_zone("Europe/Berlin")
    freezer.move_to("2026-10-29 12:00:00+01:00")


async def _switch(hass, entity_id, on):
    await hass.services.async_call(
        "switch", "turn_on" if on else "turn_off", {"entity_id": entity_id}, blocking=True
    )
    await hass.async_block_till_done()


async def test_switch_off_keeps_the_value_for_later(hass):
    entry = await setup_main(hass)
    sid = await add_plant(hass, entry, "Kaffee", limits={"temp_min": 10, "temp_max": 30})
    settings = entry.runtime_data.plants[sid].settings
    assert hass.states.get("switch.kaffee_cold_protection").state == "on"
    await _switch(hass, "switch.kaffee_cold_protection", False)
    assert settings.temp_min is None
    assert hass.states.get("switch.kaffee_cold_protection").state == "off"
    assert hass.states.get("number.kaffee_cold_protection_below").state == "unknown"
    assert settings.temp_max == 30  # the other limit stays
    await _switch(hass, "switch.kaffee_cold_protection", True)
    assert settings.temp_min == 10
    assert settings.limit_memory == {}


async def test_switch_on_without_a_remembered_value_uses_a_default(hass):
    entry = await setup_main(hass)
    sid = await add_plant(hass, entry, "Kaffee")
    assert hass.states.get("switch.kaffee_heat_protection").state == "off"
    await _switch(hass, "switch.kaffee_heat_protection", True)
    assert entry.runtime_data.plants[sid].settings.temp_max == 32.0
    await _switch(hass, "switch.kaffee_cold_protection", True)
    assert entry.runtime_data.plants[sid].settings.temp_min == 5.0


async def test_setting_the_number_switches_the_limit_on(hass):
    entry = await setup_main(hass)
    sid = await add_plant(hass, entry, "Kaffee")
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.kaffee_heat_protection_above", "value": 29},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert entry.runtime_data.plants[sid].settings.temp_max == 29
    assert hass.states.get("switch.kaffee_heat_protection").state == "on"


async def test_too_wet_switch_only_with_sensor_and_clears_the_warning(hass):
    entry = await setup_main(hass)
    await add_plant(hass, entry, "Ohne")
    assert hass.states.get("switch.ohne_too_wet_warning") is None
    hass.states.async_set("sensor.k_moisture", "95", {"device_class": "moisture"})
    sid = await add_plant(
        hass,
        entry,
        "Kaffee",
        sensors={"moisture_entity": "sensor.k_moisture"},
        limits={"moisture_max": 80},
    )
    plant = entry.runtime_data.plants[sid]
    plant.wet = WetState(True, dt_util.now() - timedelta(hours=50))
    await _switch(hass, "switch.kaffee_too_wet_warning", False)
    assert plant.settings.moisture_max is None
    assert not plant.wet.active
    assert hass.states.get("binary_sensor.kaffee_too_wet").state == "off"
    await _switch(hass, "switch.kaffee_too_wet_warning", True)
    assert plant.settings.moisture_max == 80


async def test_switched_off_limit_survives_a_restart(hass, hass_storage):
    entry = await setup_main(hass)
    sid = await add_plant(hass, entry, "Kaffee", limits={"temp_min": 10})
    await _switch(hass, "switch.kaffee_cold_protection", False)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    settings = entry.runtime_data.plants[sid].settings
    assert settings.temp_min is None and settings.limit_memory == {"temp_min": 10}
    await _switch(hass, "switch.kaffee_cold_protection", True)
    assert entry.runtime_data.plants[sid].settings.temp_min == 10


async def test_switching_on_fetches_the_forecast_at_once(hass):
    calls = []

    async def forecasts(call):
        calls.append(call.data["entity_id"])
        now = dt_util.now()
        return {
            call.data["entity_id"]: {
                "forecast": [
                    {"datetime": (now + timedelta(hours=3)).isoformat(), "temperature": 1.0}
                ]
            }
        }

    hass.services.async_register(
        "weather", "get_forecasts", forecasts, supports_response=SupportsResponse.ONLY
    )
    entry = await setup_main(hass, {"weather_entity": "weather.home"})
    await add_plant(hass, entry, "Satsuma", location="outdoor")
    assert calls == []  # no limits: no forecast needed
    await _switch(hass, "switch.satsuma_cold_protection", True)
    assert calls == ["weather.home"]
    assert hass.states.get("binary_sensor.satsuma_protection_needed").state == "on"
