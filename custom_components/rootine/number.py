"""Number entities: watering threshold, wet limit, temperature limits (stored in the Store)."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import RootinePlantEntity
from .manager import PlantRuntime, RootineManager


@dataclass(frozen=True)
class LimitDescription:
    key: str  # also the PlantSettings attribute
    percent: bool
    config: bool
    needs_sensor: bool
    switchable: bool  # has a switch to turn the limit off (switch.py)


LIMITS = (
    LimitDescription("moisture_threshold", True, False, True, False),
    LimitDescription("moisture_max", True, True, True, True),
    LimitDescription("temp_min", False, True, False, True),
    LimitDescription("temp_max", False, True, False, True),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    manager: RootineManager = entry.runtime_data
    for plant in manager.plants.values():
        async_add_entities(
            [
                LimitNumber(manager, plant, desc)
                for desc in LIMITS
                if plant.moisture_entity or not desc.needs_sensor
            ],
            config_subentry_id=plant.subentry_id,
        )


class LimitNumber(RootinePlantEntity, NumberEntity):
    _attr_mode = NumberMode.BOX
    _attr_native_step = 1

    def __init__(
        self, manager: RootineManager, plant: PlantRuntime, desc: LimitDescription
    ) -> None:
        super().__init__(manager, plant)
        self._desc = desc
        self._attr_translation_key = desc.key
        self._attr_unique_id = f"{plant.subentry_id}_{desc.key}"
        if desc.config:
            self._attr_entity_category = EntityCategory.CONFIG
        if desc.percent:
            self._attr_native_unit_of_measurement = PERCENTAGE
            self._attr_native_min_value = 0
            self._attr_native_max_value = 100
        else:
            self._attr_device_class = NumberDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
            self._attr_native_min_value = -40
            self._attr_native_max_value = 60
            self._attr_native_step = 0.5

    @property
    def native_value(self) -> float | None:
        return getattr(self.plant.settings, self._desc.key)

    async def async_set_native_value(self, value: float) -> None:
        stored: float | int = int(value) if self._desc.percent else value
        await self.manager.async_set_limit(self.subentry_id, self._desc.key, stored)
