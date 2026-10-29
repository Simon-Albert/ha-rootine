"""Sensoren: Pflegestatus, Aufgabenstatus, Fälligkeitsdatum, Sammelsensor."""

from __future__ import annotations

from datetime import date
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import RootineHubEntity, RootinePlantEntity, RootineTaskEntity
from .logic.due import DueStatus
from .logic.profile import get_field, photo_url
from .manager import RootineManager

STATUS_OPTIONS = [s.value for s in DueStatus]
PROFILE_ATTRS = (
    "common_name",
    "species",
    "cultivar",
    "rootstock",
    "pot",
    "acquired",
    "notes",
    "care.watering",
    "care.sunlight",
    "care.soil",
    "care.pruning",
    "care.fertilization",
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    manager: RootineManager = entry.runtime_data
    async_add_entities([DueCountSensor(manager)])
    for plant in manager.plants.values():
        entities: list[Any] = [CareStatusSensor(manager, plant)]
        if plant.moisture_entity:
            entities.append(MoistureEvalSensor(manager, plant))
        for task in plant.tasks:
            entities.append(TaskStatusSensor(manager, plant, task.key))
            entities.append(TaskNextDueSensor(manager, plant, task.key))
        async_add_entities(entities, config_subentry_id=plant.subentry_id)


class CareStatusSensor(RootinePlantEntity, SensorEntity):
    _attr_translation_key = "care_status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = STATUS_OPTIONS

    def __init__(self, manager: RootineManager, plant) -> None:
        super().__init__(manager, plant)
        self._attr_unique_id = f"{plant.subentry_id}_care_status"

    @property
    def native_value(self) -> str:
        return self.plant.status.value

    @property
    def entity_picture(self) -> str | None:
        return photo_url(self.plant.profile)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        plant = self.plant
        tasks = {}
        for task in plant.tasks:
            res = plant.results[task.key]
            tasks[task.key] = {
                "name": task.name,
                "status": res.status.value,
                "next_due": res.next_due.isoformat() if res.next_due else None,
                "days": res.days,
            }
        profile = {name: get_field(plant.profile, name) for name in PROFILE_ATTRS}
        profile["opb_pid"] = plant.profile.opb_pid
        return {
            "location": plant.settings.location,
            "profile": profile,
            "tasks": tasks,
            "warnings": [{"key": key, **info} for key, info in plant.warnings.items()],
            "moisture": {
                "value": plant.moisture_value,
                "raw": plant.raw_moisture,
                "threshold": plant.settings.moisture_threshold,
                "max": plant.settings.moisture_max,
            }
            if plant.moisture_entity
            else None,
            "log": list(reversed(plant.log[-10:])),
        }


class TaskStatusSensor(RootineTaskEntity, SensorEntity):
    _attr_translation_key = "task_status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = STATUS_OPTIONS

    def __init__(self, manager: RootineManager, plant, task_key: str) -> None:
        super().__init__(manager, plant, task_key)
        self._attr_unique_id = f"{plant.subentry_id}_{task_key}_status"

    @property
    def native_value(self) -> str:
        return self.result.status.value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        res = self.result
        state = self.plant.states[self.task_key]
        return {
            "next_due": res.next_due.isoformat() if res.next_due else None,
            "days": res.days,
            "interval_days": res.interval,
            "period": None
            if res.period is None
            else f"{res.period.start[0]:02d}.{res.period.start[1]:02d}.–"
            f"{res.period.end[0]:02d}.{res.period.end[1]:02d}.",
            "reason": res.reason,
            "after_pause": res.after_pause,
            "last_done": state.last_done.isoformat(),
            "last_source": state.last_source,
            "postponed_days": state.postponed_days,
        }


class TaskNextDueSensor(RootineTaskEntity, SensorEntity):
    _attr_translation_key = "task_next_due"
    _attr_device_class = SensorDeviceClass.DATE

    def __init__(self, manager: RootineManager, plant, task_key: str) -> None:
        super().__init__(manager, plant, task_key)
        self._attr_unique_id = f"{plant.subentry_id}_{task_key}_next_due"

    @property
    def native_value(self) -> date | None:
        return self.result.next_due


class DueCountSensor(RootineHubEntity, SensorEntity):
    _attr_translation_key = "due_count"
    _attr_native_unit_of_measurement = None

    def __init__(self, manager: RootineManager) -> None:
        super().__init__(manager)
        self._attr_unique_id = f"{manager.entry.entry_id}_due_count"

    @property
    def native_value(self) -> int:
        return self.manager.due_summary()["count"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        summary = self.manager.due_summary()
        return {"items": summary["items"], "soon": summary["soon"], "text": summary["text"]}


class MoistureEvalSensor(RootinePlantEntity, SensorEntity):
    _attr_translation_key = "moisture_eval"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(self, manager: RootineManager, plant) -> None:
        super().__init__(manager, plant)
        self._attr_unique_id = f"{plant.subentry_id}_moisture_eval"

    @property
    def native_value(self) -> float | None:
        return self.plant.moisture_value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        plant = self.plant
        return {
            "raw": plant.raw_moisture,
            "source_entity": plant.moisture_entity,
            "threshold": plant.settings.moisture_threshold,
            "moisture_max": plant.settings.moisture_max,
            "method": plant.method,
            "samples": len(plant.samples),
        }
