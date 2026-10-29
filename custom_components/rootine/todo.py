"""To-do list "Pflanzenpflege": derived from due tasks and warnings (plan 8.5)."""

from __future__ import annotations

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN, SOURCE_TODO, WARN_PROTECT, WARN_SENSOR, WARN_TOO_WET
from .entity import RootineHubEntity
from .manager import RootineManager

WARNINGS = (WARN_PROTECT, WARN_TOO_WET, WARN_SENSOR)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([CareTodoList(entry.runtime_data)])


class CareTodoList(RootineHubEntity, TodoListEntity):
    _attr_translation_key = "care"
    _attr_supported_features = TodoListEntityFeature.UPDATE_TODO_ITEM

    def __init__(self, manager: RootineManager) -> None:
        super().__init__(manager)
        self._attr_unique_id = f"{manager.entry.entry_id}_care"

    @property
    def todo_items(self) -> list[TodoItem]:
        return [
            TodoItem(
                uid=e["uid"],
                summary=e["summary"],
                status=TodoItemStatus.NEEDS_ACTION,
                due=e["due"],
                description=e["description"],
            )
            for e in self.manager.todo_items()
        ]

    async def async_update_todo_item(self, item: TodoItem) -> None:
        if item.status != TodoItemStatus.COMPLETED:
            return
        try:
            subentry_id, key, _tail = (item.uid or "").split(":", 2)
            plant = self.manager.plants[subentry_id]
        except (ValueError, KeyError) as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="unknown_todo_item"
            ) from err
        if key in WARNINGS:
            self.manager.acknowledge_warning(subentry_id, key)
        elif plant.has_task(key):
            self.manager.mark_done(subentry_id, key, SOURCE_TODO)
        elif plant.oneoff(key):
            self.manager.complete_oneoff(subentry_id, key, SOURCE_TODO)
        else:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="unknown_todo_item"
            )
