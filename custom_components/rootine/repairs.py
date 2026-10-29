"""Repair issues for linked entities that are gone or renamed, and the fix flow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import voluptuous as vol
from homeassistant import data_entry_flow
from homeassistant.components.repairs import RepairsFlow
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers import selector
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.start import async_at_started

from .const import (
    CONF_BATTERY_ENTITY,
    CONF_MOISTURE_ENTITY,
    CONF_OUTDOOR_TEMP_ENTITY,
    CONF_RAIN_ENTITY,
    CONF_TEMPERATURE_ENTITY,
    CONF_VALVE_ENTITY,
    CONF_WEATHER_ENTITY,
    DOMAIN,
    SUBENTRY_PLANT,
)

ISSUE_PREFIX = "missing_"
FIELD = "entity_id"

# entity selector filter per linked field: (domains, device class)
SELECTORS: dict[str, tuple[tuple[str, ...], str | None]] = {
    CONF_MOISTURE_ENTITY: (("sensor",), "moisture"),
    CONF_TEMPERATURE_ENTITY: (("sensor",), "temperature"),
    CONF_BATTERY_ENTITY: (("sensor",), "battery"),
    CONF_VALVE_ENTITY: (("switch", "valve"), None),
    CONF_RAIN_ENTITY: (("sensor",), "precipitation"),
    CONF_WEATHER_ENTITY: (("weather",), None),
    CONF_OUTDOOR_TEMP_ENTITY: (("sensor",), "temperature"),
}
MAIN_KEYS = (CONF_RAIN_ENTITY, CONF_WEATHER_ENTITY, CONF_OUTDOOR_TEMP_ENTITY)
PLANT_KEYS = (CONF_MOISTURE_ENTITY, CONF_TEMPERATURE_ENTITY, CONF_BATTERY_ENTITY, CONF_VALVE_ENTITY)


@dataclass(frozen=True)
class Link:
    """One linked entity: in the main options (subentry_id None) or in a plant."""

    subentry_id: str | None
    key: str
    entity_id: str
    owner: str

    @property
    def issue_id(self) -> str:
        return f"{ISSUE_PREFIX}{self.subentry_id or 'main'}_{self.key}"


def links(entry: ConfigEntry) -> list[Link]:
    result = [
        Link(None, key, entry.options[key], entry.title)
        for key in MAIN_KEYS
        if entry.options.get(key)
    ]
    for sid, subentry in entry.subentries.items():
        if subentry.subentry_type != SUBENTRY_PLANT:
            continue
        name = subentry.data.get("name", subentry.title)
        result.extend(
            Link(sid, key, subentry.data[key], name) for key in PLANT_KEYS if subentry.data.get(key)
        )
    return result


def is_missing(hass: HomeAssistant, entity_id: str) -> bool:
    """No state and no usable registry entry (deleted, renamed or disabled)."""
    if hass.states.get(entity_id) is not None:
        return False
    item = er.async_get(hass).async_get(entity_id)
    # a registry entry without a state is fine: its integration may still be loading
    return item is None or item.disabled_by is not None


@callback
def async_check_links(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Create issues for missing links and remove the ones that no longer apply."""
    missing = {link.issue_id: link for link in links(entry) if is_missing(hass, link.entity_id)}
    for link in missing.values():
        ir.async_create_issue(
            hass,
            DOMAIN,
            link.issue_id,
            is_fixable=True,
            is_persistent=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=f"{ISSUE_PREFIX}{link.key}",
            translation_placeholders={"entity": link.entity_id, "plant": link.owner},
            data={"entry_id": entry.entry_id, "subentry_id": link.subentry_id, "key": link.key},
        )
    _delete_issues(hass, keep=set(missing))


def _delete_issues(hass: HomeAssistant, keep: set[str] | None = None) -> None:
    keep = keep or set()
    for domain, issue_id in list(ir.async_get(hass).issues):
        if domain == DOMAIN and issue_id.startswith(ISSUE_PREFIX) and issue_id not in keep:
            ir.async_delete_issue(hass, DOMAIN, issue_id)


@callback
def async_watch_links(hass: HomeAssistant, entry: ConfigEntry) -> CALLBACK_TYPE:
    """Check once Home Assistant has started, then on every change of a linked entity."""
    watched = {link.entity_id for link in links(entry)}
    unsubs: list[CALLBACK_TYPE] = []

    @callback
    def _check(*_: Any) -> None:
        async_check_links(hass, entry)

    @callback
    def _registry_filter(data: er.EventEntityRegistryUpdatedData) -> bool:
        return data["entity_id"] in watched or data.get("old_entity_id") in watched

    @callback
    def _started(_hass: HomeAssistant) -> None:
        _check()
        if watched:
            unsubs.append(async_track_state_change_event(hass, list(watched), _check))
        unsubs.append(
            hass.bus.async_listen(
                er.EVENT_ENTITY_REGISTRY_UPDATED, _check, event_filter=_registry_filter
            )
        )

    unsubs.append(async_at_started(hass, _started))

    @callback
    def _unwatch() -> None:
        for unsub in unsubs:
            unsub()
        # issues describe the loaded configuration; the next setup creates them again
        _delete_issues(hass)

    return _unwatch


class LinkFixFlow(RepairsFlow):
    """Pick a replacement for a missing entity, or leave the field empty to unlink it."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._entry_id: str = data["entry_id"]
        self._subentry_id: str | None = data.get("subentry_id")
        self._key: str = data["key"]

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        # the repairs manager passes the issue data as user input of the first step
        return await self.async_step_relink()

    async def async_step_relink(
        self, user_input: dict[str, Any] | None = None
    ) -> data_entry_flow.FlowResult:
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        if entry is None:
            return self.async_abort(reason="not_loaded")
        subentry = entry.subentries.get(self._subentry_id) if self._subentry_id else None
        if self._subentry_id and subentry is None:
            return self.async_abort(reason="not_loaded")
        current: dict[str, Any] = dict(subentry.data if subentry else entry.options)
        if user_input is not None:
            current.pop(self._key, None)
            if user_input.get(FIELD):
                current[self._key] = user_input[FIELD]
            if subentry:
                self.hass.config_entries.async_update_subentry(entry, subentry, data=current)
            else:
                self.hass.config_entries.async_update_entry(entry, options=current)
            return self.async_create_entry(data={})
        domains, device_class = SELECTORS[self._key]
        config: dict[str, Any] = {"domain": list(domains)}
        if device_class:
            config["device_class"] = device_class
        schema = vol.Schema(
            {vol.Optional(FIELD): selector.EntitySelector(selector.EntitySelectorConfig(**config))}
        )
        owner = subentry.data.get("name", subentry.title) if subentry else entry.title
        return self.async_show_form(
            step_id="relink",
            data_schema=schema,
            description_placeholders={"entity": current.get(self._key) or "–", "plant": owner},
        )


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None
) -> RepairsFlow:
    return LinkFixFlow(data or {})
