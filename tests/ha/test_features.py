"""Feature tests: OpenPlantbook, rain, protection, sensors, actions, to-do, diagnostics."""

from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.components.todo import DOMAIN as TODO_DOMAIN
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.rootine.const import SUBENTRY_PLANT

from .conftest import add_plant, setup_main

OPB_DATA = {
    "pid": "coffea arabica",
    "display_pid": "Coffea arabica",
    "alias": "Arabica-Kaffee",
    "image_url": "https://opb-img.plantbook.io/coffea_arabica.jpg?v=1",
    "common_names": [{"name": "Kaffeestrauch", "language_code": "de"}],
    "watering": "Alle 5-7 Tage",
    "fertilization": "Alle 2-4 Wochen",
    "min_temp": 15,
    "max_temp": 27,
}


@pytest.fixture(autouse=True)
async def tz(hass, freezer):
    await hass.config.async_set_time_zone("Europe/Berlin")
    freezer.move_to("2026-10-29 12:00:00+01:00")


def register_opb(hass, results=None, data=None):
    calls = []

    async def search(call):
        calls.append(("search", dict(call.data)))
        return results if results is not None else {"coffea arabica": "Coffea arabica"}

    async def get(call):
        calls.append(("get", dict(call.data)))
        return data if data is not None else OPB_DATA

    hass.services.async_register(
        "openplantbook", "search", search, supports_response=SupportsResponse.ONLY
    )
    hass.services.async_register(
        "openplantbook", "get", get, supports_response=SupportsResponse.ONLY
    )
    return calls


async def start_flow(hass, entry, source="user", subentry_id=None):
    context = {"source": source}
    if subentry_id:
        context["subentry_id"] = subentry_id
    return await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_PLANT), context=context
    )


# --- OpenPlantbook -------------------------------------------------------------------------


async def test_create_with_openplantbook(hass):
    calls = register_opb(hass)
    entry = await setup_main(hass)
    flow = hass.config_entries.subentries
    result = await start_flow(hass, entry)
    assert "search" in result["data_schema"].schema
    result = await flow.async_configure(
        result["flow_id"], {"name": "Kaffee", "location": "indoor", "search": "coffea"}
    )
    assert result["step_id"] == "species"
    result = await flow.async_configure(result["flow_id"], {"species": "coffea arabica"})
    assert result["step_id"] == "profile"
    suggested = {
        str(k): k.description["suggested_value"]
        for k in result["data_schema"].schema
        if k.description and "suggested_value" in k.description
    }
    assert suggested["common_name"] == "Kaffeestrauch"
    assert suggested["care_watering"] == "Alle 5-7 Tage"
    # edit one field -> becomes manual
    result = await flow.async_configure(
        result["flow_id"],
        {
            "common_name": "Mein Kaffee",
            "species": "Coffea arabica",
            "care_watering": "Alle 5-7 Tage",
            "care_fertilization": "Alle 2-4 Wochen",
        },
    )
    assert result["step_id"] == "sensors"
    result = await flow.async_configure(result["flow_id"], {})
    result = await flow.async_configure(
        result["flow_id"],
        {"mode": "timer", "schedule_text": "ganzjährig: 6", "last_done": "2026-10-25"},
    )
    assert result["description_placeholders"]["care"] == "Alle 2-4 Wochen"
    result = await flow.async_configure(
        result["flow_id"], {"schedule_text": "", "last_done": "2026-10-25"}
    )
    assert result["step_id"] == "limits"
    assert result["description_placeholders"]["hint"] == "15–27 °C"
    result = await flow.async_configure(result["flow_id"], {})
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    sid = next(iter(entry.subentries))
    profile = entry.runtime_data.plants[sid].profile
    assert profile.opb_pid == "coffea arabica"
    assert profile.common_name == "Mein Kaffee"
    assert profile.manual_fields == {"common_name"}
    assert profile.opb_image_url.startswith("https://opb-img")
    assert (
        hass.states.get("sensor.kaffee_care_status")
        .attributes["entity_picture"]
        .startswith("https://opb-img")
    )
    assert ("get", {"species": "coffea arabica", "include": "care"}) in calls


