"""Resolve the photo of a plant to a URL the frontend can show (plan 8.10)."""

from __future__ import annotations

import re
from datetime import timedelta

from homeassistant.components.media_source import Unresolvable, async_resolve_media
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

UPLOAD_PREFIX = "media-source://image_upload/"
_UPLOAD_ID = re.compile(r"^[A-Za-z0-9_-]+$")
# Signed URLs for media behind authentication; refreshed at startup and every midnight.
SIGN_VALIDITY = timedelta(days=3)


class PhotoUnresolvable(HomeAssistantError):
    """The selected media cannot be shown as a photo."""


async def async_photo_url(hass: HomeAssistant, media_content_id: str) -> str:
    """URL for an image upload or any other media source item; raises PhotoUnresolvable."""
    if media_content_id.startswith(UPLOAD_PREFIX):
        image_id = media_content_id[len(UPLOAD_PREFIX) :]
        if not _UPLOAD_ID.match(image_id):
            raise PhotoUnresolvable(media_content_id)
        return f"/api/image/serve/{image_id}/512x512"  # served without authentication
    try:
        item = await async_resolve_media(hass, media_content_id, None)
    except (Unresolvable, HomeAssistantError, ValueError) as err:
        raise PhotoUnresolvable(media_content_id) from err
    if item.mime_type and not item.mime_type.startswith("image/"):
        raise PhotoUnresolvable(media_content_id)
    url = item.url
    if url.startswith("/") and "http" in hass.config.components:
        from homeassistant.components.http.auth import async_sign_path

        url = async_sign_path(hass, url, SIGN_VALIDITY, use_content_user=True)
    return url
