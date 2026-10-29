"""Large attributes must not end up in the recorder database (review item 4)."""

import pytest
from homeassistant.components.recorder import Recorder
from homeassistant.components.recorder.history import get_significant_states
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from .conftest import add_plant, setup_main


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(recorder_mock, enable_custom_integrations):
    """The recorder has to start before hass; override the conftest fixture."""
    yield


async def test_large_attributes_are_not_recorded(recorder_mock: Recorder, hass):
    await hass.config.async_set_time_zone("Europe/Berlin")
    start = dt_util.utcnow()
    entry = await setup_main(hass)
    await add_plant(hass, entry, "Kaffee", water="ganzjährig: 3", last_done="2026-10-20")
    await async_wait_recording_done(hass)
    care, hub = "sensor.kaffee_care_status", "sensor.rootine_due_care_tasks"
    assert {"profile", "log", "tasks"} <= set(
        hass.states.get(care).attributes
    )  # live state keeps them
    states = await recorder_mock.async_add_executor_job(
        get_significant_states, hass, start, None, [care, hub], None, True, False
    )
    recorded_care = states[care][-1].attributes
    recorded_hub = states[hub][-1].attributes
    for key in ("profile", "log", "tasks", "warnings", "moisture"):
        assert key not in recorded_care
    assert "location" in recorded_care  # small, useful attributes are still recorded
    for key in ("items", "text"):
        assert key not in recorded_hub
