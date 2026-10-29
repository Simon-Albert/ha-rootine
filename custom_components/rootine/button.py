"""Knöpfe: Gegossen / Gedüngt / Erledigt."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import SOURCE_BUTTON
from .entity import RootinePlantEntity, RootineTaskEntity
from .manager import RootineManager


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    manager: RootineManager = entry.runtime_data
    for plant in manager.plants.values():
        entities: list[ButtonEntity] = [TaskDoneButton(manager, plant, t.key) for t in plant.tasks]
        if plant.moisture_entity:
            entities.append(SensorCheckedButton(manager, plant))
        async_add_entities(entities, config_subentry_id=plant.subentry_id)


class TaskDoneButton(RootineTaskEntity, ButtonEntity):
    def __init__(self, manager, plant, task_key: str) -> None:
        super().__init__(manager, plant, task_key)
        self._attr_unique_id = f"{plant.subentry_id}_{task_key}_done"
        self._attr_translation_key = f"done_{plant.task(task_key).kind.value}"

    async def async_press(self) -> None:
        self.manager.mark_done(self.subentry_id, self.task_key, SOURCE_BUTTON)


class SensorCheckedButton(RootinePlantEntity, ButtonEntity):
    _attr_translation_key = "sensor_checked"

    def __init__(self, manager, plant) -> None:
        super().__init__(manager, plant)
        self._attr_unique_id = f"{plant.subentry_id}_sensor_checked"

    async def async_press(self) -> None:
        self.manager.acknowledge_sensor(self.subentry_id)