async def test_openplantbook_not_installed_hides_search(hass):
    entry = await setup_main(hass)
    result = await start_flow(hass, entry)
    assert "search" not in result["data_schema"].schema


async def test_nothing_found_and_continue_without(hass):
    register_opb(hass, results={})
    entry = await setup_main(hass)
    flow = hass.config_entries.subentries
    result = await start_flow(hass, entry)
    result = await flow.async_configure(
        result["flow_id"], {"name": "Nektarine", "location": "outdoor", "search": "nectarine"}
    )
    assert result["step_id"] == "species"
    result = await flow.async_configure(result["flow_id"], {"species": "__none__"})
    assert result["step_id"] == "profile"


async def test_search_again(hass):
    register_opb(hass)
    entry = await setup_main(hass)
    flow = hass.config_entries.subentries
    result = await start_flow(hass, entry)
    result = await flow.async_configure(
        result["flow_id"], {"name": "A", "location": "outdoor", "search": "x"}
    )
    result = await flow.async_configure(result["flow_id"], {"species": "__again__"})
    assert result["step_id"] == "search"
    result = await flow.async_configure(result["flow_id"], {"search": "coffea"})
    assert result["step_id"] == "species"


async def test_reconfigure_link_refresh_unlink_keeps_manual(hass):
    entry = await setup_main(hass)
    sid = await add_plant(hass, entry, "Kaffee", profile={"cultivar": "Typica"})
    manager = entry.runtime_data
    flow = hass.config_entries.subentries

    result = await start_flow(hass, entry, "reconfigure", sid)
    result = await flow.async_configure(result["flow_id"], {"next_step_id": "openplantbook"})
    assert result["type"] == "abort" and result["reason"] == "opb_missing"

    calls = register_opb(hass)
    result = await start_flow(hass, entry, "reconfigure", sid)
    result = await flow.async_configure(result["flow_id"], {"next_step_id": "openplantbook"})
    result = await flow.async_configure(result["flow_id"], {"next_step_id": "opb_search"})
    result = await flow.async_configure(result["flow_id"], {"search": "coffea"})
    result = await flow.async_configure(result["flow_id"], {"species": "coffea arabica"})
    assert result["reason"] == "reconfigure_successful"
    profile = manager.plants[sid].profile
    assert (profile.opb_pid, profile.common_name, profile.cultivar) == (
        "coffea arabica",
        "Kaffeestrauch",
        "Typica",
    )

    # user edits a text, OpenPlantbook changes, refresh must keep the user's text
    await hass.services.async_call(
        "rootine",
        "update_profile",
        {"entity_id": "sensor.kaffee_care_status", "care_watering": "Meine Regel"},
        blocking=True,
    )
    register_opb_changed = dict(OPB_DATA, watering="Neu", fertilization="Neu2")
    hass.services.async_remove("openplantbook", "get")

    async def get(call):
        return register_opb_changed

    hass.services.async_register(
        "openplantbook", "get", get, supports_response=SupportsResponse.ONLY
    )
    await hass.services.async_call(
        "rootine", "refresh_species", {"entity_id": "sensor.kaffee_care_status"}, blocking=True
    )
    profile = manager.plants[sid].profile
    assert profile.care["watering"] == "Meine Regel"
    assert profile.care["fertilization"] == "Neu2"
    await hass.services.async_call(
        "rootine",
        "refresh_species",
        {"entity_id": "sensor.kaffee_care_status", "overwrite_manual": True},
        blocking=True,
    )
    assert manager.plants[sid].profile.care["watering"] == "Neu"

    result = await start_flow(hass, entry, "reconfigure", sid)
    result = await flow.async_configure(result["flow_id"], {"next_step_id": "openplantbook"})
    result = await flow.async_configure(result["flow_id"], {"next_step_id": "opb_unlink"})
    profile = manager.plants[sid].profile
    assert profile.opb_pid is None and profile.opb_image_url is None
    assert profile.common_name == "Kaffeestrauch"
    assert calls  # sanity


