"""Rootine actions (plan 8.4). Registered once in async_setup."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from . import openplantbook
from .const import DOMAIN, SOURCE_SERVICE
from .logic.profile import apply_opb, parse_opb, update_fields
from .manager import PlantRuntime, RootineManager

PROFILE_FIELDS = {
    "common_name": "common_name",
    "species": "species",
    "cultivar": "cultivar",
    "rootstock": "rootstock",
    "pot": "pot",
    "acquired": "acquired",
    "notes": "notes",
    "care_watering": "care.watering",
    "care_sunlight": "care.sunlight",
    "care_soil": "care.soil",
    "care_pruning": "care.pruning",
    "care_fertilization": "care.fertilization",
}

_ENTITY = {vol.Required("entity_id"): cv.entity_id}
_PHOTO = vol.Any(None, "", cv.string, dict)

MARK_DONE = vol.Schema(
    {
        **_ENTITY,
        vol.Required("task"): cv.string,
        vol.Optional("when"): cv.datetime,
        vol.Optional("note"): cv.string,
    }
)
POSTPONE = vol.Schema(
    {
        **_ENTITY,
        vol.Required("task"): cv.string,
        vol.Required("days"): vol.All(int, vol.Range(1, 60)),
    }
)
GET_DUE = vol.Schema(
    {
        vol.Optional("days_ahead", default=0): vol.All(int, vol.Range(0, 14)),
        vol.Optional("include_soon", default=True): cv.boolean,
    }
)
REFRESH = vol.Schema({**_ENTITY, vol.Optional("overwrite_manual", default=False): cv.boolean})
UPDATE_PROFILE = vol.Schema(
    {
        **_ENTITY,
        **{vol.Optional(name): vol.Any(None, cv.string) for name in PROFILE_FIELDS},
        vol.Optional("photo"): _PHOTO,
    }
)
SET_PHOTO = vol.Schema({**_ENTITY, vol.Optional("photo"): _PHOTO})
HISTORY = vol.Schema(
    {**_ENTITY, vol.Optional("limit", default=50): vol.All(int, vol.Range(1, 200))}
)
UNDO = vol.Schema({**_ENTITY, vol.Required("event_id"): cv.string})


def _fail(key: str, **placeholders: str) -> ServiceValidationError:
    return ServiceValidationError(
        translation_domain=DOMAIN, translation_key=key, translation_placeholders=placeholders
    )


def _resolve(hass: HomeAssistant, entity_id: str) -> tuple[RootineManager, PlantRuntime]:
    entry = er.async_get(hass).async_get(entity_id)
    if entry is None or entry.platform != DOMAIN or entry.config_subentry_id is None:
        raise _fail("unknown_plant")
    config_entry = hass.config_entries.async_get_entry(entry.config_entry_id or "")
    manager = getattr(config_entry, "runtime_data", None)
    plant = manager.plants.get(entry.config_subentry_id) if manager else None
    if manager is None or plant is None:
        raise _fail("unknown_plant")
    return manager, plant


def _task(plant: PlantRuntime, key: str) -> str:
    if not plant.has_task(key):
        raise _fail("unknown_task", task=key)
    return key


def _photo_id(value: Any) -> str | None:
    if isinstance(value, dict):
        return value.get("media_content_id") or None
    return value or None


def async_register_services(hass: HomeAssistant) -> None:
    async def mark_done(call: ServiceCall) -> None:
        manager, plant = _resolve(hass, call.data["entity_id"])
        manager.mark_done(
            plant.subentry_id,
            _task(plant, call.data["task"]),
            SOURCE_SERVICE,
            when=call.data.get("when"),
            note=call.data.get("note"),
        )

    async def postpone(call: ServiceCall) -> None:
        manager, plant = _resolve(hass, call.data["entity_id"])
        manager.postpone(plant.subentry_id, _task(plant, call.data["task"]), call.data["days"])

    async def get_due(call: ServiceCall) -> ServiceResponse:
        managers = [
            entry.runtime_data
            for entry in hass.config_entries.async_loaded_entries(DOMAIN)
            if hasattr(entry, "runtime_data")
        ]
        items: list[dict[str, Any]] = []
        text = "Heute ist nichts zu tun."
        for manager in managers:
            items += manager.due_items(
                include_soon=call.data["include_soon"], days_ahead=call.data["days_ahead"]
            )
            text = manager.due_summary()["text"]
        for item in items:
            item.pop("report_name", None)
        count = sum(
            1 for i in items if i["status"] in ("due", "overdue", "check_sensor", "protect")
        )
        return {"count": count, "text": text, "items": items}

    async def refresh_species(call: ServiceCall) -> None:
        manager, plant = _resolve(hass, call.data["entity_id"])
        if not plant.profile.opb_pid:
            raise _fail("no_openplantbook")
        data = await openplantbook.async_get(hass, plant.profile.opb_pid)
        if not data:
            raise _fail("no_openplantbook")
        profile = apply_opb(
            plant.profile, parse_opb(data), overwrite_manual=call.data["overwrite_manual"]
        )
        manager.set_profile(plant.subentry_id, profile)

    async def update_profile(call: ServiceCall) -> None:
        manager, plant = _resolve(hass, call.data["entity_id"])
        changes = {
            PROFILE_FIELDS[name]: call.data[name] for name in PROFILE_FIELDS if name in call.data
        }
        profile = update_fields(plant.profile, changes)
        if "photo" in call.data:
            profile.photo = _photo_id(call.data["photo"])
        manager.set_profile(plant.subentry_id, profile)

    async def set_photo(call: ServiceCall) -> None:
        manager, plant = _resolve(hass, call.data["entity_id"])
        profile = update_fields(plant.profile, {})
        profile.photo = _photo_id(call.data.get("photo"))
        manager.set_profile(plant.subentry_id, profile)

    async def get_history(call: ServiceCall) -> ServiceResponse:
        manager, plant = _resolve(hass, call.data["entity_id"])
        return {"items": manager.history(plant.subentry_id, call.data["limit"])}

    async def undo_event(call: ServiceCall) -> None:
        manager, plant = _resolve(hass, call.data["entity_id"])
        if not manager.undo_event(plant.subentry_id, call.data["event_id"]):
            raise _fail("unknown_event")

    for name, handler, schema, response in (
        ("mark_done", mark_done, MARK_DONE, None),
        ("postpone", postpone, POSTPONE, None),
        ("get_due", get_due, GET_DUE, SupportsResponse.ONLY),
        ("refresh_species", refresh_species, REFRESH, None),
        ("update_profile", update_profile, UPDATE_PROFILE, None),
        ("set_photo", set_photo, SET_PHOTO, None),
        ("get_history", get_history, HISTORY, SupportsResponse.ONLY),
        ("undo_event", undo_event, UNDO, None),
    ):
        hass.services.async_register(
            DOMAIN,
            name,
            handler,
            schema=schema,
            supports_response=response or SupportsResponse.NONE,
        )
