"""Fixtures for the tests with pytest-homeassistant-custom-component."""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.rootine.const import DOMAIN, SUBENTRY_PLANT


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


async def setup_main(hass: HomeAssistant, options: dict[str, Any] | None = None) -> ConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, title="Rootine", data={}, options=options or {})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def add_plant(
    hass: HomeAssistant,
    entry: ConfigEntry,
    name: str = "Kaffee",
    *,
    water: str = "01.04.–30.09.: 6\n01.10.–31.03.: 8",
    fertilize: str = "01.03.–30.09.: 21",
    last_done: str = "2026-10-25",
    profile: dict[str, Any] | None = None,
    location: str = "indoor",
    sensors: dict[str, Any] | None = None,
    mode: str = "timer",
    water_extra: dict[str, Any] | None = None,
    limits: dict[str, Any] | None = None,
) -> str:
    """Create a plant through the real flow. Returns the subentry id."""
    flow = hass.config_entries.subentries
    result = await flow.async_init((entry.entry_id, SUBENTRY_PLANT), context={"source": "user"})
    result = await flow.async_configure(result["flow_id"], {"name": name, "location": location})
    result = await flow.async_configure(result["flow_id"], profile or {})
    result = await flow.async_configure(result["flow_id"], sensors or {})
    result = await flow.async_configure(
        result["flow_id"],
        {"mode": mode, "schedule_text": water, "last_done": last_done, **(water_extra or {})},
    )
    assert result["type"] == "form" and result["step_id"] == "fertilize", result
    result = await flow.async_configure(
        result["flow_id"], {"schedule_text": fertilize, "last_done": last_done}
    )
    result = await flow.async_configure(result["flow_id"], limits or {})
    assert result["type"] == "create_entry", result
    await hass.async_block_till_done()
    return next(sid for sid, s in entry.subentries.items() if s.data["name"] == name)


def find_device(hass: HomeAssistant, entry: ConfigEntry, subentry_id: str):
    """Device of a plant, via the lookup helper that works in every HA version."""
    from homeassistant.helpers import device_registry as dr

    registry = dr.async_get(hass)
    return next(
        (
            d
            for d in dr.async_entries_for_config_entry(registry, entry.entry_id)
            if (DOMAIN, subentry_id) in d.identifiers
        ),
        None,
    )