async def test_refresh_without_link_fails(hass):
    entry = await setup_main(hass)
    await add_plant(hass, entry, "Kaffee")
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "rootine", "refresh_species", {"entity_id": "sensor.kaffee_care_status"}, blocking=True
        )


# --- rain mode -----------------------------------------------------------------------------


async def test_rain_mode_resets_and_per_plant_threshold(hass, freezer):
    hass.states.async_set("sensor.rain", "0")
    entry = await setup_main(hass, {"rain_entity": "sensor.rain", "rain_threshold": 5.0})
    await add_plant(
        hass,
        entry,
        "Kirsche",
        location="outdoor",
        mode="rain",
        water="ganzjährig: 3",
        last_done="2026-10-20",
    )
    await add_plant(
        hass,
        entry,
        "Pfirsich",
        location="outdoor",
        mode="rain",
        water="ganzjährig: 3",
        last_done="2026-10-20",
        limits={"rain_threshold": 2.0},
    )
    assert hass.states.get("sensor.kirsche_watering").state == "overdue"
    hass.states.async_set("sensor.rain", "3.0")
    await hass.async_block_till_done()
    assert hass.states.get("sensor.kirsche_watering").state == "overdue"
    assert hass.states.get("sensor.pfirsich_watering").state == "ok"  # own threshold 2 mm
    assert hass.states.get("sensor.pfirsich_watering").attributes["last_source"] == "rain"
    hass.states.async_set("sensor.rain", "5.5")
    await hass.async_block_till_done()
    assert hass.states.get("sensor.kirsche_watering").state == "ok"
    assert hass.states.get("sensor.kirsche_watering").attributes["last_source"] == "rain"


async def test_rain_ignored_indoors(hass):
    hass.states.async_set("sensor.rain", "0")
    entry = await setup_main(hass, {"rain_entity": "sensor.rain"})
    await add_plant(
        hass,
        entry,
        "Drinnen",
        location="indoor",
        mode="rain",
        water="ganzjährig: 3",
        last_done="2026-10-20",
    )
    hass.states.async_set("sensor.rain", "12")
    await hass.async_block_till_done()
    assert hass.states.get("sensor.drinnen_watering").state == "overdue"


# --- protection ----------------------------------------------------------------------------


async def test_protect_from_forecast_and_location(hass, freezer):
    async def forecasts(call):
        now = dt_util.now()
        return {
            call.data["entity_id"]: {
                "forecast": [
                    {"datetime": (now + timedelta(hours=h)).isoformat(), "temperature": t}
                    for h, t in ((1, 8), (5, 2.0), (9, 10))
                ]
            }
        }

    hass.services.async_register(
        "weather", "get_forecasts", forecasts, supports_response=SupportsResponse.ONLY
    )
    entry = await setup_main(hass, {"weather_entity": "weather.home"})
    sid = await add_plant(
        hass,
        entry,
        "Satsuma",
        location="outdoor",
        limits={"temp_min": 5},
        sensors={"temperature_entity": "sensor.sat_temp"},
    )
    hass.states.async_set("sensor.sat_temp", "12")
    await hass.async_block_till_done()
    await entry.runtime_data.async_start()
    assert hass.states.get("binary_sensor.satsuma_protection_needed").state == "on"
    attrs = hass.states.get("binary_sensor.satsuma_protection_needed").attributes
    assert attrs["reason"] == "cold_forecast" and attrs["forecast_min"] == 2.0
    assert hass.states.get("sensor.satsuma_care_status").state == "protect"
    # moved indoors: forecast warnings vanish at once
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.satsuma_location", "option": "indoor"},
        blocking=True,
    )
    assert hass.states.get("binary_sensor.satsuma_protection_needed").state == "off"
    # cold now from the own sensor works indoors too
    hass.states.async_set("sensor.sat_temp", "3")
    await hass.async_block_till_done()
    assert (
        hass.states.get("binary_sensor.satsuma_protection_needed").attributes["reason"]
        == "cold_now"
    )
    assert entry.runtime_data.plants[sid].warnings["protect"]["value"] == 3.0


