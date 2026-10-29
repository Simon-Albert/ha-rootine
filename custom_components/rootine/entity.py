"""Base classes for Rootine entities."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, signal_hub, signal_plant
from .manager import PlantRuntime, RootineManager


class RootineHubEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, manager: RootineManager) -> None:
        self.manager = manager
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, manager.entry.entry_id)},
            name="Rootine",
            manufacturer="Rootine",
            model="Hub",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal_hub(self.manager.entry.entry_id), self._refresh
            )
        )

    @callback
    def _refresh(self) -> None:
        self.async_write_ha_state()


class RootinePlantEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, manager: RootineManager, plant: PlantRuntime) -> None:
        self.manager = manager
        self.subentry_id = plant.subentry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, plant.subentry_id)},
            name=plant.name,
            manufacturer="Rootine",
            model=plant.profile.species or "Pflanze",
        )

    @property
    def plant(self) -> PlantRuntime:
        return self.manager.plants[self.subentry_id]

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_plant(self.manager.entry.entry_id, self.subentry_id),
                self._refresh,
            )
        )

    @callback
    def _refresh(self) -> None:
        self.async_write_ha_state()


class RootineTaskEntity(RootinePlantEntity):
    def __init__(self, manager: RootineManager, plant: PlantRuntime, task_key: str) -> None:
        super().__init__(manager, plant)
        self.task_key = task_key
        self._attr_translation_placeholders = {"task": plant.task(task_key).name}

    @property
    def result(self):
        return self.plant.results[self.task_key]
