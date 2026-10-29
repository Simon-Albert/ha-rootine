"""One-time tasks per plant in Home Assistant (item B6)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.components.todo import DOMAIN as TODO_DOMAIN
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.rootine.const import SUBENTRY_PLANT

from .conftest import add_plant, setup_main

CARE = "sensor.kaffee_care_status"


@pytest.fixture(autouse=True)
async def tz(hass, freezer):
    await hass.config.async_set_time_zone("Europe/Berlin")
    freezer.move_to("2026-10-29 12:00:00+01:00")


async def _plant(hass):
    entry = await setup_main(hass)
    sid = await add_plant(hass, entry, "Kaffee", last_done="2026-10-29")
    return entry, sid


async def _add(hass, **data) -> str:
    response = await hass.services.async_call(
        "rootine",
        "add_oneoff",
        {"entity_id": CARE, **data},
        blocking=True,
        return_response=True,
    )
    return response["id"]


def _oneoffs(hass):
    return {o["name"]: o for o in hass.states.get(CARE).attributes["oneoffs"]}


async def _due(hass, **data):
    return await hass.services.async_call(
        "rootine", "get_due", data, blocking=True, return_response=True
    )


async def _todo(hass):
    response = await hass.services.async_call(
        TODO_DOMAIN,
        "get_items",
        {"entity_id": "todo.rootine_plant_care"},
        blocking=True,
        return_response=True,
    )
    return response["todo.rootine_plant_care"]["items"]


async def test_add_and_show_in_status(hass):
    await _plant(hass)
    assert hass.states.get(CARE).state == "ok"
    oid = await _add(hass, name="Umtopfen", due="2026-10-29")
    assert oid.startswith("once_")
    assert _oneoffs(hass)["Umtopfen"] == {
        "id": oid,
        "name": "Umtopfen",
        "due": "2026-10-29",
        "yearly": False,
        "remind_days": 0,
        "status": "due",
        "days": 0,
    }
    assert hass.states.get(CARE).state == "due"
    assert hass.states.get("sensor.rootine_due_care_tasks").state == "1"


async def test_reminder_window_shows_in_get_due_and_todo_but_not_in_status(hass):
    await _plant(hass)
    await _add(hass, name="Umtopfen", due="2026-11-03", remind_days=7)
    assert _oneoffs(hass)["Umtopfen"]["status"] == "soon"
    assert hass.states.get(CARE).state == "ok"  # "soon" in the status means tomorrow
    due = await _due(hass)
    assert due["count"] == 0
    assert [i["task_name"] for i in due["items"]] == ["Umtopfen"]
    assert due["items"][0]["due"] == "2026-11-03" and due["items"][0]["days"] == 5
    assert due["text"] == "Demnächst: Kaffee Umtopfen erledigen (in 5 Tagen)."
    assert (await _due(hass, include_soon=False))["items"] == []
    items = await _todo(hass)
    assert [i["summary"] for i in items] == ["Kaffee: Umtopfen"]
    assert items[0]["due"] == "2026-11-03"


async def test_without_reminder_only_from_the_day_before(hass):
    await _plant(hass)
    await _add(hass, name="Schneiden", due="2026-11-03")
    assert (await _due(hass))["items"] == []
    assert await _todo(hass) == []
    preview = await _due(hass, days_ahead=7)
    assert preview["text"] == "Demnächst: Kaffee Schneiden erledigen (in 5 Tagen)."


async def test_texts_for_due_and_overdue(hass):
    await _plant(hass)
    await _add(hass, name="Umtopfen", due="2026-10-29")
    await _add(hass, name="Schneiden", due="2026-10-26")
    due = await _due(hass)
    assert due["count"] == 2
    assert due["text"] == (
        "Heute zu tun: Kaffee Umtopfen erledigen. Überfällig: Kaffee Schneiden erledigen."
    )
    texts = {i["task_name"]: i["text"] for i in due["items"]}
    assert texts["Schneiden"] == "Kaffee: Schneiden ist seit 3 Tagen überfällig."
    assert hass.states.get(CARE).state == "overdue"


async def test_done_one_time_goes_to_history_and_disappears(hass):
    entry, sid = await _plant(hass)
    oid = await _add(hass, name="Umtopfen", due="2026-10-29")
    await hass.services.async_call(
        "rootine", "mark_done", {"entity_id": CARE, "task": oid}, blocking=True
    )
    assert _oneoffs(hass) == {}
    assert hass.states.get(CARE).state == "ok"
    done = next(h for h in entry.runtime_data.history(sid) if h["task"] == oid)
    assert done["task_name"] == "Umtopfen" and done["oneoff"]["due"] == "2026-10-29"
    # undo brings it back
    await hass.services.async_call(
        "rootine", "undo_event", {"entity_id": CARE, "event_id": done["id"]}, blocking=True
    )
    assert _oneoffs(hass)["Umtopfen"]["status"] == "due"


async def test_done_yearly_moves_to_next_year_and_undo_moves_back(hass):
    entry, sid = await _plant(hass)
    oid = await _add(hass, name="Umtopfen", due="2026-10-27", yearly=True, remind_days=14)
    events = []
    hass.bus.async_listen("rootine_task_done", events.append)
    await hass.services.async_call(
        "rootine", "mark_done", {"entity_id": CARE, "task": oid}, blocking=True
    )
    await hass.async_block_till_done()
    item = _oneoffs(hass)["Umtopfen"]
    assert (item["id"], item["due"], item["status"]) == (oid, "2027-10-27", "ok")
    assert events[0].data["task"] == oid and events[0].data["task_name"] == "Umtopfen"
    event_id = next(h["id"] for h in entry.runtime_data.history(sid) if h["task"] == oid)
    await hass.services.async_call(
        "rootine", "undo_event", {"entity_id": CARE, "event_id": event_id}, blocking=True
    )
    assert _oneoffs(hass)["Umtopfen"]["due"] == "2026-10-27"


async def test_done_through_the_todo_list(hass):
    await _plant(hass)
    await _add(hass, name="Umtopfen", due="2026-10-28")
    item = (await _todo(hass))[0]
    await hass.services.async_call(
        TODO_DOMAIN,
        "update_item",
        {"entity_id": "todo.rootine_plant_care", "item": item["uid"], "status": "completed"},
        blocking=True,
    )
    assert _oneoffs(hass) == {}


async def test_update_postpone_and_remove_by_action(hass):
    await _plant(hass)
    oid = await _add(hass, name="Umtopfen", due="2026-10-29")
    await hass.services.async_call(
        "rootine",
        "update_oneoff",
        {"entity_id": CARE, "oneoff_id": oid, "name": "Umtopfen in Kübel", "yearly": True},
        blocking=True,
    )
    item = _oneoffs(hass)["Umtopfen in Kübel"]
    assert (item["due"], item["yearly"]) == ("2026-10-29", True)
    await hass.services.async_call(
        "rootine", "postpone", {"entity_id": CARE, "task": oid, "days": 3}, blocking=True
    )
    assert _oneoffs(hass)["Umtopfen in Kübel"]["due"] == "2026-11-01"
    await hass.services.async_call(
        "rootine", "remove_oneoff", {"entity_id": CARE, "oneoff_id": oid}, blocking=True
    )
    assert _oneoffs(hass) == {}
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "rootine", "remove_oneoff", {"entity_id": CARE, "oneoff_id": oid}, blocking=True
        )


async def test_invalid_input_is_rejected(hass):
    await _plant(hass)
    with pytest.raises(ServiceValidationError):
        await _add(hass, name="  ", due="2026-10-29")
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "rootine", "mark_done", {"entity_id": CARE, "task": "once_missing"}, blocking=True
        )


async def test_status_changes_at_midnight_and_survives_restart(hass, freezer):
    entry, _sid = await _plant(hass)
    await _add(hass, name="Umtopfen", due="2026-10-30")
    assert _oneoffs(hass)["Umtopfen"]["status"] == "soon"
    freezer.move_to("2026-10-30 00:00:30+01:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert _oneoffs(hass)["Umtopfen"]["status"] == "due"
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert _oneoffs(hass)["Umtopfen"]["status"] == "due"
    assert hass.states.get(CARE).state == "due"


async def test_changing_one_offs_never_reloads(hass):
    entry, _sid = await _plant(hass)
    manager = entry.runtime_data
    oid = await _add(hass, name="Umtopfen", due="2026-11-20")
    await hass.services.async_call(
        "rootine", "remove_oneoff", {"entity_id": CARE, "oneoff_id": oid}, blocking=True
    )
    await hass.async_block_till_done()
    assert entry.runtime_data is manager


# --- reconfigure menu ----------------------------------------------------------------------


async def _menu(hass, entry, sid, step):
    flow = hass.config_entries.subentries
    result = await flow.async_init(
        (entry.entry_id, SUBENTRY_PLANT), context={"source": "reconfigure", "subentry_id": sid}
    )
    result = await flow.async_configure(result["flow_id"], {"next_step_id": "oneoffs"})
    assert result["type"] == "menu"
    return await flow.async_configure(result["flow_id"], {"next_step_id": step})


async def test_reconfigure_add_edit_remove(hass):
    entry, sid = await _plant(hass)
    flow = hass.config_entries.subentries
    manager = entry.runtime_data
    for step in ("edit_oneoff", "remove_oneoff"):
        result = await _menu(hass, entry, sid, step)
        assert result["type"] == "abort" and result["reason"] == "no_oneoffs"

    result = await _menu(hass, entry, sid, "add_oneoff")
    assert result["step_id"] == "add_oneoff"
    result = await flow.async_configure(
        result["flow_id"], {"name": "Umtopfen", "due": "2026-11-15", "remind_days": 7}
    )
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert entry.runtime_data is manager  # store value, no reload
    item = _oneoffs(hass)["Umtopfen"]
    assert (item["due"], item["remind_days"], item["yearly"]) == ("2026-11-15", 7, False)

    result = await _menu(hass, entry, sid, "edit_oneoff")
    result = await flow.async_configure(result["flow_id"], {"oneoff": item["id"]})
    assert result["step_id"] == "edit_oneoff_form"
    result = await flow.async_configure(
        result["flow_id"],
        {"name": "Umtopfen", "due": "2026-11-20", "yearly": True, "remind_days": 0},
    )
    assert result["reason"] == "reconfigure_successful"
    item = _oneoffs(hass)["Umtopfen"]
    assert (item["due"], item["remind_days"], item["yearly"]) == ("2026-11-20", 0, True)

    result = await _menu(hass, entry, sid, "remove_oneoff")
    result = await flow.async_configure(result["flow_id"], {"oneoff": item["id"]})
    assert result["reason"] == "reconfigure_successful"
    assert _oneoffs(hass) == {}


async def test_reconfigure_rejects_an_empty_name(hass):
    entry, sid = await _plant(hass)
    result = await _menu(hass, entry, sid, "add_oneoff")
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"name": " ", "due": "2026-11-15"}
    )
    assert result["type"] == "form" and result["errors"] == {"name": "name_required"}


async def test_midnight_tick_without_change(hass, freezer):
    """Recompute at midnight with one-offs present must not fail (regression guard)."""
    await _plant(hass)
    await _add(hass, name="Umtopfen", due="2026-12-24", yearly=True)
    freezer.tick(timedelta(days=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert _oneoffs(hass)["Umtopfen"]["days"] == 55


async def test_unknown_ids(hass):
    entry, sid = await _plant(hass)
    manager = entry.runtime_data
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "rootine",
            "update_oneoff",
            {"entity_id": CARE, "oneoff_id": "once_missing", "name": "x"},
            blocking=True,
        )
    assert not manager.complete_oneoff(sid, "once_missing", "service")
    assert not manager.postpone_oneoff(sid, "once_missing", 2)


async def test_undo_twice_and_undo_after_a_later_change(hass):
    entry, sid = await _plant(hass)
    manager = entry.runtime_data
    oid = await _add(hass, name="Umtopfen", due="2026-10-29", yearly=True)
    manager.complete_oneoff(sid, oid, "service")
    event_id = next(h["id"] for h in manager.history(sid) if h["task"] == oid)
    # the user moved next year's date by hand: undoing the old completion keeps it
    manager.update_oneoff(sid, oid, due=manager.plants[sid].oneoff(oid).due.replace(month=11))
    assert manager.undo_event(sid, event_id)
    assert _oneoffs(hass)["Umtopfen"]["due"] == "2027-11-29"
    assert manager.undo_event(sid, event_id)  # already undone: nothing changes
    assert _oneoffs(hass)["Umtopfen"]["due"] == "2027-11-29"


async def test_diagnostics_list_one_offs(hass):
    from custom_components.rootine.diagnostics import async_get_config_entry_diagnostics

    entry, sid = await _plant(hass)
    oid = await _add(hass, name="Umtopfen", due="2026-11-20")
    data = await async_get_config_entry_diagnostics(hass, entry)
    assert [o["id"] for o in data["plants"][sid]["oneoffs"]] == [oid]
