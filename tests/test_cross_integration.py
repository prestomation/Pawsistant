"""Cross-integration test: Pawsistant <-> Home Keeper, two-way completion sync.

This is a real-HA test (it must run before the mock-based unit tier contaminates
sys.modules). It uses Home Keeper's published test fake
(``home_keeper.testing.async_setup_fake_home_keeper``) so we exercise the genuine
contract — the real service names and the real ``home_keeper_task_completed`` event
— without standing up Home Keeper's own UI/storage.

Home Keeper is a git test dependency (see requirements-test.txt); if it isn't
installed the test skips rather than fails, so the rest of the suite still runs.
"""

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.real_ha

# Skip cleanly when the Home Keeper test dependency isn't installed.
testing = pytest.importorskip("home_keeper.testing")

from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

from custom_components.pawsistant import care_link  # noqa: E402
from custom_components.pawsistant.const import DOMAIN  # noqa: E402

# The undo half of the contract needs a Home Keeper that fires the removed completion's
# ``ts`` on home_keeper_task_uncompleted, and whose fake can drive that path. Skip
# rather than fail against an older one, matching how this module treats Home Keeper
# missing entirely.
requires_hk_undo = pytest.mark.skipif(
    not hasattr(testing.FakeHomeKeeper, "fire_user_uncompletion"),
    reason="installed Home Keeper predates the task_uncompleted ts/origin contract",
)


def _add_home_keeper_entry(hass) -> None:
    """Give the fake a config entry, which is how care_link detects Home Keeper.

    ``home_keeper_available`` asks the config-entry registry, not the service registry,
    so anything going through it (``reconcile``) needs this even though the fake
    registers the services itself.
    """
    MockConfigEntry(domain=care_link.HK_DOMAIN).add_to_hass(hass)


async def _setup_pawsistant(hass) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"initial_dog": {"name": "Buddy"}},
    )
    entry.add_to_hass(hass)
    # Pawsistant's manifest depends on `frontend` (for its Lovelace card), which needs
    # the compiled `hass_frontend` package that isn't installed in the test env. We
    # don't exercise the card here, so mark http/frontend as already set up and stub
    # the card registration so setup focuses on the store/coordinator/services.
    hass.config.components.add("http")
    hass.config.components.add("frontend")
    with patch(
        "custom_components.pawsistant._ensure_frontend_registered", new=AsyncMock()
    ):
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


async def _make_linked_schedule(hass, store, dog_id, schedule_id="sched-1"):
    """Create a medicine care schedule and its linked Home Keeper task."""
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
    return task_id


@requires_hk_undo
@pytest.mark.asyncio
async def test_undo_in_home_keeper_removes_the_mirrored_event(
    hass, enable_custom_integrations
):
    """The reported bug: undo a completion in HK, the pet-care entry should go too."""
    hk = await testing.async_setup_fake_home_keeper(hass)
    entry = await _setup_pawsistant(hass)
    store = entry.runtime_data.store
    dog_id = next(iter(store.get_dogs()))
    task_id = await _make_linked_schedule(hass, store, dog_id)

    # A user checks the task off in Home Keeper; we mirror it in.
    hk.fire_user_completion(task_id)
    await hass.async_block_till_done()
    assert await _medicine_count(store, dog_id) == 1

    # They undo it — the mirrored entry goes with the completion.
    ts = hk.tasks[task_id]["completions"][-1]["ts"]
    hk.fire_user_uncompletion(task_id, ts)
    await hass.async_block_till_done()
    assert await _medicine_count(store, dog_id) == 0


@requires_hk_undo
@pytest.mark.asyncio
async def test_deleting_a_logged_event_undoes_the_completion(
    hass, enable_custom_integrations
):
    """The reverse direction: delete the entry on our side, the completion goes."""
    hk = await testing.async_setup_fake_home_keeper(hass)
    entry = await _setup_pawsistant(hass)
    store = entry.runtime_data.store
    dog_id = next(iter(store.get_dogs()))
    task_id = await _make_linked_schedule(hass, store, dog_id)

    await hass.services.async_call(
        DOMAIN, "log_event", {"dog": "Buddy", "event_type": "medicine"}, blocking=True
    )
    await hass.async_block_till_done()
    events = await store.get_events(dog_id, "medicine")
    assert len(events) == 1
    assert len(hk.tasks[task_id]["completions"]) == 1

    await hass.services.async_call(
        DOMAIN, "delete_event", {"event_id": events[0]["id"]}, blocking=True
    )
    await hass.async_block_till_done()

    assert hk.tasks[task_id]["completions"] == []
    assert hk.tasks[task_id]["last_completed"] is None
    # The resulting uncompleted event carried our origin, so it did not echo back and
    # try to delete anything a second time.
    assert await _medicine_count(store, dog_id) == 0


