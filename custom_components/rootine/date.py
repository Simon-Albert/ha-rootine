"""Datums-Entitäten: zuletzt erledigt (editierbar)."""

from __future__ import annotations

from datetime import date

from homeassistant.components.date import DateEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import RootineTaskEntity
from .manager import RootineManager


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    manager: RootineManager = entry.runtime_data
    for plant in manager.plants.values():
        async_add_entities(
            [TaskLastDoneDate(manager, plant, t.key) for t in plant.tasks],
            config_subentry_id=plant.subentry_id,
        )


class TaskLastDoneDate(RootineTaskEntity, DateEntity):
    _attr_translation_key = "task_last_done"

    def __init__(self, manager, plant, task_key: str) -> None:
        super().__init__(manager, plant, task_key)
        self._attr_unique_id = f"{plant.subentry_id}_{task_key}_last_done"

    @property
    def native_value(self) -> date:
        return self.plant.states[self.task_key].last_done.date()

    async def async_set_value(self, value: date) -> None:
        self.manager.set_last_done_date(self.subentry_id, self.task_key, value)
