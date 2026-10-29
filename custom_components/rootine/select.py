"""Select: location (outdoor/indoor)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import LOCATIONS
from .entity import RootinePlantEntity
from .manager import RootineManager


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    manager: RootineManager = entry.runtime_data
    for plant in manager.plants.values():
        async_add_entities([LocationSelect(manager, plant)], config_subentry_id=plant.subentry_id)


class LocationSelect(RootinePlantEntity, SelectEntity):
    _attr_translation_key = "location"
    _attr_options = list(LOCATIONS)

    def __init__(self, manager, plant) -> None:
        super().__init__(manager, plant)
        self._attr_unique_id = f"{plant.subentry_id}_location"

    @property
    def current_option(self) -> str:
        return self.plant.settings.location

    async def async_select_option(self, option: str) -> None:
        self.manager.set_location(self.subentry_id, option)
