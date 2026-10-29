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
from .logic.oneoff import REMIND_MAX
from .logic.profile import apply_opb, parse_opb, update_fields
from .manager import PlantRuntime, RootineManager
from .photo import PhotoUnresolvable

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
_REMIND = vol.All(vol.Coerce(int), vol.Range(0, REMIND_MAX))
ADD_ONEOFF = vol.Schema(
    {
        **_ENTITY,
        vol.Required("name"): cv.string,
        vol.Required("due"): cv.date,
        vol.Optional("yearly", default=False): cv.boolean,
        vol.Optional("remind_days", default=0): _REMIND,
    }
)
UPDATE_ONEOFF = vol.Schema(
    {
        **_ENTITY,
        vol.Required("oneoff_id"): cv.string,
        vol.Optional("name"): cv.string,
        vol.Optional("due"): cv.date,
        vol.Optional("yearly"): cv.boolean,
        vol.Optional("remind_days"): _REMIND,
    }
)
REMOVE_ONEOFF = vol.Schema({**_ENTITY, vol.Required("oneoff_id"): cv.string})


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
    """A task key or the id of a one-time task."""
    if not plant.has_task(key) and plant.oneoff(key) is None:
        raise _fail("unknown_task", task=key)
    return key


def _oneoff_name(value: str) -> str:
    if not value.strip():
        raise _fail("name_required")
    return value.strip()


def _photo_id(value: Any) -> str | None:
    if isinstance(value, dict):
        return value.get("media_content_id") or None
    return value or None


async def _set_photo(manager: RootineManager, plant: PlantRuntime, value: Any) -> None:
    try:
        await manager.async_set_photo(plant.subentry_id, _photo_id(value))
    except PhotoUnresolvable as err:
        raise _fail("photo_unresolvable") from err


def async_register_services(hass: HomeAssistant) -> None:
    async def mark_done(call: ServiceCall) -> None:
        manager, plant = _resolve(hass, call.data["entity_id"])
        key = _task(plant, call.data["task"])
        done = manager.complete_oneoff if plant.oneoff(key) else manager.mark_done
        done(
            plant.subentry_id,
            key,
            SOURCE_SERVICE,
            when=call.data.get("when"),
            note=call.data.get("note"),
        )

    async def postpone(call: ServiceCall) -> None:
        manager, plant = _resolve(hass, call.data["entity_id"])
        key = _task(plant, call.data["task"])
        if plant.oneoff(key):
            manager.postpone_oneoff(plant.subentry_id, key, call.data["days"])
        else:
            manager.postpone(plant.subentry_id, key, call.data["days"])

    async def add_oneoff(call: ServiceCall) -> ServiceResponse:
        manager, plant = _resolve(hass, call.data["entity_id"])
        item = manager.add_oneoff(
            plant.subentry_id,
            _oneoff_name(call.data["name"]),
            call.data["due"],
            call.data["yearly"],
            call.data["remind_days"],
        )
        return {"id": item.id}

    async def update_oneoff(call: ServiceCall) -> None:
        manager, plant = _resolve(hass, call.data["entity_id"])
        changes = {
            k: call.data[k] for k in ("name", "due", "yearly", "remind_days") if k in call.data
        }
        if "name" in changes:
            changes["name"] = _oneoff_name(changes["name"])
        if not manager.update_oneoff(plant.subentry_id, call.data["oneoff_id"], **changes):
            raise _fail("unknown_oneoff")

    async def remove_oneoff(call: ServiceCall) -> None:
        manager, plant = _resolve(hass, call.data["entity_id"])
        if not manager.remove_oneoff(plant.subentry_id, call.data["oneoff_id"]):
            raise _fail("unknown_oneoff")

    async def get_due(call: ServiceCall) -> ServiceResponse:
        managers = [
            entry.runtime_data
            for entry in hass.config_entries.async_loaded_entries(DOMAIN)
            if hasattr(entry, "runtime_data")
        ]
        if not managers:
            return {"count": 0, "text": "Heute ist nichts zu tun.", "items": []}
        summary = managers[0].due_summary(
            include_soon=call.data["include_soon"], days_ahead=call.data["days_ahead"]
        )
        count, text, items = summary["count"], summary["text"], summary["items"]
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
        if "photo" in call.data:
            await _set_photo(manager, plant, call.data["photo"])
        manager.set_profile(plant.subentry_id, update_fields(plant.profile, changes))

    async def set_photo(call: ServiceCall) -> None:
        manager, plant = _resolve(hass, call.data["entity_id"])
        await _set_photo(manager, plant, call.data.get("photo"))

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
        ("add_oneoff", add_oneoff, ADD_ONEOFF, SupportsResponse.OPTIONAL),
        ("update_oneoff", update_oneoff, UPDATE_ONEOFF, None),
        ("remove_oneoff", remove_oneoff, REMOVE_ONEOFF, None),
    ):
        hass.services.async_register(
            DOMAIN,
            name,
            handler,
            schema=schema,
            supports_response=response or SupportsResponse.NONE,
        )