async def test_heat_only_from_outdoor_sensor_not_plant_sensor(hass):
    entry = await setup_main(hass, {"outdoor_temp_entity": "sensor.outdoor"})
    await add_plant(
        hass,
        entry,
        "Kirsche",
        location="outdoor",
        limits={"temp_max": 32},
        sensors={"temperature_entity": "sensor.k_temp"},
    )
    hass.states.async_set("sensor.k_temp", "38")  # sun-heated sensor head
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.kirsche_protection_needed").state == "off"
    hass.states.async_set("sensor.outdoor", "34")
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.kirsche_protection_needed").state == "on"


async def test_limits_numbers_and_form(hass):
    entry = await setup_main(hass)
    sid = await add_plant(hass, entry, "Kaffee", limits={"temp_min": 10})
    assert float(hass.states.get("number.kaffee_cold_protection_below").state) == 10
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.kaffee_cold_protection_below", "value": 8},
        blocking=True,
    )
    assert entry.runtime_data.plants[sid].settings.temp_min == 8
    flow = hass.config_entries.subentries
    result = await start_flow(hass, entry, "reconfigure", sid)
    result = await flow.async_configure(result["flow_id"], {"next_step_id": "limits_edit"})
    result = await flow.async_configure(result["flow_id"], {"temp_max": 30})
    assert result["reason"] == "reconfigure_successful"
    settings = entry.runtime_data.plants[sid].settings
    assert (settings.temp_min, settings.temp_max) == (None, 30.0)  # empty field clears


# --- sensor mode ---------------------------------------------------------------------------


async def make_sensor_plant(hass, entry, **kwargs):
    return await add_plant(
        hass,
        entry,
        "Nektarine",
        location="outdoor",
        mode="sensor",
        water="",
        sensors={
            "moisture_entity": "sensor.nek",
            "battery_entity": "sensor.nek_batt",
            "valve_entity": "switch.valve",
        },
        water_extra={"moisture_threshold": 50},
        **kwargs,
    )


async def test_sensor_mode_not_offered_without_sensor(hass):
    from homeassistant.data_entry_flow import InvalidData

    entry = await setup_main(hass)
    flow = hass.config_entries.subentries
    result = await start_flow(hass, entry)
    result = await flow.async_configure(result["flow_id"], {"name": "A", "location": "indoor"})
    result = await flow.async_configure(result["flow_id"], {})
    result = await flow.async_configure(result["flow_id"], {})
    with pytest.raises(InvalidData):
        await flow.async_configure(
            result["flow_id"], {"mode": "sensor", "schedule_text": "", "last_done": "2026-10-01"}
        )


