"""Home Assistant tests for the options flow, driven through the real flow manager.

``tests/unit/test_options_flow.py`` calls each step method directly with a dict
that the test writes. That misses bugs where the dict that the form really sends
back has a different shape. These tests go through
``hass.config_entries.options`` so Home Assistant builds and validates each step,
as it does for a user in the UI.

Some tests are parity tests: they do one job by the service and by the options
flow, and check that the end state is the same. The two code paths must not
drift apart.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.real_ha

from homeassistant.data_entry_flow import FlowResultType  # noqa: E402
from homeassistant.helpers import entity_registry as er  # noqa: E402
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

from custom_components.pawsistant.const import DOMAIN  # noqa: E402

FRONTEND = "custom_components.pawsistant._ensure_frontend_registered"
DELETE_TASK = "custom_components.pawsistant.care_link.delete_task"


@pytest.fixture(autouse=True)
def _no_frontend():
    # The card needs the compiled frontend, which the test env does not have.
    # Reloads (add_dog) set up the entry again, so keep the patch for the whole test.
    with patch(FRONTEND, new=AsyncMock()):
        yield


async def _setup(hass) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data={"initial_dog": {"name": "Buddy"}})
    entry.add_to_hass(hass)
    hass.config.components.add("http")
    hass.config.components.add("frontend")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _flow(hass, entry: MockConfigEntry, *steps: dict) -> dict:
    """Start the options flow and submit each dict in turn; return the last result."""
    result = await hass.config_entries.options.async_init(entry.entry_id)
    for user_input in steps:
        assert result["type"] == FlowResultType.FORM, result
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], user_input
        )
    await hass.async_block_till_done()
    return result


def _buddy_id(entry: MockConfigEntry) -> str:
    result = entry.runtime_data.store.get_dog_by_name("Buddy")
    assert result is not None
    return result[0]


def _entities_for(hass, entry: MockConfigEntry, dog_id: str) -> list[str]:
    ent_reg = er.async_get(hass)
    return [
        e.entity_id
        for e in er.async_entries_for_config_entry(ent_reg, entry.entry_id)
        if e.unique_id.startswith(f"pawsistant_{dog_id}_")
    ]


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------


async def _edit_walk_by_flow(hass, entry) -> None:
    result = await _flow(
        hass,
        entry,
        {"action": "edit_event_types"},
        {"action": "edit_walk"},
        {
            "event_type_key": "walk",
            "name": "Stroll",
            "icon": "mdi:walk",
            "color": "#123456",
            "metric": "days_since",
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY, result


async def _edit_walk_by_service(hass, entry) -> None:
    await hass.services.async_call(
        DOMAIN,
        "update_event_type",
        {
            "event_type": "walk",
            "name": "Stroll",
            "icon": "mdi:walk",
            "color": "#123456",
            "metric": "days_since",
        },
        blocking=True,
    )
    await hass.async_block_till_done()


@pytest.mark.asyncio
@pytest.mark.parametrize("edit", [_edit_walk_by_flow, _edit_walk_by_service])
async def test_edit_event_type_changes_same_key(hass, enable_custom_integrations, edit):
    entry = await _setup(hass)
    store = entry.runtime_data.store
    keys_before = set(store.get_event_types())

    await edit(hass, entry)

    assert set(store.get_event_types()) == keys_before
    walk = store.get_event_types()["walk"]
    assert walk["name"] == "Stroll"
    assert walk["color"].upper() == "#123456"
    assert store.get_button_metrics()["walk"] == "days_since"


@pytest.mark.asyncio
async def test_edit_form_shows_current_values(hass, enable_custom_integrations):
    entry = await _setup(hass)
    result = await _flow(
        hass, entry, {"action": "edit_event_types"}, {"action": "edit_walk"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "edit_event_type"
    assert not result["errors"]


@pytest.mark.asyncio
async def test_add_event_type_by_flow(hass, enable_custom_integrations):
    entry = await _setup(hass)
    store = entry.runtime_data.store

    result = await _flow(
        hass,
        entry,
        {"action": "edit_event_types"},
        {"action": "add"},
        {"name": "Brush", "icon": "mdi:brush", "color": "#336699", "metric": "daily_count"},
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY, result
    assert store.get_event_types()["brush"]["name"] == "Brush"


@pytest.mark.asyncio
async def test_add_event_type_form_starts_empty(hass, enable_custom_integrations):
    entry = await _setup(hass)
    result = await _flow(hass, entry, {"action": "edit_event_types"}, {"action": "add"})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "add_event_type"
    assert not result["errors"]


# ---------------------------------------------------------------------------
# Removing a pet
# ---------------------------------------------------------------------------


async def _remove_by_flow(hass, entry) -> None:
    result = await _flow(
        hass, entry, {"action": "remove_dog"}, {"dog_name": "Buddy"}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY, result


async def _remove_by_service(hass, entry) -> None:
    await hass.services.async_call(DOMAIN, "remove_dog", {"dog": "Buddy"}, blocking=True)
    await hass.async_block_till_done()


@pytest.mark.asyncio
@pytest.mark.parametrize("remove", [_remove_by_flow, _remove_by_service])
async def test_remove_pet_cleans_up(hass, enable_custom_integrations, remove):
    entry = await _setup(hass)
    store = entry.runtime_data.store
    dog_id = _buddy_id(entry)
    await store.add_care_schedule(
        "sched-1",
        {
            "dog_id": dog_id,
            "event_type": "medicine",
            "recurrence_type": "floating",
            "interval": 1,
            "unit": "weeks",
            "task_id": "task-1",
        },
    )
    assert _entities_for(hass, entry, dog_id)

    with patch(DELETE_TASK, new=AsyncMock()) as delete_task:
        await remove(hass, entry)

    assert store.get_dog_by_name("Buddy") is None
    assert _entities_for(hass, entry, dog_id) == []
    assert store.get_care_schedules() == {}
    delete_task.assert_awaited_once()
    assert delete_task.await_args.args[1] == "task-1"
