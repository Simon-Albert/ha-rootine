"""Logbook entries for rootine_task_done."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.components.logbook import LOGBOOK_ENTRY_MESSAGE, LOGBOOK_ENTRY_NAME
from homeassistant.core import Event, HomeAssistant, callback

from .const import DOMAIN, EVENT_TASK_DONE

SOURCES = {
    "button": "per Knopf",
    "todo": "über die To-do-Liste",
    "service": "über eine Aktion",
    "date_edit": "per Datumskorrektur",
    "sensor": "vom Sensor erkannt",
    "valve": "vom Ventil erkannt",
    "rain": "durch Regen",
    "setup": "beim Einrichten",
}


@callback
def async_describe_events(
    hass: HomeAssistant,
    async_describe_event: Callable[[str, str, Callable[[Event], dict[str, Any]]], None],
) -> None:
    @callback
    def describe(event: Event) -> dict[str, Any]:
        data = event.data
        source = SOURCES.get(data.get("source", ""), data.get("source", ""))
        task = data.get("task_name") or data.get("task")
        return {
            LOGBOOK_ENTRY_NAME: data.get("plant"),
            LOGBOOK_ENTRY_MESSAGE: f"{task} erledigt ({source})",
        }

    async_describe_event(DOMAIN, EVENT_TASK_DONE, describe)