async def test_sensor_latch_button_and_battery(hass, freezer):
    hass.states.async_set("sensor.nek", "70")
    hass.states.async_set("sensor.nek_batt", "58")
    entry = await setup_main(hass)
    sid = await make_sensor_plant(hass, entry, fertilize="", last_done="2026-10-27")
    manager = entry.runtime_data
    assert hass.states.get("sensor.nektarine_watering").state == "unknown"  # not enough data yet
    # one day of readings
    for hours in range(0, 26):
        freezer.tick(timedelta(hours=1))
        hass.states.async_set("sensor.nek", str(70 - hours // 3))
        await hass.async_block_till_done()
    assert hass.states.get("sensor.nektarine_evaluated_soil_moisture").state not in (
        "unknown",
        "unavailable",
    )
    # slow decline below the threshold -> latched due
    for hour in range(60):
        freezer.tick(timedelta(hours=1))
        hass.states.async_set("sensor.nek", str(60 - hour))
        await hass.async_block_till_done()
    assert hass.states.get("sensor.nektarine_watering").state == "due"
    assert hass.states.get("sensor.nektarine_watering").attributes["reason"] == "sensor"
    assert float(hass.states.get("number.nektarine_watering_threshold").state) == 50
    # press "watered": resets and does not re-latch until a newer reading arrives
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.nektarine_watered"}, blocking=True
    )
    assert hass.states.get("sensor.nektarine_watering").state == "ok"
    # battery warning
    hass.states.async_set("sensor.nek_batt", "9")
    await hass.async_block_till_done()
    assert (
        hass.states.get("binary_sensor.nektarine_check_sensor").attributes["reason"]
        == "battery_low"
    )
    assert hass.states.get("sensor.nektarine_care_status").state in ("check_sensor", "ok")
    assert manager.plants[sid].warnings["sensor_check"]["reason"] == "battery_low"


async def test_sensor_drop_warning_and_checked_button(hass, freezer):
    hass.states.async_set("sensor.nek", "80")
    entry = await setup_main(hass)
    await make_sensor_plant(hass, entry, fertilize="")
    freezer.tick(timedelta(hours=2))
    hass.states.async_set("sensor.nek", "55")
    await hass.async_block_till_done()
    check = hass.states.get("binary_sensor.nektarine_check_sensor")
    assert check.state == "on" and check.attributes["reason"] == "drop"
    assert hass.states.get("sensor.nektarine_care_status").state == "check_sensor"
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.nektarine_sensor_checked"}, blocking=True
    )
    assert hass.states.get("binary_sensor.nektarine_check_sensor").state == "off"


async def test_sensor_stale_warning(hass, freezer):
    hass.states.async_set("sensor.nek", "60")
    entry = await setup_main(hass)
    await make_sensor_plant(hass, entry, fertilize="")
    freezer.tick(timedelta(hours=37))
    async_fire_time_changed(hass, dt_util.now())
    await hass.async_block_till_done()
    check = hass.states.get("binary_sensor.nektarine_check_sensor")
    assert check.state == "on" and check.attributes["reason"] == "stale"


async def test_valve_marks_plant_without_sensor(hass, freezer):
    hass.states.async_set("switch.valve", "off")
    entry = await setup_main(hass)
    await add_plant(
        hass,
        entry,
        "Kirsche",
        location="outdoor",
        water="ganzjährig: 3",
        last_done="2026-10-20",
        sensors={"valve_entity": "switch.valve"},
    )
    assert hass.states.get("sensor.kirsche_watering").state == "overdue"
    hass.states.async_set("switch.valve", "on")
    await hass.async_block_till_done()
    hass.states.async_set("switch.valve", "off")
    await hass.async_block_till_done()
    state = hass.states.get("sensor.kirsche_watering")
    assert state.state == "ok" and state.attributes["last_source"] == "valve"
    # a second switch within 10 minutes belongs to the same event
    freezer.tick(timedelta(minutes=3))
    hass.states.async_set("switch.valve", "on")
    hass.states.async_set("switch.valve", "off")
    await hass.async_block_till_done()
    valve_logs = [
        e
        for e in entry.runtime_data.plants[next(iter(entry.subentries))].log
        if e["source"] == "valve"
    ]
    assert len(valve_logs) == 1


# --- actions -------------------------------------------------------------------------------


async def test_mark_done_postpone_history_undo(hass):
    entry = await setup_main(hass)
    sid = await add_plant(hass, entry, "Kaffee", water="ganzjährig: 6", last_done="2026-10-20")
    entity = "sensor.kaffee_care_status"
    assert hass.states.get("sensor.kaffee_watering").state == "overdue"
    await hass.services.async_call(
        "rootine",
        "mark_done",
        {
            "entity_id": entity,
            "task": "water",
            "when": "2026-10-28T08:00:00+01:00",
            "note": "nachgetragen",
        },
        blocking=True,
    )
    state = hass.states.get("sensor.kaffee_watering")
    assert state.attributes["last_source"] == "service" and state.state == "ok"
    await hass.services.async_call(
        "rootine", "postpone", {"entity_id": entity, "task": "water", "days": 2}, blocking=True
    )
    assert hass.states.get("sensor.kaffee_watering").attributes["postponed_days"] == 2
    history = await hass.services.async_call(
        "rootine",
        "get_history",
        {"entity_id": entity, "limit": 5},
        blocking=True,
        return_response=True,
    )
    newest = history["items"][0]
    assert (newest["task"], newest["note"], newest["undone"]) == ("water", "nachgetragen", False)
    await hass.services.async_call(
        "rootine", "undo_event", {"entity_id": entity, "event_id": newest["id"]}, blocking=True
    )
    assert hass.states.get("sensor.kaffee_watering").attributes["last_source"] == "setup"
    assert entry.runtime_data.plants[sid].log[-1]["undone"] is True
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "rootine", "undo_event", {"entity_id": entity, "event_id": "nope"}, blocking=True
        )
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "rootine", "mark_done", {"entity_id": entity, "task": "nope"}, blocking=True
        )
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "rootine",
            "mark_done",
            {"entity_id": "sensor.rootine_due_care_tasks", "task": "water"},
            blocking=True,
        )


