"""Binärsensoren: Aufgabe fällig."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import WARN_SENSOR, WARN_TOO_WET
from .entity import RootinePlantEntity, RootineTaskEntity
from .logic.due import DueStatus
from .manager import RootineManager


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    manager: RootineManager = entry.runtime_data
    for plant in manager.plants.values():
        entities: list[Any] = [TaskDueBinarySensor(manager, plant, t.key) for t in plant.tasks]
        entities.append(ProtectBinarySensor(manager, plant))
        if plant.moisture_entity:
            entities.append(TooWetBinarySensor(manager, plant))
            entities.append(SensorCheckBinarySensor(manager, plant))
        async_add_entities(entities, config_subentry_id=plant.subentry_id)


class TaskDueBinarySensor(RootineTaskEntity, BinarySensorEntity):
    _attr_translation_key = "task_due"

    def __init__(self, manager, plant, task_key: str) -> None:
        super().__init__(manager, plant, task_key)
        self._attr_unique_id = f"{plant.subentry_id}_{task_key}_due"

    @property
    def is_on(self) -> bool:
        return self.result.status in (DueStatus.DUE, DueStatus.OVERDUE)


class ProtectBinarySensor(RootinePlantEntity, BinarySensorEntity):
    _attr_translation_key = "protect"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, manager, plant) -> None:
        super().__init__(manager, plant)
        self._attr_unique_id = f"{plant.subentry_id}_protect"

    @property
    def is_on(self) -> bool:
        return self.plant.protect.active

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        plant = self.plant
        return {
            "reason": plant.protect.reason,
            "forecast_min": plant.forecast_min,
            "forecast_max": plant.forecast_max,
            "current": plant.current_temp,
        }


class TooWetBinarySensor(RootinePlantEntity, BinarySensorEntity):
    _attr_translation_key = "too_wet"
    _attr_device_class = BinarySensorDeviceClass.MOISTURE

    def __init__(self, manager, plant) -> None:
        super().__init__(manager, plant)
        self._attr_unique_id = f"{plant.subentry_id}_too_wet"

    @property
    def is_on(self) -> bool:
        return WARN_TOO_WET in self.plant.warnings


class SensorCheckBinarySensor(RootinePlantEntity, BinarySensorEntity):
    _attr_translation_key = "sensor_check"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, manager, plant) -> None:
        super().__init__(manager, plant)
        self._attr_unique_id = f"{plant.subentry_id}_sensor_check"

    @property
    def is_on(self) -> bool:
        return WARN_SENSOR in self.plant.warnings

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"reason": self.plant.warnings.get(WARN_SENSOR, {}).get("reason")}
