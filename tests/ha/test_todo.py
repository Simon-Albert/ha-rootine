"""To-do list "Pflanzenpflege": items, completing, invalid items (item A5)."""

from __future__ import annotations

from datetime import date

import pytest
from homeassistant.components.todo import DOMAIN as TODO_DOMAIN
from homeassistant.components.todo import TodoItem, TodoItemStatus
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import async_get_platforms

from custom_components.rootine.const import DOMAIN

from .conftest import add_plant, setup_main

TODO = "todo.rootine_plant_care"


@pytest.fixture(autouse=True)
async def tz(hass, freezer):
    await hass.config.async_set_time_zone("Europe/Berlin")
    freezer.move_to("2026-10-29 12:00:00+01:00")


async def _items(hass):
    response = await hass.services.async_call(
        TODO_DOMAIN, "get_items", {"entity_id": TODO}, blocking=True, return_response=True
    )
    return response[TODO]["items"]


def _entity(hass):
    return next(p.entities[TODO] for p in async_get_platforms(hass, DOMAIN) if TODO in p.entities)


async def test_empty_list_and_count(hass):
    entry = await setup_main(hass)
    await add_plant(hass, entry, "Kaffee", last_done="2026-10-29")
    assert await _items(hass) == []
    assert hass.states.get(TODO).state == "0"


async def test_due_and_overdue_tasks_with_date_and_care_text(hass):
    entry = await setup_main(hass)
    await add_plant(
        hass,
        entry,
        "Kaffee",
        water="ganzjährig: 3",
        fertilize="ganzjährig: 7",
        last_done="2026-10-22",
        profile={"care_watering": "Erde leicht feucht halten"},
    )
    items = {i["summary"]: i for i in await _items(hass)}
    assert set(items) == {"Kaffee gießen", "Kaffee düngen"}
    water = items["Kaffee gießen"]
    assert water["status"] == "needs_action"
    assert water["due"] == "2026-10-25"
    assert "Erde leicht feucht halten" in water["description"]
    assert hass.states.get(TODO).state == "2"


async def test_soon_is_not_on_the_list(hass):
    entry = await setup_main(hass)
    await add_plant(
        hass, entry, "Kaffee", water="ganzjährig: 3", fertilize="", last_done="2026-10-27"
    )
    assert await _items(hass) == []


async def test_setting_back_to_open_does_nothing(hass):
    entry = await setup_main(hass)
    sid = await add_plant(
        hass, entry, "Kaffee", water="ganzjährig: 3", fertilize="", last_done="2026-10-20"
    )
    item = (await _items(hass))[0]
    await hass.services.async_call(
        TODO_DOMAIN,
        "update_item",
        {"entity_id": TODO, "item": item["uid"], "status": "needs_action"},
        blocking=True,
    )
    assert entry.runtime_data.plants[sid].states["water"].last_done.date() == date(2026, 10, 20)
    assert len(await _items(hass)) == 1


async def test_completing_marks_done_and_removes_the_item(hass):
    entry = await setup_main(hass)
    sid = await add_plant(
        hass, entry, "Kaffee", water="ganzjährig: 3", fertilize="", last_done="2026-10-20"
    )
    item = (await _items(hass))[0]
    await hass.services.async_call(
        TODO_DOMAIN,
        "update_item",
        {"entity_id": TODO, "item": item["uid"], "status": "completed"},
        blocking=True,
    )
    state = entry.runtime_data.plants[sid].states["water"]
    assert state.last_done.date() == date(2026, 10, 29) and state.last_source == "todo"
    assert await _items(hass) == []


@pytest.mark.parametrize("uid", ["garbage", "unknownplant:water:2026-10-29", "{sid}:gone:x"])
async def test_invalid_items_are_rejected(hass, uid):
    entry = await setup_main(hass)
    sid = await add_plant(hass, entry, "Kaffee")
    entity = _entity(hass)
    with pytest.raises(ServiceValidationError) as err:
        await entity.async_update_todo_item(
            TodoItem(uid=uid.format(sid=sid), summary="x", status=TodoItemStatus.COMPLETED)
        )
    assert err.value.translation_key == "unknown_todo_item"