@requires_hk_undo
@pytest.mark.asyncio
async def test_editing_an_events_time_moves_the_completion(
    hass, enable_custom_integrations
):
    """Re-timing an entry re-times the completion, and leaves exactly one behind."""
    hk = await testing.async_setup_fake_home_keeper(hass)
    entry = await _setup_pawsistant(hass)
    store = entry.runtime_data.store
    dog_id = next(iter(store.get_dogs()))
    task_id = await _make_linked_schedule(hass, store, dog_id)

    await hass.services.async_call(
        DOMAIN, "log_event", {"dog": "Buddy", "event_type": "medicine"}, blocking=True
    )
    await hass.async_block_till_done()
    event = (await store.get_events(dog_id, "medicine"))[0]
    original_ts = hk.tasks[task_id]["completions"][-1]["ts"]

    corrected = "2026-06-14T08:30:00+00:00"
    await hass.services.async_call(
        DOMAIN,
        "update_event",
        {"event_id": event["id"], "timestamp": corrected},
        blocking=True,
    )
    await hass.async_block_till_done()

    completions = hk.tasks[task_id]["completions"]
    assert len(completions) == 1, "the old completion was replaced, not duplicated"
    assert completions[0]["ts"] != original_ts
    # The pair of events this fires carried our origin, so nothing echoed back into a
    # second logged entry or deleted the one we just edited.
    assert await _medicine_count(store, dog_id) == 1


@requires_hk_undo
@pytest.mark.asyncio
async def test_undo_of_a_foreign_task_leaves_our_log_alone(
    hass, enable_custom_integrations
):
    """An undo on someone else's task must not delete a pet-care entry."""
    hk = await testing.async_setup_fake_home_keeper(hass)
    entry = await _setup_pawsistant(hass)
    store = entry.runtime_data.store
    dog_id = next(iter(store.get_dogs()))
    await _make_linked_schedule(hass, store, dog_id)

    await hass.services.async_call(
        DOMAIN, "log_event", {"dog": "Buddy", "event_type": "medicine"}, blocking=True
    )
    await hass.async_block_till_done()
    before = await _medicine_count(store, dog_id)

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
    hk.fire_user_completion(other["id"])
    await hass.async_block_till_done()
    hk.fire_user_uncompletion(other["id"], hk.tasks[other["id"]]["completions"][-1]["ts"])
    await hass.async_block_till_done()

    assert await _medicine_count(store, dog_id) == before


@pytest.mark.asyncio
async def test_reconcile_heals_an_orphaned_mirror(hass, enable_custom_integrations):
    """An undo that happened while we were down is repaired at startup.

    This is what fixes an install that already diverged, before the event listener
    existed at all.
    """
    hk = await testing.async_setup_fake_home_keeper(hass)
    _add_home_keeper_entry(hass)
    entry = await _setup_pawsistant(hass)
    store = entry.runtime_data.store
    dog_id = next(iter(store.get_dogs()))
    task_id = await _make_linked_schedule(hass, store, dog_id)

    # A mirrored entry whose completion no longer exists in Home Keeper, plus an entry
    # the user logged by hand that must survive.
    await store.add_event(
        dog_id=dog_id, event_type="medicine", note=care_link.MIRROR_NOTE
    )
    await store.add_event(dog_id=dog_id, event_type="medicine", note="gave it by hand")
    assert hk.tasks[task_id]["completions"] == []
    assert await _medicine_count(store, dog_id) == 2

    await care_link.reconcile(hass, store)
    await hass.async_block_till_done()

    remaining = await store.get_events(dog_id, "medicine")
    assert [e["note"] for e in remaining] == ["gave it by hand"]


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


# ── supplies ─────────────────────────────────────────────────────────────────
#
# An event type can use a supply that Home Keeper counts. These need a Home Keeper
# whose adjust_part_stock reports what it applied and whose completion undo gives
# stock back, and a fake that does the same.

requires_hk_supplies = pytest.mark.skipif(
    not hasattr(testing.FakeHomeKeeper, "_return_stock_drawn"),
    reason="installed Home Keeper predates the stock report and the stock undo",
)


def _our_part(hk, name):
    from custom_components.pawsistant import supplies

    asset = supplies.find_appliance(list(hk.assets.values()))
    assert asset is not None, "the Pet supplies appliance was not created"
    part = supplies.find_part_by_name(asset, name)
    assert part is not None, f"no part called {name}"
    return asset, part


