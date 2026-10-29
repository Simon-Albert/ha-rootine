import pytest

from custom_components.rootine.const import SUBENTRY_PLANT

from .conftest import add_plant, setup_main


@pytest.fixture(autouse=True)
async def tz(hass, freezer):
    await hass.config.async_set_time_zone("Europe/Berlin")
    freezer.move_to("2026-10-29 12:00:00+01:00")


async def start(hass, entry, source="user", subentry_id=None):
    context = {"source": source}
    if subentry_id:
        context["subentry_id"] = subentry_id
    return await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_PLANT), context=context
    )


async def test_main_flow_with_options(hass):
    result = await hass.config_entries.flow.async_init("rootine", context={"source": "user"})
    assert result["type"] == "form"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"rain_threshold": 4.0, "default_location": "indoor"}
    )
    assert result["type"] == "create_entry"
    assert result["options"] == {"rain_threshold": 4.0, "default_location": "indoor"}
    # single_config_entry
    again = await hass.config_entries.flow.async_init("rootine", context={"source": "user"})
    assert again["type"] == "abort"


async def test_options_flow(hass):
    entry = await setup_main(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"rain_threshold": 3.0, "default_location": "outdoor"}
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    assert entry.options["rain_threshold"] == 3.0
    assert entry.state.value == "loaded"


async def test_create_by_hand_with_profile(hass):
    entry = await setup_main(hass)
    await add_plant(
        hass,
        entry,
        "Satsuma",
        profile={
            "common_name": "Satsuma-Mandarine",
            "cultivar": "Iwasaki",
            "care_watering": "Gleichmäßig feucht",
            "photo": {
                "media_content_id": "media-source://image_upload/01ABC",
                "media_content_type": "image/jpeg",
            },
        },
    )
    state = hass.states.get("sensor.satsuma_care_status")
    assert state.attributes["profile"]["cultivar"] == "Iwasaki"
    assert state.attributes["profile"]["care.watering"] == "Gleichmäßig feucht"
    assert state.attributes["entity_picture"] == "/api/image/serve/01ABC/512x512"


async def test_duplicate_and_empty_name(hass):
    entry = await setup_main(hass)
    await add_plant(hass, entry, "Kaffee")
    for name, error in (("kaffee", "name_exists"), ("  ", "invalid_name")):
        result = await start(hass, entry)
        result = await hass.config_entries.subentries.async_configure(
            result["flow_id"], {"name": name, "location": "indoor"}
        )
        assert result["errors"] == {"base": error}


async def test_invalid_schedule_shows_line(hass):
    entry = await setup_main(hass)
    result = await start(hass, entry)
    flow = hass.config_entries.subentries
    result = await flow.async_configure(result["flow_id"], {"name": "A", "location": "indoor"})
    result = await flow.async_configure(result["flow_id"], {})
    result = await flow.async_configure(result["flow_id"], {})
    result = await flow.async_configure(
        result["flow_id"],
        {
            "mode": "timer",
            "schedule_text": "01.03.–30.06.: 6\n01.06.–31.10.: 7",
            "last_done": "2026-10-01",
        },
    )
    assert result["errors"] == {"base": "overlap"}
    assert result["description_placeholders"]["line"] == "2"
    assert result["description_placeholders"]["other"] == "1"


async def test_fertilize_empty_means_no_task(hass):
    entry = await setup_main(hass)
    await add_plant(hass, entry, "Nur Wasser", fertilize="")
    assert hass.states.get("sensor.nur_wasser_watering")
    assert hass.states.get("sensor.nur_wasser_fertilizing") is None


async def test_reconfigure_profile_no_reload(hass):
    entry = await setup_main(hass)
    sid = await add_plant(hass, entry, "Kaffee", profile={"common_name": "Kaffee"})
    manager = entry.runtime_data
    result = await start(hass, entry, "reconfigure", sid)
    assert result["type"] == "menu"
    flow = hass.config_entries.subentries
    result = await flow.async_configure(result["flow_id"], {"next_step_id": "profile_edit"})
    result = await flow.async_configure(
        result["flow_id"], {"common_name": "Kaffee", "pot": "Terrakotta 28 cm", "notes": ""}
    )
    assert result["type"] == "abort" and result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert entry.runtime_data is manager
    profile = manager.plants[sid].profile
    assert profile.pot == "Terrakotta 28 cm"
    assert profile.manual_fields == {"common_name", "pot"}
    assert (
        hass.states.get("sensor.kaffee_care_status").attributes["profile"]["pot"]
        == "Terrakotta 28 cm"
    )