async def test_update_profile_and_photo_services(hass):
    entry = await setup_main(hass)
    sid = await add_plant(hass, entry, "Kaffee")
    entity = "sensor.kaffee_care_status"
    await hass.services.async_call(
        "rootine",
        "update_profile",
        {"entity_id": entity, "cultivar": "Typica", "care_soil": "Locker", "notes": "# Hallo"},
        blocking=True,
    )
    profile = entry.runtime_data.plants[sid].profile
    assert (profile.cultivar, profile.care["soil"], profile.notes) == (
        "Typica",
        "Locker",
        "# Hallo",
    )
    await hass.services.async_call(
        "rootine", "update_profile", {"entity_id": entity, "cultivar": ""}, blocking=True
    )
    assert entry.runtime_data.plants[sid].profile.cultivar is None
    await hass.services.async_call(
        "rootine",
        "set_photo",
        {
            "entity_id": entity,
            "photo": {
                "media_content_id": "media-source://image_upload/ID1",
                "media_content_type": "image/jpeg",
            },
        },
        blocking=True,
    )
    assert hass.states.get(entity).attributes["entity_picture"] == "/api/image/serve/ID1/512x512"
    await hass.services.async_call("rootine", "set_photo", {"entity_id": entity}, blocking=True)
    assert "entity_picture" not in hass.states.get(entity).attributes


async def test_get_due_and_hub_sensor(hass):
    entry = await setup_main(hass)
    await add_plant(
        hass, entry, "Satsuma", water="ganzjährig: 6", last_done="2026-10-23", fertilize=""
    )
    await add_plant(
        hass, entry, "Kirsche", water="ganzjährig: 3", last_done="2026-10-20", fertilize=""
    )
    await add_plant(
        hass, entry, "Kaffee", water="ganzjährig: 6", last_done="2026-10-24", fertilize=""
    )
    result = await hass.services.async_call(
        "rootine", "get_due", {}, blocking=True, return_response=True
    )
    assert result["count"] == 2
    assert [i["plant"] for i in result["items"]] == ["Kirsche", "Satsuma", "Kaffee"]
    assert [i["status"] for i in result["items"]] == ["overdue", "due", "soon"]
    assert (
        result["text"]
        == ("Heute zu tun: Satsuma gießen. Überfällig: Kirsche gießen. Morgen: Kaffee gießen.")
        or "Satsuma" in result["text"]
    )
    assert result["items"][0]["text"] == "Kirsche: Gießen ist seit 6 Tagen überfällig."
    assert result["items"][0]["plant_entity"] == "sensor.kirsche_care_status"
    no_soon = await hass.services.async_call(
        "rootine", "get_due", {"include_soon": False}, blocking=True, return_response=True
    )
    assert len(no_soon["items"]) == 2
    hub = hass.states.get("sensor.rootine_due_care_tasks")
    assert (
        hub.state == "2" and len(hub.attributes["items"]) == 2 and len(hub.attributes["soon"]) == 1
    )


