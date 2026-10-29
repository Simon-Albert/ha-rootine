"""Rootine – Pflegeroutinen für Pflanzen."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import ConfigType

from .card import async_register_card
from .const import DOMAIN
from .manager import RootineManager
from .repairs import async_watch_links
from .services import async_register_services

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.DATE,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.TODO,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type RootineConfigEntry = ConfigEntry[RootineManager]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async_register_services(hass)
    await async_register_card(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: RootineConfigEntry) -> bool:
    manager = RootineManager(hass, entry)
    await manager.async_load()
    entry.runtime_data = manager

    async def _save_on_stop(_event: Event) -> None:
        await manager.async_save()

    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _save_on_stop))
    # Strukturänderungen (Subentries, Optionen) laden den Eintrag neu. Alltagswerte
    # (Steckbrief, Standort, Knöpfe) liegen im Store und lösen nie ein Neuladen aus.
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    _remove_orphans(hass, entry, manager)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await manager.async_start()
    entry.async_on_unload(async_watch_links(hass, entry))
    return True


def _remove_orphans(
    hass: HomeAssistant, entry: RootineConfigEntry, manager: RootineManager
) -> None:
    """Entitäten entfernter Aufgaben aus der Registry löschen."""
    expected = manager.expected_unique_ids()
    registry = er.async_get(hass)
    for item in er.async_entries_for_config_entry(registry, entry.entry_id):
        if item.config_subentry_id is not None and item.unique_id not in expected:
            registry.async_remove(item.entity_id)


async def _async_reload(hass: HomeAssistant, entry: RootineConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: RootineConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_unload()
    return unloaded
