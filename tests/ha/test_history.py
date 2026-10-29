"""History is the source of truth: last_done is the newest valid entry (review item 3)."""

import pytest

from .conftest import add_plant, setup_main

ENTITY = "sensor.kaffee_care_status"


@pytest.fixture(autouse=True)
async def tz(hass, freezer):
    await hass.config.async_set_time_zone("Europe/Berlin")
    freezer.move_to("2026-10-29 12:00:00+01:00")


async def mark(hass, when, note=None):
    data = {"entity_id": ENTITY, "task": "water", "when": when}
    if note:
        data["note"] = note
    await hass.services.async_call("rootine", "mark_done", data, blocking=True)


async def history(hass):
    result = await hass.services.async_call(
        "rootine", "get_history", {"entity_id": ENTITY}, blocking=True, return_response=True
    )
    return result["items"]


async def test_backfilling_never_moves_last_done_back(hass):
    entry = await setup_main(hass)
    await add_plant(
        hass, entry, "Kaffee", water="ganzjährig: 6", last_done="2026-10-20", fertilize=""
    )
    await mark(hass, "2026-10-28T09:00:00+01:00")
    await mark(hass, "2026-10-24T09:00:00+02:00", note="nachgetragen")  # older entry added later
    state = hass.states.get("sensor.kaffee_watering")
    assert state.attributes["last_done"].startswith("2026-10-28T09:00")
    assert state.attributes["last_source"] == "service"
    assert hass.states.get("date.kaffee_watering_last_done").state == "2026-10-28"
    items = await history(hass)
    assert [i["ts"][:10] for i in items] == ["2026-10-28", "2026-10-24", "2026-10-20"]
    # undoing the newest falls back to the newest remaining entry, i.e. the backfilled one
    await hass.services.async_call(
        "rootine", "undo_event", {"entity_id": ENTITY, "event_id": items[0]["id"]}, blocking=True
    )
    assert hass.states.get("date.kaffee_watering_last_done").state == "2026-10-24"


async def test_order_is_by_time_across_the_dst_change(hass):
    entry = await setup_main(hass)
    await add_plant(
        hass, entry, "Kaffee", water="ganzjährig: 6", last_done="2026-10-20", fertilize=""
    )
    # 25.10.2026: the hour 02:00-03:00 exists twice. 02:10 CET is later than 02:30 CEST.
    await mark(hass, "2026-10-25T02:10:00+01:00")
    await mark(hass, "2026-10-25T02:30:00+02:00")
    items = await history(hass)
    assert [i["ts"] for i in items[:2]] == [
        "2026-10-25T02:10:00+01:00",
        "2026-10-25T02:30:00+02:00",
    ]
    assert (
        hass.states.get("sensor.kaffee_watering").attributes["last_done"]
        == "2026-10-25T02:10:00+01:00"
    )


async def test_date_correction_still_wins(hass):
    """The date entity is an explicit correction: newer entries are marked undone."""
    entry = await setup_main(hass)
    sid = await add_plant(
        hass, entry, "Kaffee", water="ganzjährig: 6", last_done="2026-10-20", fertilize=""
    )
    await mark(hass, "2026-10-28T09:00:00+01:00")
    await hass.services.async_call(
        "date",
        "set_value",
        {"entity_id": "date.kaffee_watering_last_done", "date": "2026-10-26"},
        blocking=True,
    )
    assert hass.states.get("date.kaffee_watering_last_done").state == "2026-10-26"
    log = entry.runtime_data.plants[sid].log
    corrected = next(e for e in log if e["ts"].startswith("2026-10-28"))
    assert corrected["undone"] is True