async def test_todo_list_complete_task_and_warning(hass, freezer):
    hass.states.async_set("sensor.nek", "80")
    entry = await setup_main(hass)
    await add_plant(
        hass, entry, "Kirsche", water="ganzjährig: 3", last_done="2026-10-20", fertilize=""
    )
    await make_sensor_plant(hass, entry, fertilize="")
    freezer.tick(timedelta(hours=2))
    hass.states.async_set("sensor.nek", "50")
    await hass.async_block_till_done()
    items = (
        await hass.services.async_call(
            TODO_DOMAIN,
            "get_items",
            {"entity_id": "todo.rootine_plant_care"},
            blocking=True,
            return_response=True,
        )
    )["todo.rootine_plant_care"]["items"]
    summaries = {i["summary"]: i for i in items}
    assert "Kirsche gießen" in summaries
    assert any("Sensor prüfen" in s for s in summaries)
    await hass.services.async_call(
        TODO_DOMAIN,
        "update_item",
        {
            "entity_id": "todo.rootine_plant_care",
            "item": next(i["uid"] for i in items if "Sensor prüfen" in i["summary"]),
            "status": "completed",
        },
        blocking=True,
    )
    # acknowledged: gone from the list and get_due, binary sensor stays on
    assert hass.states.get("binary_sensor.nektarine_check_sensor").state == "on"
    items = (
        await hass.services.async_call(
            TODO_DOMAIN,
            "get_items",
            {"entity_id": "todo.rootine_plant_care"},
            blocking=True,
            return_response=True,
        )
    )["todo.rootine_plant_care"]["items"]
    assert not any("Sensor prüfen" in i["summary"] for i in items)
    watering = next(i for i in items if i["summary"].startswith("Kirsche"))
    await hass.services.async_call(
        TODO_DOMAIN,
        "update_item",
        {"entity_id": "todo.rootine_plant_care", "item": watering["uid"], "status": "completed"},
        blocking=True,
    )
    assert hass.states.get("sensor.kirsche_watering").attributes["last_source"] == "todo"


# --- structure ----------------------------------------------------------------------------


async def test_custom_tasks_add_edit_remove(hass):
    entry = await setup_main(hass)
    sid = await add_plant(hass, entry, "Satsuma")
    flow = hass.config_entries.subentries

    result = await start_flow(hass, entry, "reconfigure", sid)
    result = await flow.async_configure(result["flow_id"], {"next_step_id": "edit_task"})
    assert result["reason"] == "no_custom_tasks"

    result = await start_flow(hass, entry, "reconfigure", sid)
    result = await flow.async_configure(result["flow_id"], {"next_step_id": "add_task"})
    clash = await flow.async_configure(
        result["flow_id"],
        {"name": "Water", "schedule_text": "ganzjährig: 7", "last_done": "2026-10-20"},
    )
    assert clash["errors"] == {"base": "task_exists"}
    result = await flow.async_configure(
        result["flow_id"],
        {
            "name": "Spinnmilben-Check",
            "schedule_text": "01.11.–31.03.: 7",
            "last_done": "2026-10-20",
        },
    )
    await hass.async_block_till_done()
    assert hass.states.get("sensor.satsuma_spinnmilben_check")
    assert hass.states.get("button.satsuma_done")
    assert hass.states.get("date.satsuma_spinnmilben_check_last_done").state == "2026-10-20"

    result = await start_flow(hass, entry, "reconfigure", sid)
    result = await flow.async_configure(result["flow_id"], {"next_step_id": "edit_task"})
    result = await flow.async_configure(result["flow_id"], {"task": "spinnmilben_check"})
    result = await flow.async_configure(
        result["flow_id"], {"name": "Milbenkontrolle", "schedule_text": "ganzjährig: 5"}
    )
    await hass.async_block_till_done()
    renamed = hass.states.get("sensor.satsuma_spinnmilben_check")
    assert renamed.attributes["friendly_name"] == "Satsuma Milbenkontrolle"

    result = await start_flow(hass, entry, "reconfigure", sid)
    result = await flow.async_configure(result["flow_id"], {"next_step_id": "remove_task"})
    await flow.async_configure(result["flow_id"], {"task": "spinnmilben_check"})
    await hass.async_block_till_done()
    assert hass.states.get("sensor.satsuma_spinnmilben_check") is None


