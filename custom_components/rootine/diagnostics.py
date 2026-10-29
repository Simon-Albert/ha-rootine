"""Diagnostics download (plan 8.8)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .logic import oneoff
from .store import profile_to_dict, settings_to_dict

TO_REDACT: set[str] = set()  # nothing secret today; kept for future fields


def _strip_query(url: str | None) -> str | None:
    return url.split("?", 1)[0] if url else url


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    manager = entry.runtime_data
    plants = {}
    for sid, plant in manager.plants.items():
        profile = profile_to_dict(plant.profile)
        profile["opb_image_url"] = _strip_query(profile["opb_image_url"])
        plants[sid] = {
            "name": plant.name,
            "config": dict(plant.config),
            "profile": profile,
            "settings": settings_to_dict(plant.settings),
            "status": plant.status.value,
            "warnings": plant.warnings,
            "moisture": {
                "value": plant.moisture_value,
                "raw": plant.raw_moisture,
                "samples": len(plant.samples),
                "anomaly": plant.anomaly,
            },
            "tasks": {
                key: {
                    "state": {
                        "last_done": plant.states[key].last_done.isoformat(),
                        "last_source": plant.states[key].last_source,
                        "postponed_days": plant.states[key].postponed_days,
                        "latched": plant.states[key].sensor_due_latched,
                    },
                    "result": {
                        "status": res.status.value,
                        "next_due": res.next_due.isoformat() if res.next_due else None,
                        "days": res.days,
                        "reason": res.reason,
                    },
                }
                for key, res in plant.results.items()
            },
            "oneoffs": [oneoff.to_dict(o) for o in plant.oneoffs],
            "log": plant.log[-20:],
        }
    return async_redact_data(
        {"options": dict(entry.options), "rain_days": manager.rain_days, "plants": plants},
        TO_REDACT,
    )
