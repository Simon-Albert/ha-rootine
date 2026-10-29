"""Blueprints must load and actually run against the Rootine actions."""

from pathlib import Path

import pytest
from homeassistant.components.blueprint import models
from homeassistant.components.blueprint.schemas import BLUEPRINT_SCHEMA
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from homeassistant.util.yaml import load_yaml
from pytest_homeassistant_custom_component.common import async_fire_time_changed, async_mock_service

from .conftest import add_plant, setup_main

BLUEPRINTS = Path(__file__).parents[2] / "blueprints" / "automation" / "rootine"


@pytest.mark.parametrize("name", ["daily_reminder.yaml", "spoken_report.yaml"])
def test_blueprint_is_valid(name):
    blueprint = models.Blueprint(
        load_yaml(str(BLUEPRINTS / name)), expected_domain="automation", schema=BLUEPRINT_SCHEMA
    )
    assert blueprint.metadata["domain"] == "automation"


async def test_daily_reminder_runs(hass, freezer):
    await hass.config.async_set_time_zone("Europe/Berlin")
    freezer.move_to("2026-10-29 07:59:50+01:00")
    entry = await setup_main(hass)
    await add_plant(
        hass, entry, "Kirsche", water="ganzjährig: 3", last_done="2026-10-20", fertilize=""
    )
    target = Path(hass.config.path("blueprints/automation/rootine"))
    target.mkdir(parents=True, exist_ok=True)
    (target / "daily_reminder.yaml").write_text((BLUEPRINTS / "daily_reminder.yaml").read_text())
    sent = async_mock_service(hass, "test", "notify")
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": {
                "use_blueprint": {
                    "path": "rootine/daily_reminder.yaml",
                    "input": {
                        "reminder_time": "08:00:00",
                        "include_soon": True,
                        "notify_actions": [
                            {
                                "action": "test.notify",
                                "data": {"message": "{{ text }}", "n": "{{ count }}"},
                            }
                        ],
                    },
                }
            }
        },
    )
    freezer.move_to("2026-10-29 08:00:01+01:00")
    async_fire_time_changed(hass, dt_util.now())
    await hass.async_block_till_done()
    assert len(sent) == 1
    assert "Kirsche" in sent[0].data["message"]
    assert int(sent[0].data["n"]) == 1
    # detach the time trigger, otherwise its timer for tomorrow 08:00 lingers after the test
    await hass.services.async_call("automation", "turn_off", {"entity_id": "all"}, blocking=True)
    await hass.async_block_till_done()
