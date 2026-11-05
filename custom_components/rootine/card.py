"""Serve the dashboard card shipped with the integration."""

from __future__ import annotations

import time
from pathlib import Path

from homeassistant.core import HomeAssistant

from .const import VERSION

CARD_URL = "/rootine_static/rootine-card.js"
CARD_FILE = Path(__file__).parent / "frontend" / "rootine-card.js"


async def async_register_card(hass: HomeAssistant) -> None:
    """Register the static path and load the card in every dashboard (needs http + frontend)."""
    if "http" not in hass.config.components or "frontend" not in hass.config.components:
        return
    from homeassistant.components.frontend import add_extra_js_url
    from homeassistant.components.http import StaticPathConfig

    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(CARD_FILE), cache_headers=False)]
    )
    # A new URL on every start: if a phone cached a broken response for the card
    # (for example a proxy error page while HA was restarting), it is not reused.
    add_extra_js_url(hass, f"{CARD_URL}?v={VERSION}-{int(time.time()):x}")
