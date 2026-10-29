"""Persistenter Zustand (.storage/rootine): Serialisierung und Store-Hülle (6.4)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import STORE_KEY, STORE_VERSION
from .logic.due import TaskState
from .logic.profile import PlantSettings, Profile


def state_to_dict(state: TaskState) -> dict[str, Any]:
    return {
        "last_done": state.last_done.isoformat(),
        "last_source": state.last_source,
        "postponed_days": state.postponed_days,
        "sensor_due_latched": state.sensor_due_latched,
        "rain_at_done": state.rain_at_done,
    }


def state_from_dict(data: dict[str, Any]) -> TaskState:
    last_done = dt_util.parse_datetime(data["last_done"]) or dt_util.now()
    return TaskState(
        last_done=dt_util.as_local(last_done),
        last_source=data.get("last_source", "setup"),
        postponed_days=data.get("postponed_days", 0),
        sensor_due_latched=data.get("sensor_due_latched", False),
        rain_at_done=data.get("rain_at_done"),
    )


def profile_to_dict(profile: Profile) -> dict[str, Any]:
    return {
        "common_name": profile.common_name,
        "species": profile.species,
        "cultivar": profile.cultivar,
        "rootstock": profile.rootstock,
        "pot": profile.pot,
        "acquired": profile.acquired,
        "care": dict(profile.care),
        "notes": profile.notes,
        "photo": profile.photo,
        "opb_pid": profile.opb_pid,
        "opb_image_url": profile.opb_image_url,
        "manual_fields": sorted(profile.manual_fields),
    }


def profile_from_dict(data: dict[str, Any]) -> Profile:
    return Profile(
        common_name=data.get("common_name"),
        species=data.get("species"),
        cultivar=data.get("cultivar"),
        rootstock=data.get("rootstock"),
        pot=data.get("pot"),
        acquired=data.get("acquired"),
        care=dict(data.get("care") or {}),
        notes=data.get("notes") or "",
        photo=data.get("photo"),
        opb_pid=data.get("opb_pid"),
        opb_image_url=data.get("opb_image_url"),
        manual_fields=set(data.get("manual_fields") or []),
    )


def settings_to_dict(settings: PlantSettings) -> dict[str, Any]:
    return {
        "location": settings.location,
        "moisture_threshold": settings.moisture_threshold,
        "moisture_max": settings.moisture_max,
        "temp_min": settings.temp_min,
        "temp_max": settings.temp_max,
        "rain_threshold": settings.rain_threshold,
    }


def settings_from_dict(data: dict[str, Any]) -> PlantSettings:
    defaults = PlantSettings()
    return PlantSettings(
        location=data.get("location", defaults.location),
        moisture_threshold=data.get("moisture_threshold"),
        moisture_max=data.get("moisture_max"),
        temp_min=data.get("temp_min"),
        temp_max=data.get("temp_max"),
        rain_threshold=data.get("rain_threshold"),
    )


class RootineStore:
    """Dünne Hülle um helpers.storage.Store."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, Any]] = Store(hass, STORE_VERSION, STORE_KEY)

    async def async_load(self) -> dict[str, Any]:
        data = await self._store.async_load() or {}
        data.setdefault("plants", {})
        data.setdefault("rain_days", {})
        return data

    def schedule_save(self, delay: int, data_func: Callable[[], dict[str, Any]]) -> None:
        self._store.async_delay_save(data_func, delay)

    async def async_save(self, data: dict[str, Any]) -> None:
        await self._store.async_save(data)
