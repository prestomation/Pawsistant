"""Cross-integration test: Pawsistant <-> Home Keeper, two-way completion sync.

This is a real-HA test (it must run before the mock-based unit tier contaminates
sys.modules). It uses Home Keeper's published test fake
(``home_keeper.testing.async_setup_fake_home_keeper``) so we exercise the genuine
contract — the real service names and the real ``home_keeper_task_completed`` event
— without standing up Home Keeper's own UI/storage.

Home Keeper is a git test dependency (see requirements-test.txt); if it isn't
installed the test skips rather than fails, so the rest of the suite still runs.
"""

import pytest

pytestmark = pytest.mark.real_ha

# Skip cleanly when the Home Keeper test dependency isn't installed.
testing = pytest.importorskip("home_keeper.testing")

from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

from custom_components.pawsistant import care_link  # noqa: E402
from custom_components.pawsistant.const import DOMAIN  # noqa: E402


async def _setup_pawsistant(hass) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"initial_dog": {"name": "Buddy"}},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _medicine_count(store, dog_id) -> int:
    return len(await store.get_events(dog_id, "medicine"))


@pytest.mark.asyncio
async def test_two_way_sync_with_home_keeper(hass, enable_custom_integrations):
    hk = await testing.async_setup_fake_home_keeper(hass)

    entry = await _setup_pawsistant(hass)
    store = entry.runtime_data.store
    dog_id = next(iter(store.get_dogs()))

    # Create a care schedule -> creates a Home Keeper task tagged with our source.
    schedule_id = "sched-1"
    schedule = {
        "dog_id": dog_id,
        "event_type": "medicine",
        "recurrence_type": "floating",
        "interval": 2,
        "unit": "weeks",
    }
    task_id = await care_link.create_task(hass, store, schedule_id, schedule)
    schedule["task_id"] = task_id
    await store.add_care_schedule(schedule_id, schedule)

    assert task_id is not None
    task = hk.get_task_by_source("pawsistant", schedule_id=schedule_id)
    assert task is not None and task["id"] == task_id
    assert task["last_completed"] is None

    # --- Direction A: logging the activity completes the linked HK task ---------
    await hass.services.async_call(
        DOMAIN, "log_event", {"dog": "Buddy", "event_type": "medicine"}, blocking=True
    )
    await hass.async_block_till_done()

    # The HK task advanced (it was completed)...
    assert hk.tasks[task_id]["last_completed"] is not None
    # ...and exactly ONE medicine event exists (the completion echo did NOT loop
    # back into a second logged event).
    assert await _medicine_count(store, dog_id) == 1

    # --- Direction B: completing in Home Keeper logs the activity --------------
    hk.fire_user_completion(task_id)  # origin=None, i.e. a user check-off in HK
    await hass.async_block_till_done()

    # Exactly one NEW medicine event was mirrored in (and it did NOT loop back to
    # re-complete the HK task — only a real second completion would).
    assert await _medicine_count(store, dog_id) == 2


@pytest.mark.asyncio
async def test_completion_for_unknown_source_is_ignored(hass, enable_custom_integrations):
    """A completion for a task that isn't ours must not create a pet event."""
    hk = await testing.async_setup_fake_home_keeper(hass)
    entry = await _setup_pawsistant(hass)
    store = entry.runtime_data.store
    dog_id = next(iter(store.get_dogs()))

    # A task contributed by some other integration (foreign source namespace).
    await hass.services.async_call(
        "home_keeper",
        "add_task",
        {
            "name": "Replace battery",
            "recurrence_type": "floating",
            "interval": 6,
            "unit": "months",
            "source": {"battery_notes": {"device": "x"}},
        },
        blocking=True,
    )
    other = hk.get_task_by_source("battery_notes", device="x")
    before = await _medicine_count(store, dog_id)

    hk.fire_user_completion(other["id"])
    await hass.async_block_till_done()

    assert await _medicine_count(store, dog_id) == before