async def test_photo_set_replace_remove(hass):
    entry = await setup_main(hass)
    sid = await add_plant(hass, entry, "Kaffee")
    manager = entry.runtime_data
    flow = hass.config_entries.subentries

    async def set_photo(photo):
        result = await start(hass, entry, "reconfigure", sid)
        result = await flow.async_configure(result["flow_id"], {"next_step_id": "photo"})
        data = {"photo": photo} if photo else {}
        result = await flow.async_configure(result["flow_id"], data)
        assert result["reason"] == "reconfigure_successful"
        await hass.async_block_till_done()

    pic = lambda: hass.states.get("sensor.kaffee_care_status").attributes.get("entity_picture")  # noqa: E731
    assert pic() is None
    await set_photo(
        {"media_content_id": "media-source://image_upload/AAA", "media_content_type": "image/png"}
    )
    assert pic() == "/api/image/serve/AAA/512x512"
    await set_photo(
        {"media_content_id": "media-source://image_upload/BBB", "media_content_type": "image/png"}
    )
    assert pic() == "/api/image/serve/BBB/512x512"
    await set_photo(None)
    assert pic() is None
    assert entry.runtime_data is manager  # never a reload


async def test_reconfigure_water_reloads_and_keeps_state(hass):
    entry = await setup_main(hass)
    sid = await add_plant(hass, entry, "Kaffee", last_done="2026-10-10", water="ganzjährig: 6")
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.kaffee_watered"}, blocking=True
    )
    flow = hass.config_entries.subentries
    result = await start(hass, entry, "reconfigure", sid)
    result = await flow.async_configure(result["flow_id"], {"next_step_id": "water_edit"})
    bad = await flow.async_configure(
        result["flow_id"], {"mode": "timer", "schedule_text": "quatsch"}
    )
    assert bad["errors"] == {"base": "invalid_line"}
    result = await flow.async_configure(
        result["flow_id"], {"mode": "timer", "schedule_text": "ganzjährig: 3"}
    )
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert entry.subentries[sid].data["tasks"][0]["schedule_text"] == "ganzjährig: 3"
    assert hass.states.get("date.kaffee_watering_last_done").state == "2026-10-29"
    assert hass.states.get("sensor.kaffee_watering").attributes["interval_days"] == 3


async def test_reconfigure_fertilize_add_and_remove(hass):
    entry = await setup_main(hass)
    sid = await add_plant(hass, entry, "Kaffee", fertilize="")
    flow = hass.config_entries.subentries

    async def edit(text):
        result = await start(hass, entry, "reconfigure", sid)
        result = await flow.async_configure(result["flow_id"], {"next_step_id": "fertilize_edit"})
        result = await flow.async_configure(result["flow_id"], {"schedule_text": text})
        assert result["reason"] == "reconfigure_successful"
        await hass.async_block_till_done()

    await edit("ganzjährig: 21")
    assert hass.states.get("sensor.kaffee_fertilizing")
    await edit("")
    assert hass.states.get("sensor.kaffee_fertilizing") is None


async def test_reconfigure_rename(hass):
    entry = await setup_main(hass)
    sid = await add_plant(hass, entry, "Kaffee")
    await add_plant(hass, entry, "Kirsche")
    flow = hass.config_entries.subentries
    result = await start(hass, entry, "reconfigure", sid)
    result = await flow.async_configure(result["flow_id"], {"next_step_id": "general"})
    clash = await flow.async_configure(result["flow_id"], {"name": "Kirsche", "location": "indoor"})
    assert clash["errors"] == {"base": "name_exists"}
    result = await flow.async_configure(
        result["flow_id"], {"name": "Coffea", "location": "outdoor"}
    )
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert entry.subentries[sid].title == "Coffea"
    assert entry.subentries[sid].unique_id == "coffea"
    assert entry.runtime_data.plants[sid].settings.location == "outdoor"


async def _water_default(hass, entry, location):
    flow = hass.config_entries.subentries
    result = await start(hass, entry)
    result = await flow.async_configure(
        result["flow_id"], {"name": f"P{location}", "location": location}
    )
    result = await flow.async_configure(result["flow_id"], {})
    result = await flow.async_configure(result["flow_id"], {})
    mode = next(k for k in result["data_schema"].schema if str(k) == "mode")
    return mode.default()


async def test_rain_mode_only_preselected_with_rain_sensor(hass):
    entry = await setup_main(hass)
    assert await _water_default(hass, entry, "outdoor") == "timer"
    entry2 = await setup_main_with_rain(hass)
    assert await _water_default(hass, entry2, "outdoor") == "rain"


async def setup_main_with_rain(hass):
    entry = next(iter(hass.config_entries.async_entries("rootine")))
    hass.config_entries.async_update_entry(entry, options={"rain_entity": "sensor.rain"})
    await hass.async_block_till_done()
    return entry