async def _add_roll_type(hass):
    await hass.services.async_call(
        DOMAIN,
        "add_event_type",
        {
            "event_type": "roll",
            "name": "Roll",
            "icon": "mdi:paper-roll",
            "color": "#8D6E63",
            "supply": {"name": "Poop bag rolls", "amount": 1},
        },
        blocking=True,
    )
    await hass.services.async_call(
        DOMAIN,
        "update_supply",
        {"event_type": "roll", "stock": 3, "reorder_at": 1, "pack_size": 8, "unit": "roll"},
        blocking=True,
    )
    await hass.async_block_till_done()


@requires_hk_supplies
@pytest.mark.asyncio
async def test_a_supply_makes_a_managed_part(hass, enable_custom_integrations):
    hk = await testing.async_setup_fake_home_keeper(hass)
    _add_home_keeper_entry(hass)
    entry = await _setup_pawsistant(hass)
    await _add_roll_type(hass)

    asset, part = _our_part(hk, "Poop bag rolls")
    assert asset["name"] == "Pet supplies"
    assert asset["managed_by"]["integration"] == "pawsistant"
    assert asset["managed_by"]["locked_fields"] == ["name", "parts"]
    assert part["notes"] == "Used by Roll"
    # The user's numbers went on the part, and a reorder point turned on the Buy task.
    assert (part["stock"], part["reorder_at"], part["restock_quantity"]) == (3, 1, 8)
    assert part["stock_unit"] == "roll"
    assert part["create_buy_task"] is True
    stored = entry.runtime_data.store.get_event_types()["roll"]["supply"]
    assert stored == {
        "asset_id": asset["id"],
        "part_id": part["id"],
        "name": "Poop bag rolls",
        "amount": 1.0,
    }


@requires_hk_supplies
@pytest.mark.asyncio
async def test_a_log_takes_its_supply_and_a_delete_gives_it_back(
    hass, enable_custom_integrations
):
    hk = await testing.async_setup_fake_home_keeper(hass)
    _add_home_keeper_entry(hass)
    entry = await _setup_pawsistant(hass)
    store = entry.runtime_data.store
    dog_id = next(iter(store.get_dogs()))
    await _add_roll_type(hass)
    _, part = _our_part(hk, "Poop bag rolls")

    await hass.services.async_call(
        DOMAIN, "log_event", {"dog": "Buddy", "event_type": "roll"}, blocking=True
    )
    await hass.async_block_till_done()
    assert part["stock"] == 2
    [event] = await store.get_events(dog_id, "roll")
    assert event["supply_draw"]["applied_delta"] == -1

    # A poop log does not touch the rolls.
    await hass.services.async_call(
        DOMAIN, "log_event", {"dog": "Buddy", "event_type": "poop"}, blocking=True
    )
    assert part["stock"] == 2

    await hass.services.async_call(
        DOMAIN, "delete_event", {"event_id": event["id"]}, blocking=True
    )
    await hass.async_block_till_done()
    assert part["stock"] == 3


@requires_hk_supplies
@pytest.mark.asyncio
async def test_an_empty_supply_gives_back_only_what_it_gave(
    hass, enable_custom_integrations
):
    hk = await testing.async_setup_fake_home_keeper(hass)
    _add_home_keeper_entry(hass)
    entry = await _setup_pawsistant(hass)
    store = entry.runtime_data.store
    dog_id = next(iter(store.get_dogs()))
    await _add_roll_type(hass)
    await hass.services.async_call(
        DOMAIN, "update_supply", {"event_type": "roll", "stock": 0}, blocking=True
    )
    _, part = _our_part(hk, "Poop bag rolls")

    await hass.services.async_call(
        DOMAIN, "log_event", {"dog": "Buddy", "event_type": "roll"}, blocking=True
    )
    [event] = await store.get_events(dog_id, "roll")
    assert event["supply_draw"]["applied_delta"] == 0
    await hass.services.async_call(
        DOMAIN, "delete_event", {"event_id": event["id"]}, blocking=True
    )
    assert part["stock"] == 0, "a delete must not make up a roll that never left"


