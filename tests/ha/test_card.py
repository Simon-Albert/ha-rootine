import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.rootine.card import CARD_FILE, CARD_URL, async_register_card
from custom_components.rootine.const import VERSION


def test_version_matches_manifest():
    manifest = Path(__file__).parents[2] / "custom_components" / "rootine" / "manifest.json"
    assert json.loads(manifest.read_text())["version"] == VERSION
    assert CARD_FILE.exists()


async def test_card_registered_when_frontend_loaded(hass):
    hass.config.components.update({"http", "frontend"})
    hass.http = MagicMock()
    hass.http.async_register_static_paths = AsyncMock()
    with patch("homeassistant.components.frontend.add_extra_js_url") as add:
        await async_register_card(hass)
    hass.http.async_register_static_paths.assert_awaited_once()
    add.assert_called_once()
    assert add.call_args.args[1].startswith(f"{CARD_URL}?v={VERSION}-")


async def test_card_url_changes_with_every_start(hass):
    """A response a phone cached while HA was restarting must not be reused after the next start."""
    hass.config.components.update({"http", "frontend"})
    hass.http = MagicMock()
    hass.http.async_register_static_paths = AsyncMock()
    urls = []
    for start in (1_800_000_000, 1_800_000_060):
        with (
            patch("custom_components.rootine.card.time.time", return_value=start),
            patch("homeassistant.components.frontend.add_extra_js_url") as add,
        ):
            await async_register_card(hass)
        urls.append(add.call_args.args[1])
    assert urls[0] != urls[1]


async def test_card_skipped_without_frontend(hass):
    hass.http = MagicMock()
    hass.http.async_register_static_paths = AsyncMock()
    await async_register_card(hass)
    hass.http.async_register_static_paths.assert_not_awaited()
