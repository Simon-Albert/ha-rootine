import pytest
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from .conftest import add_plant, find_device, setup_main


@pytest.fixture(autouse=True)
async def fixed_time(hass, freezer):
    await hass.config.async_set_time_zone("Europe/Berlin")
    freezer.move_to("2026-10-29 12:00:00+01:00")


def state_of(hass, name):
    return hass.states.get(name)


async def test_load_unload(hass):
    entry = await setup_main(hass)
    assert entry.state.value == "loaded"
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state.value == "not_loaded"


async def test_plant_entities_and_device(hass):
    entry = await setup_main(hass)
    sid = await add_plant(hass, entry, "Kaffee")
    reg = er.async_get(hass)
    entities = er.async_entries_for_config_entry(reg, entry.entry_id)
    unique_ids = {e.unique_id for e in entities}
    assert {
        f"{sid}_care_status",
        f"{sid}_location",
        f"{sid}_water_status",
        f"{sid}_water_next_due",
        f"{sid}_water_due",
        f"{sid}_water_last_done",
        f"{sid}_water_done",
        f"{sid}_fertilize_status",
        f"{entry.entry_id}_due_count",
    } <= unique_ids
    device = find_device(hass, entry, sid)
    assert device.name == "Kaffee"
    assert all(e.config_subentry_id == sid for e in entities if e.unique_id.startswith(sid))


async def test_status_values(hass):
    entry = await setup_main(hass)
    await add_plant(hass, entry, "Kaffee", last_done="2026-10-25")
    # Wasser: 25.10. + 8 = 02.11. -> ok. Dünger: Pause (01.10. bis ...) -> Plan endet 30.09.
    assert hass.states.get("sensor.kaffee_watering").state == "ok"
    assert hass.states.get("sensor.kaffee_fertilizing").state == "rest"
    assert hass.states.get("sensor.kaffee_care_status").state == "ok"
    assert hass.states.get("select.kaffee_location").state == "indoor"
    assert hass.states.get("sensor.rootine_due_care_tasks").state == "0"


async def test_overdue_button_and_date(hass):
    entry = await setup_main(hass)
    sid = await add_plant(hass, entry, "Kirsche", last_done="2026-10-10")
    assert hass.states.get("sensor.kirsche_watering").state == "overdue"
    assert hass.states.get("binary_sensor.kirsche_watering_due").state == "on"
    assert hass.states.get("sensor.rootine_due_care_tasks").state == "1"

    events = []
    hass.bus.async_listen("rootine_task_done", lambda e: events.append(e.data))
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.kirsche_watered"}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get("sensor.kirsche_watering").state == "ok"
    assert hass.states.get("date.kirsche_watering_last_done").state == "2026-10-29"
    assert events and events[0]["task"] == "water" and events[0]["source"] == "button"
    attrs = hass.states.get("sensor.kirsche_watering").attributes
    assert attrs["last_source"] == "button"

    await hass.services.async_call(
        "date",
        "set_value",
        {"entity_id": "date.kirsche_watering_last_done", "date": "2026-10-20"},
        blocking=True,
    )
    assert hass.states.get("sensor.kirsche_watering").state == "overdue"
    assert hass.states.get("sensor.kirsche_watering").attributes["last_source"] == "date_edit"
    assert entry.runtime_data.plants[sid].log[-1]["source"] == "date_edit"


async def test_location_select_no_reload(hass):
    entry = await setup_main(hass)
    await add_plant(hass, entry, "Kaffee")
    manager = entry.runtime_data
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.kaffee_location", "option": "outdoor"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert entry.runtime_data is manager  # kein Neuladen
    assert hass.states.get("select.kaffee_location").state == "outdoor"
    assert hass.states.get("sensor.kaffee_care_status").attributes["location"] == "outdoor"


async def test_midnight_recompute(hass, freezer):
    entry = await setup_main(hass)
    await add_plant(hass, entry, "Kaffee", last_done="2026-10-22", water="ganzjährig: 8")
    assert hass.states.get("sensor.kaffee_watering").state == "soon"  # fällig 30.10.
    freezer.move_to("2026-10-30 00:00:10+01:00")
    async_fire_time_changed(hass, dt_util.now())
    await hass.async_block_till_done()
    assert hass.states.get("sensor.kaffee_watering").state == "due"


async def test_restart_keeps_state(hass, hass_storage):
    entry = await setup_main(hass)
    await add_plant(hass, entry, "Kaffee", last_done="2026-10-20", water="ganzjährig: 8")
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.kaffee_watered"}, blocking=True
    )
    await hass.config_entries.async_unload(entry.entry_id)
    assert "rootine" in hass_storage
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("date.kaffee_watering_last_done").state == "2026-10-29"
    assert hass.states.get("sensor.kaffee_watering").state == "ok"


async def test_delete_plant(hass, hass_storage):
    entry = await setup_main(hass)
    sid = await add_plant(hass, entry, "Kaffee")
    assert hass.states.get("sensor.kaffee_care_status")
    hass.config_entries.async_remove_subentry(entry, sid)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.kaffee_care_status") is None
    assert find_device(hass, entry, sid) is None
    await hass.config_entries.async_unload(entry.entry_id)
    assert sid not in hass_storage["rootine"]["data"]["plants"]