@requires_hk_supplies
@pytest.mark.asyncio
async def test_a_scheduled_dose_is_drawn_once_from_either_side(
    hass, enable_custom_integrations
):
    from custom_components.pawsistant import supply_link

    hk = await testing.async_setup_fake_home_keeper(hass)
    _add_home_keeper_entry(hass)
    entry = await _setup_pawsistant(hass)
    store = entry.runtime_data.store
    dog_id = next(iter(store.get_dogs()))
    task_id = await _make_linked_schedule(hass, store, dog_id)

    await hass.services.async_call(
        DOMAIN,
        "update_event_type",
        {"event_type": "medicine", "supply": {"name": "Carprofen 75 mg", "amount": 1}},
        blocking=True,
    )
    await hass.services.async_call(
        DOMAIN, "update_supply", {"event_type": "medicine", "stock": 9}, blocking=True
    )
    await hass.async_block_till_done()
    asset, part = _our_part(hk, "Carprofen 75 mg")
    assert hk.tasks[task_id]["source"]["part"]["part_id"] == part["id"]
    assert hk.tasks[task_id]["source"]["part"]["quantity"] == 1

    # Logged here: Home Keeper draws it through the task, and we draw nothing.
    await hass.services.async_call(
        DOMAIN, "log_event", {"dog": "Buddy", "event_type": "medicine"}, blocking=True
    )
    await hass.async_block_till_done()
    assert part["stock"] == 8
    [logged] = await store.get_events(dog_id, "medicine")
    assert "supply_draw" not in logged

    # Ticked in Home Keeper: one more dose, and the mirror draws nothing extra.
    hk.fire_user_completion(task_id)
    await hass.async_block_till_done()
    assert part["stock"] == 7

    # Deleting the dose logged here undoes its completion, which gives the tablet back.
    await hass.services.async_call(
        DOMAIN, "delete_event", {"event_id": logged["id"]}, blocking=True
    )
    await hass.async_block_till_done()
    assert part["stock"] == 8

    # A second sync changes nothing.
    await supply_link.sync_links(hass, store)
    assert hk.tasks[task_id]["source"]["part"]["asset_id"] == asset["id"]


@requires_hk_supplies
@pytest.mark.asyncio
async def test_clearing_a_supply_unlinks_the_task_and_drops_an_uncounted_part(
    hass, enable_custom_integrations
):
    hk = await testing.async_setup_fake_home_keeper(hass)
    _add_home_keeper_entry(hass)
    entry = await _setup_pawsistant(hass)
    store = entry.runtime_data.store
    dog_id = next(iter(store.get_dogs()))
    task_id = await _make_linked_schedule(hass, store, dog_id)
    await hass.services.async_call(
        DOMAIN,
        "update_event_type",
        {"event_type": "medicine", "supply": {"name": "Carprofen 75 mg"}},
        blocking=True,
    )
    assert "part" in hk.tasks[task_id]["source"]

    await hass.services.async_call(
        DOMAIN, "update_event_type", {"event_type": "medicine", "supply": None},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert "part" not in hk.tasks[task_id]["source"]
    assert "pawsistant" in hk.tasks[task_id]["source"], "our own namespace stays"
    assert "supply" not in store.get_event_types()["medicine"]
    from custom_components.pawsistant import supplies

    asset = supplies.find_appliance(list(hk.assets.values()))
    assert asset["parts"] == [], "a part nobody counted leaves with its last user"


@requires_hk_supplies
@pytest.mark.asyncio
async def test_update_supply_needs_a_supply(hass, enable_custom_integrations):
    from homeassistant.exceptions import ServiceValidationError

    await testing.async_setup_fake_home_keeper(hass)
    _add_home_keeper_entry(hass)
    await _setup_pawsistant(hass)
    with pytest.raises(ServiceValidationError, match="does not use a supply"):
        await hass.services.async_call(
            DOMAIN, "update_supply", {"event_type": "poop", "stock": 2}, blocking=True
        )


@pytest.mark.asyncio
async def test_a_supply_without_home_keeper_is_refused(hass, enable_custom_integrations):
    from homeassistant.exceptions import ServiceValidationError

    await _setup_pawsistant(hass)
    with pytest.raises(ServiceValidationError, match="needs Home Keeper"):
        await hass.services.async_call(
            DOMAIN,
            "update_event_type",
            {"event_type": "poop", "supply": {"name": "Rolls"}},
            blocking=True,
        )


@requires_hk_supplies
@pytest.mark.asyncio
async def test_draw_ignores_a_supply_with_no_part(hass, enable_custom_integrations):
    from custom_components.pawsistant import supply_link

    await testing.async_setup_fake_home_keeper(hass)
    assert await supply_link.draw(hass, {"amount": 1}, 1) is None
    assert await supply_link.draw(hass, {"asset_id": "a1", "part_id": ""}, 1) is None
