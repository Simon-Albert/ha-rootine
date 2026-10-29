"""Switches: turn a limit off at the entity; its value is kept for switching it on again."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import RootinePlantEntity
from .manager import PlantRuntime, RootineManager
from .number import LIMITS, LimitDescription


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    manager: RootineManager = entry.runtime_data
    for plant in manager.plants.values():
        async_add_entities(
            [
                LimitSwitch(manager, plant, desc)
                for desc in LIMITS
                if desc.switchable and (plant.moisture_entity or not desc.needs_sensor)
            ],
            config_subentry_id=plant.subentry_id,
        )


class LimitSwitch(RootinePlantEntity, SwitchEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, manager: RootineManager, plant: PlantRuntime, desc: LimitDescription
    ) -> None:
        super().__init__(manager, plant)
        self._key = desc.key
        self._attr_translation_key = f"{desc.key}_enabled"
        self._attr_unique_id = f"{plant.subentry_id}_{desc.key}_enabled"

    @property
    def is_on(self) -> bool:
        return getattr(self.plant.settings, self._key) is not None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.manager.async_switch_limit(self.subentry_id, self._key, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.manager.async_switch_limit(self.subentry_id, self._key, False)
