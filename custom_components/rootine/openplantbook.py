"""Thin wrapper around the actions of the OpenPlantbook integration (plan 8.6).

Rootine never talks to the network itself; everything goes through the services of
the installed `openplantbook` integration. Without it every function degrades quietly.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

DOMAIN = "openplantbook"


def is_available(hass: HomeAssistant) -> bool:
    return hass.services.has_service(DOMAIN, "search") and hass.services.has_service(DOMAIN, "get")


async def async_search(hass: HomeAssistant, term: str) -> dict[str, str]:
    """Return {pid: display name}; empty when nothing is found or the call fails."""
    if not is_available(hass) or not term.strip():
        return {}
    try:
        result = await hass.services.async_call(
            DOMAIN, "search", {"alias": term.strip()}, blocking=True, return_response=True
        )
    except Exception:
        _LOGGER.debug("OpenPlantbook search failed", exc_info=True)
        return {}
    return {str(k): str(v) for k, v in (result or {}).items()}


async def async_get(hass: HomeAssistant, pid: str) -> dict[str, Any] | None:
    """Return the species details or None when unavailable."""
    if not is_available(hass):
        return None
    try:
        result = await hass.services.async_call(
            DOMAIN, "get", {"species": pid, "include": "care"}, blocking=True, return_response=True
        )
    except Exception:
        _LOGGER.debug("OpenPlantbook get failed", exc_info=True)
        return None
    return dict(result) if result else None
