"""Repair issues for missing or renamed linked entities, with a fix flow (item A3)."""

from __future__ import annotations

import pytest
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component

from custom_components.rootine.const import DOMAIN

from .conftest import add_plant, setup_main

MOISTURE = "sensor.test_moisture"


@pytest.fixture(autouse=True)
async def tz(hass, freezer):
    await hass.config.async_set_time_zone("Europe/Berlin")
    freezer.move_to("2026-10-29 12:00:00+01:00")


def _issues(hass) -> dict[str, ir.IssueEntry]:
    registry = ir.async_get(hass)
    return {
        issue_id: issue for (domain, issue_id), issue in registry.issues.items() if domain == DOMAIN
    }


async def _plant_with_sensor(hass, **options):
    hass.states.async_set(MOISTURE, "40", {"device_class": "moisture", "unit_of_measurement": "%"})
    entry = await setup_main(hass, options or None)
    sid = await add_plant(hass, entry, "Kaffee", sensors={"moisture_entity": MOISTURE})
    return entry, sid


async def test_no_issue_while_everything_is_there(hass):
    await _plant_with_sensor(hass)
    assert _issues(hass) == {}


async def test_missing_sensor_raises_issue_and_it_clears_itself(hass):
    _entry, sid = await _plant_with_sensor(hass)
    hass.states.async_remove(MOISTURE)
    await hass.async_block_till_done()
    issues = _issues(hass)
    assert list(issues) == [f"missing_{sid}_moisture_entity"]
    issue = issues[f"missing_{sid}_moisture_entity"]
    assert issue.is_fixable
    assert issue.translation_key == "missing_moisture_entity"
    assert issue.translation_placeholders == {"entity": MOISTURE, "plant": "Kaffee"}
    # the sensor comes back: the issue disappears without any action
    hass.states.async_set(MOISTURE, "41")
    await hass.async_block_till_done()
    assert _issues(hass) == {}


async def test_missing_at_start_raises_issue(hass):
    await setup_main(hass, {"weather_entity": "weather.gone", "rain_entity": "sensor.gone"})
    assert set(_issues(hass)) == {"missing_main_weather_entity", "missing_main_rain_entity"}
    issue = _issues(hass)["missing_main_rain_entity"]
    assert issue.translation_placeholders == {"entity": "sensor.gone", "plant": "Rootine"}


async def test_registry_entity_without_state_is_not_missing(hass):
    """At start other integrations may not have loaded yet: a registry entry is enough."""
    registry = er.async_get(hass)
    registry.async_get_or_create("switch", "test", "valve1", suggested_object_id="test_valve")
    entry = await setup_main(hass)
    await add_plant(hass, entry, "Kaffee", sensors={"valve_entity": "switch.test_valve"})
    assert _issues(hass) == {}


async def test_renamed_entity_raises_issue(hass):
    registry = er.async_get(hass)
    registry.async_get_or_create("sensor", "test", "rain1", suggested_object_id="test_rain")
    await setup_main(hass, {"rain_entity": "sensor.test_rain"})
    assert _issues(hass) == {}
    registry.async_update_entity("sensor.test_rain", new_entity_id="sensor.test_rain_gauge")
    await hass.async_block_till_done()
    assert set(_issues(hass)) == {"missing_main_rain_entity"}


async def test_disabled_entity_counts_as_missing(hass):
    registry = er.async_get(hass)
    registry.async_get_or_create("sensor", "test", "rain1", suggested_object_id="test_rain")
    await setup_main(hass, {"rain_entity": "sensor.test_rain"})
    registry.async_update_entity("sensor.test_rain", disabled_by=er.RegistryEntryDisabler.USER)
    await hass.async_block_till_done()
    assert set(_issues(hass)) == {"missing_main_rain_entity"}


async def _fix(hass, hass_client, issue_id, user_input):
    """Run the fix flow through the repairs HTTP API, as the frontend does."""
    assert await async_setup_component(hass, "repairs", {})
    await hass.async_block_till_done()
    client = await hass_client()
    resp = await client.post(
        "/api/repairs/issues/fix", json={"handler": DOMAIN, "issue_id": issue_id}
    )
    assert resp.status == 200, await resp.text()
    result = await resp.json()
    assert result["type"] == "form" and result["step_id"] == "relink"
    assert result["description_placeholders"]["entity"]
    resp = await client.post(f"/api/repairs/issues/fix/{result['flow_id']}", json=user_input)
    assert resp.status == 200, await resp.text()
    await hass.async_block_till_done()
    return await resp.json()


async def test_fix_flow_links_the_new_entity(hass, hass_client):
    entry, sid = await _plant_with_sensor(hass)
    hass.states.async_remove(MOISTURE)
    await hass.async_block_till_done()
    hass.states.async_set("sensor.test_moisture_2", "38", {"device_class": "moisture"})
    result = await _fix(
        hass, hass_client, f"missing_{sid}_moisture_entity", {"entity_id": "sensor.test_moisture_2"}
    )
    assert result["type"] == "create_entry"
    assert entry.subentries[sid].data["moisture_entity"] == "sensor.test_moisture_2"
    assert _issues(hass) == {}
    plant = entry.runtime_data.plants[sid]
    assert plant.moisture_entity == "sensor.test_moisture_2"


async def test_fix_flow_can_remove_the_link(hass, hass_client):
    entry = await setup_main(hass, {"weather_entity": "weather.gone"})
    result = await _fix(hass, hass_client, "missing_main_weather_entity", {})
    assert result["type"] == "create_entry"
    assert "weather_entity" not in entry.options
    assert _issues(hass) == {}


async def test_issues_of_a_removed_plant_disappear(hass):
    entry, sid = await _plant_with_sensor(hass)
    hass.states.async_remove(MOISTURE)
    await hass.async_block_till_done()
    assert _issues(hass)
    hass.config_entries.async_remove_subentry(entry, sid)
    await hass.async_block_till_done()
    assert _issues(hass) == {}


async def test_issues_are_removed_with_the_integration(hass):
    entry = await setup_main(hass, {"weather_entity": "weather.gone"})
    assert _issues(hass)
    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert _issues(hass) == {}


@pytest.mark.parametrize("language", ["de", "en"])
def test_every_issue_is_translated(language):
    import json
    from pathlib import Path

    from custom_components.rootine import repairs

    path = Path(repairs.__file__).parent / "translations" / f"{language}.json"
    issues = json.loads(path.read_text(encoding="utf-8"))["issues"]
    for key in (*repairs.MAIN_KEYS, *repairs.PLANT_KEYS):
        issue = issues[f"missing_{key}"]
        assert "{plant}" in issue["title"] and "description" not in issue  # hassfest rule
        assert "{entity}" in issue["fix_flow"]["step"]["relink"]["description"]