async def test_sensors_edit_adds_sensor_entities(hass):
    entry = await setup_main(hass)
    sid = await add_plant(hass, entry, "Satsuma")
    assert hass.states.get("sensor.satsuma_evaluated_soil_moisture") is None
    flow = hass.config_entries.subentries
    result = await start_flow(hass, entry, "reconfigure", sid)
    result = await flow.async_configure(result["flow_id"], {"next_step_id": "sensors_edit"})
    await flow.async_configure(result["flow_id"], {"moisture_entity": "sensor.sat"})
    await hass.async_block_till_done()
    assert hass.states.get("sensor.satsuma_evaluated_soil_moisture")
    assert hass.states.get("binary_sensor.satsuma_too_wet") is not None


async def test_water_edit_changes_mode(hass):
    hass.states.async_set("sensor.sat", "70")
    entry = await setup_main(hass)
    sid = await add_plant(
        hass, entry, "Satsuma", sensors={"moisture_entity": "sensor.sat"}, mode="timer"
    )
    flow = hass.config_entries.subentries
    result = await start_flow(hass, entry, "reconfigure", sid)
    result = await flow.async_configure(result["flow_id"], {"next_step_id": "water_edit"})
    bad = await flow.async_configure(result["flow_id"], {"mode": "sensor", "schedule_text": ""})
    assert bad["errors"] == {"base": "threshold_required"}
    await flow.async_configure(
        result["flow_id"],
        {"mode": "sensor", "schedule_text": "ganzjährig: 10", "moisture_threshold": 60},
    )
    await hass.async_block_till_done()
    assert entry.subentries[sid].data["tasks"][0]["mode"] == "sensor"
    assert entry.runtime_data.plants[sid].settings.moisture_threshold == 60


async def test_diagnostics(hass):
    from custom_components.rootine.diagnostics import async_get_config_entry_diagnostics

    entry = await setup_main(hass)
    sid = await add_plant(hass, entry, "Kaffee")
    data = await async_get_config_entry_diagnostics(hass, entry)
    assert data["plants"][sid]["name"] == "Kaffee"
    assert "water" in data["plants"][sid]["tasks"]


async def test_logbook_event_description(hass):
    from custom_components.rootine.logbook import async_describe_events

    captured = {}
    async_describe_events(hass, lambda domain, name, fn: captured.update({name: fn}))
    from homeassistant.core import Event

    out = captured["rootine_task_done"](
        Event("rootine_task_done", {"plant": "Kaffee", "task": "water", "source": "valve"})
    )
    assert out["name"] == "Kaffee" and "vom Ventil" in out["message"]


async def test_orphan_registry_cleanup_after_sensor_removed(hass):
    hass.states.async_set("sensor.sat", "70")
    entry = await setup_main(hass)
    sid = await add_plant(
        hass, entry, "Satsuma", sensors={"moisture_entity": "sensor.sat"}, mode="timer"
    )
    assert hass.states.get("sensor.satsuma_evaluated_soil_moisture")
    flow = hass.config_entries.subentries
    result = await start_flow(hass, entry, "reconfigure", sid)
    result = await flow.async_configure(result["flow_id"], {"next_step_id": "sensors_edit"})
    await flow.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()
    assert hass.states.get("sensor.satsuma_evaluated_soil_moisture") is None


async def test_care_status_exposes_moisture_for_the_card(hass):
    hass.states.async_set("sensor.nek", "70")
    entry = await setup_main(hass)
    await make_sensor_plant(hass, entry, fertilize="")
    moisture = hass.states.get("sensor.nektarine_care_status").attributes["moisture"]
    assert moisture["threshold"] == 50 and moisture["raw"] == 70
    await add_plant(hass, entry, "Kaffee")
    assert hass.states.get("sensor.kaffee_care_status").attributes["moisture"] is None
