"""Photos: image upload in the selector, other media sources resolved, unresolvable rejected."""

from unittest.mock import patch

import pytest
from homeassistant.components.media_source.models import PlayMedia
from homeassistant.exceptions import ServiceValidationError

from custom_components.rootine.const import SUBENTRY_PLANT

from .conftest import add_plant, setup_main

LOCAL = {
    "media_content_id": "media-source://media_source/local/plants/a.jpg",
    "media_content_type": "image/jpeg",
}
RESOLVE = "custom_components.rootine.photo.async_resolve_media"


@pytest.fixture(autouse=True)
async def tz(hass, freezer):
    await hass.config.async_set_time_zone("Europe/Berlin")
    freezer.move_to("2026-10-29 12:00:00+01:00")


def test_selector_offers_image_upload():
    from custom_components.rootine import config_flow

    assert config_flow._PHOTO.config["accept"] == ["image/*"]
    assert config_flow._PHOTO.config["image_upload"] is True


async def _photo_step(hass, entry, sid, photo):
    flow = hass.config_entries.subentries
    result = await flow.async_init(
        (entry.entry_id, SUBENTRY_PLANT), context={"source": "reconfigure", "subentry_id": sid}
    )
    result = await flow.async_configure(result["flow_id"], {"next_step_id": "photo"})
    return await flow.async_configure(result["flow_id"], {"photo": photo})


async def test_other_media_source_is_resolved(hass):
    entry = await setup_main(hass)
    sid = await add_plant(hass, entry, "Kaffee")
    with patch(RESOLVE, return_value=PlayMedia("/media/local/plants/a.jpg", "image/jpeg")):
        result = await _photo_step(hass, entry, sid, LOCAL)
        await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert entry.runtime_data.plants[sid].profile.photo == LOCAL["media_content_id"]
    picture = hass.states.get("sensor.kaffee_care_status").attributes["entity_picture"]
    # media behind authentication gets a signed URL, so the frontend can load it as <img>
    assert picture.startswith("/media/local/plants/a.jpg?authSig=")


async def test_unresolvable_photo_is_rejected_in_the_form(hass):
    entry = await setup_main(hass)
    sid = await add_plant(hass, entry, "Kaffee")
    result = await _photo_step(hass, entry, sid, LOCAL)  # media_source not loaded -> unresolvable
    assert result["type"] == "form"
    assert result["errors"] == {"photo": "photo_unresolvable"}
    assert entry.runtime_data.plants[sid].profile.photo is None


async def test_unresolvable_photo_is_rejected_when_creating(hass):
    entry = await setup_main(hass)
    flow = hass.config_entries.subentries
    result = await flow.async_init((entry.entry_id, SUBENTRY_PLANT), context={"source": "user"})
    result = await flow.async_configure(result["flow_id"], {"name": "A", "location": "indoor"})
    result = await flow.async_configure(result["flow_id"], {"photo": LOCAL})
    assert result["step_id"] == "profile"
    assert result["errors"] == {"photo": "photo_unresolvable"}


async def test_set_photo_service_rejects_unresolvable(hass):
    entry = await setup_main(hass)
    await add_plant(hass, entry, "Kaffee")
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "rootine",
            "set_photo",
            {"entity_id": "sensor.kaffee_care_status", "photo": LOCAL},
            blocking=True,
        )


async def test_uploaded_photo_needs_no_resolving(hass):
    entry = await setup_main(hass)
    sid = await add_plant(hass, entry, "Kaffee")
    upload = {
        "media_content_id": "media-source://image_upload/ABC",
        "media_content_type": "image/png",
    }
    result = await _photo_step(hass, entry, sid, upload)
    await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert (
        hass.states.get("sensor.kaffee_care_status").attributes["entity_picture"]
        == "/api/image/serve/ABC/512x512"
    )
