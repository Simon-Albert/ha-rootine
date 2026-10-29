"""Store migration from the format of v1.1.0 (round 3, item A2)."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.rootine.const import DOMAIN

SID = "01KAFFEESUBENTRY0000000000"

V110_STORE = {
    "version": 1,
    "minor_version": 1,
    "key": "rootine",
    "data": {
        "plants": {
            SID: {
                "tasks": {
                    "water": {
                        "last_done": "2026-10-24T12:00:00+02:00",
                        "last_source": "button",
                        "postponed_days": 0,
                        "sensor_due_latched": False,
                        "rain_at_done": 0.0,
                    }
                },
                "profile": {
                    "common_name": "Kaffeestrauch",
                    "care": {},
                    "notes": "",
                    "manual_fields": [],
                },
                "settings": {
                    "location": "indoor",
                    "temp_min": 12.0,
                    "temp_max": None,
                    "moisture_threshold": None,
                    "moisture_max": None,
                    "rain_threshold": None,
                },
                "log": [
                    {
                        "id": "01A",
                        "ts": "2026-10-24T12:00:00+02:00",
                        "task": "water",
                        "source": "button",
                        "note": None,
                        "undone": False,
                    }
                ],
                "moisture_samples": [],
                "anomaly": {"active": False},
                "last_event": None,
                "wet": {"active": False, "above_since": None},
                "acked": [],
            }
        },
        "rain_days": {"2026-10-24": 1.5},
    },
}


@pytest.fixture(autouse=True)
async def tz(hass, freezer):
    await hass.config.async_set_time_zone("Europe/Berlin")
    freezer.move_to("2026-10-29 12:00:00+01:00")


async def test_migrates_a_v110_store(hass, hass_storage):
    hass_storage["rootine"] = V110_STORE
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Rootine",
        data={},
        options={},
        subentries_data=[
            {
                "subentry_id": SID,
                "subentry_type": "plant",
                "title": "Kaffee",
                "unique_id": "kaffee",
                "data": {
                    "name": "Kaffee",
                    "tasks": [
                        {
                            "key": "water",
                            "kind": "water",
                            "name": "Watering",
                            "schedule_text": "ganzjährig: 3",
                            "mode": "timer",
                        }
                    ],
                },
            }
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    plant = entry.runtime_data.plants[SID]
    assert plant.states["water"].last_done.isoformat() == "2026-10-24T12:00:00+02:00"
    assert plant.states["water"].latched_since is None
    assert plant.settings.temp_min == 12.0
    assert plant.profile.common_name == "Kaffeestrauch"
    assert hass.states.get("sensor.kaffee_watering").state == "overdue"
    await hass.config_entries.async_unload(entry.entry_id)
    saved = hass_storage["rootine"]
    assert (saved["version"], saved["minor_version"]) == (1, 2)
    stored = saved["data"]["plants"][SID]
    assert stored["oneoffs"] == []
    assert stored["settings"]["limit_memory"] == {}
    assert stored["tasks"]["water"]["latched_since"] is None
    assert saved["data"]["rain_days"] == {"2026-10-24": 1.5}


async def test_migration_function_directly():
    from custom_components.rootine.store import migrate

    data = migrate(1, 1, V110_STORE["data"])
    plant = data["plants"][SID]
    assert plant["oneoffs"] == [] and plant["settings"]["limit_memory"] == {}
    assert plant["tasks"]["water"]["latched_since"] is None
