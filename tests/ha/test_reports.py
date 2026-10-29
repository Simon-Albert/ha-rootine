"""Regression tests for report texts and counts (found in the final review)."""

import pytest
from homeassistant.core import Event

from .conftest import add_plant, setup_main


@pytest.fixture(autouse=True)
async def tz(hass, freezer):
    await hass.config.async_set_time_zone("Europe/Berlin")
    freezer.move_to("2026-10-29 12:00:00+01:00")


async def get_due(hass, **data):
    return await hass.services.async_call(
        "rootine", "get_due", data, blocking=True, return_response=True
    )


async def test_summary_text_is_german_even_with_english_ui(hass):
    # the test instance runs with language "en", so task names are "Watering"
    entry = await setup_main(hass)
    await add_plant(
        hass, entry, "Kirsche", water="ganzjährig: 3", last_done="2026-10-20", fertilize=""
    )
    result = await get_due(hass)
    assert result["text"] == "Überfällig: Kirsche gießen."
    hub = hass.states.get("sensor.rootine_due_care_tasks")
    assert hub.attributes["text"] == "Überfällig: Kirsche gießen."


async def test_text_respects_include_soon(hass):
    entry = await setup_main(hass)
    await add_plant(
        hass, entry, "Kaffee", water="ganzjährig: 6", last_done="2026-10-24", fertilize=""
    )
    assert (await get_due(hass))["text"] == "Morgen: Kaffee gießen."
    assert (await get_due(hass, include_soon=False))["text"] == "Heute ist nichts zu tun."


async def test_days_ahead_has_a_real_sentence(hass):
    entry = await setup_main(hass)
    await add_plant(
        hass, entry, "Kaffee", water="ganzjährig: 6", last_done="2026-10-26", fertilize=""
    )
    result = await get_due(hass, days_ahead=5)
    assert [i["text"] for i in result["items"]] == ["Kaffee: Gießen ist in 3 Tagen fällig."]
    assert result["text"] == "Demnächst: Kaffee gießen (in 3 Tagen)."
    assert result["count"] == 0


async def test_hub_and_get_due_count_the_same_including_protection(hass):
    entry = await setup_main(hass)
    await add_plant(
        hass,
        entry,
        "Satsuma",
        water="ganzjährig: 6",
        last_done="2026-10-28",
        fertilize="",
        limits={"temp_min": 5},
        sensors={"temperature_entity": "sensor.sat_temp"},
    )
    hass.states.async_set("sensor.sat_temp", "2")
    await hass.async_block_till_done()
    result = await get_due(hass)
    assert result["count"] == 1
    assert hass.states.get("sensor.rootine_due_care_tasks").state == "1"
    assert result["text"] == "Satsuma: zu kalt, gemessen 2 Grad."


async def test_logbook_uses_task_name(hass):
    from custom_components.rootine.logbook import async_describe_events

    entry = await setup_main(hass)
    await add_plant(hass, entry, "Kaffee", fertilize="")
    events = []
    hass.bus.async_listen("rootine_task_done", events.append)
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.kaffee_watered"}, blocking=True
    )
    await hass.async_block_till_done()
    assert events[0].data["task_name"] == "Watering"
    captured = {}
    async_describe_events(hass, lambda domain, name, fn: captured.update({name: fn}))
    out = captured["rootine_task_done"](Event("rootine_task_done", dict(events[0].data)))
    assert out["message"] == "Watering erledigt (per Knopf)"
