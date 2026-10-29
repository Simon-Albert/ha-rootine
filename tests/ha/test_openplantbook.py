"""OpenPlantbook wrapper and the flow/action paths around it (item A5)."""

from __future__ import annotations

import pytest
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.rootine import openplantbook

from .conftest import add_plant, setup_main
from .test_features import OPB_DATA, register_opb, start_flow


@pytest.fixture(autouse=True)
async def tz(hass, freezer):
    await hass.config.async_set_time_zone("Europe/Berlin")
    freezer.move_to("2026-10-29 12:00:00+01:00")


def register_failing(hass, search=None, get=None):
    """Register OpenPlantbook actions that raise (or return what is given)."""

    async def _search(call):
        if search is None:
            raise HomeAssistantError("offline")
        return search

    async def _get(call):
        if get is None:
            raise HomeAssistantError("offline")
        return get

    hass.services.async_register(
        "openplantbook", "search", _search, supports_response=SupportsResponse.ONLY
    )
    hass.services.async_register(
        "openplantbook", "get", _get, supports_response=SupportsResponse.ONLY
    )


# --- wrapper -------------------------------------------------------------------------------


async def test_without_the_integration_everything_is_empty(hass):
    assert not openplantbook.is_available(hass)
    assert await openplantbook.async_search(hass, "coffea") == {}
    assert await openplantbook.async_get(hass, "coffea arabica") is None


async def test_only_one_action_registered_is_not_available(hass):
    async def search(call):
        return {}

    hass.services.async_register(
        "openplantbook", "search", search, supports_response=SupportsResponse.ONLY
    )
    assert not openplantbook.is_available(hass)


async def test_search_strips_the_term_and_returns_strings(hass):
    calls = register_opb(hass, results={"coffea arabica": "Coffea arabica", 7: 8})
    assert await openplantbook.async_search(hass, "  coffea ") == {
        "coffea arabica": "Coffea arabica",
        "7": "8",
    }
    assert calls == [("search", {"alias": "coffea"})]


async def test_blank_search_makes_no_call(hass):
    calls = register_opb(hass)
    assert await openplantbook.async_search(hass, "   ") == {}
    assert calls == []


async def test_get_asks_for_care_data(hass):
    calls = register_opb(hass)
    assert await openplantbook.async_get(hass, "coffea arabica") == OPB_DATA
    assert calls == [("get", {"species": "coffea arabica", "include": "care"})]


async def test_failures_degrade_quietly(hass):
    register_failing(hass)
    assert await openplantbook.async_search(hass, "coffea") == {}
    assert await openplantbook.async_get(hass, "coffea arabica") is None


async def test_empty_answers(hass):
    register_failing(hass, search={}, get={})
    assert await openplantbook.async_search(hass, "coffea") == {}
    assert await openplantbook.async_get(hass, "coffea arabica") is None


# --- reconfigure flow ----------------------------------------------------------------------


async def _to_pick(hass, entry, sid):
    flow = hass.config_entries.subentries
    result = await start_flow(hass, entry, "reconfigure", sid)
    result = await flow.async_configure(result["flow_id"], {"next_step_id": "openplantbook"})
    result = await flow.async_configure(result["flow_id"], {"next_step_id": "opb_search"})
    result = await flow.async_configure(result["flow_id"], {"search": "coffea"})
    assert result["step_id"] == "opb_pick"
    return result


async def test_pick_search_again_and_none(hass):
    register_opb(hass)
    entry = await setup_main(hass)
    sid = await add_plant(hass, entry, "Kaffee")
    flow = hass.config_entries.subentries
    result = await _to_pick(hass, entry, sid)
    result = await flow.async_configure(result["flow_id"], {"species": "__again__"})
    assert result["step_id"] == "opb_search"
    result = await flow.async_configure(result["flow_id"], {"search": "coffea"})
    result = await flow.async_configure(result["flow_id"], {"species": "__none__"})
    assert result["reason"] == "reconfigure_successful"
    assert entry.runtime_data.plants[sid].profile.opb_pid is None


async def test_pick_when_details_fail(hass):
    register_failing(hass, search={"coffea arabica": "Coffea arabica"})
    entry = await setup_main(hass)
    sid = await add_plant(hass, entry, "Kaffee")
    result = await _to_pick(hass, entry, sid)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"species": "coffea arabica"}
    )
    assert result["reason"] == "opb_failed"
    assert entry.runtime_data.plants[sid].profile.opb_pid is None


async def test_refresh_in_the_menu(hass):
    register_opb(hass)
    entry = await setup_main(hass)
    sid = await add_plant(hass, entry, "Kaffee")
    flow = hass.config_entries.subentries

    async def refresh():
        result = await start_flow(hass, entry, "reconfigure", sid)
        result = await flow.async_configure(result["flow_id"], {"next_step_id": "openplantbook"})
        return await flow.async_configure(result["flow_id"], {"next_step_id": "opb_refresh"})

    assert (await refresh())["reason"] == "opb_not_linked"
    result = await _to_pick(hass, entry, sid)
    await flow.async_configure(result["flow_id"], {"species": "coffea arabica"})
    hass.services.async_remove("openplantbook", "get")
    register_failing(hass, search={})
    assert (await refresh())["reason"] == "opb_failed"
    hass.services.async_remove("openplantbook", "get")
    register_opb(hass, data=dict(OPB_DATA, watering="Alle 4 Tage"))
    assert (await refresh())["reason"] == "reconfigure_successful"
    assert entry.runtime_data.plants[sid].profile.care["watering"] == "Alle 4 Tage"


# --- action --------------------------------------------------------------------------------


async def test_refresh_action_when_details_fail(hass):
    register_opb(hass)
    entry = await setup_main(hass)
    sid = await add_plant(hass, entry, "Kaffee")
    result = await _to_pick(hass, entry, sid)
    await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"species": "coffea arabica"}
    )
    hass.services.async_remove("openplantbook", "get")
    register_failing(hass, search={})
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "rootine",
            "refresh_species",
            {"entity_id": "sensor.kaffee_care_status"},
            blocking=True,
        )
    assert entry.runtime_data.plants[sid].profile.opb_pid == "coffea arabica"
