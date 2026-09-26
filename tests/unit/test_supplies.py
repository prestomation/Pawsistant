"""The pure rules behind supplies: what an event type's supply means in Home Keeper.

``supplies.py`` has no Home Assistant imports, so it loads alone from its file and
these tests need no stubs.
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

_PATH = (
    pathlib.Path(__file__).parent.parent.parent
    / "custom_components"
    / "pawsistant"
    / "supplies.py"
)
_spec = importlib.util.spec_from_file_location("pawsistant_supplies", _PATH)
supplies = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(supplies)


def _appliance(parts=None):
    return {
        "id": "a1",
        "name": supplies.APPLIANCE_NAME,
        "source": {"pawsistant": {"role": "supplies"}},
        "parts": parts or [],
    }


def _supply(part_id="p1", amount=1, name="Poop bag rolls"):
    return {"asset_id": "a1", "part_id": part_id, "name": name, "amount": amount}


# ── normalize_supply_input ────────────────────────────────────────────────────


def test_a_supply_is_a_name_and_an_amount():
    assert supplies.normalize_supply_input({"name": " Rolls ", "amount": 0.5}) == {
        "name": "Rolls",
        "amount": 0.5,
    }


def test_the_amount_defaults_to_one():
    assert supplies.normalize_supply_input({"name": "Rolls"})["amount"] == 1.0


def test_none_clears_the_supply():
    assert supplies.normalize_supply_input(None) is None


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("Rolls", "supply must be a mapping with a name and an amount"),
        ({"amount": 1}, "supply needs a name"),
        ({"name": "  "}, "supply needs a name"),
        ({"name": "x" * 61}, "supply name must be at most 60 characters"),
        ({"name": "Rolls", "amount": "lots"}, "supply amount must be a number"),
        ({"name": "Rolls", "amount": 0}, "supply amount must be greater than zero"),
        ({"name": "Rolls", "amount": -1}, "supply amount must be greater than zero"),
        (
            {"name": "Rolls", "amount": float("nan")},
            "supply amount must be greater than zero",
        ),
    ],
)
def test_a_bad_supply_is_refused(raw, message):
    with pytest.raises(supplies.SupplyError) as err:
        supplies.normalize_supply_input(raw)
    assert str(err.value) == message


def test_a_name_of_sixty_characters_is_allowed():
    assert supplies.normalize_supply_input({"name": "x" * 60})["name"] == "x" * 60


# ── reading a stored supply ───────────────────────────────────────────────────


def test_event_type_supply_needs_both_ids():
    assert supplies.event_type_supply({"supply": _supply()}) == _supply()
    assert supplies.event_type_supply({"supply": {"part_id": "p1"}}) is None
    assert supplies.event_type_supply({"supply": {"asset_id": "a1"}}) is None
    assert supplies.event_type_supply({"supply": "Rolls"}) is None
    assert supplies.event_type_supply({}) is None
    assert supplies.event_type_supply(None) is None


def test_our_appliance_is_found_by_its_source_role():
    other = {"id": "b", "source": {"battery_notes": {"role": "battery_stock"}}}
    wrong_role = {"id": "c", "source": {"pawsistant": {"role": "other"}}}
    plain = {"id": "d", "source": None}
    assert supplies.find_appliance([other, wrong_role, plain, _appliance()])["id"] == "a1"
    assert supplies.find_appliance([other, wrong_role, plain]) is None


def test_a_part_is_found_by_name_ignoring_case():
    asset = _appliance([{"id": "p1", "name": "Poop bag rolls"}])
    assert supplies.find_part_by_name(asset, " poop BAG rolls ")["id"] == "p1"
    assert supplies.find_part_by_name(asset, "Carprofen") is None
    assert supplies.find_part_by_id(asset, "p1")["name"] == "Poop bag rolls"
    assert supplies.find_part_by_id(asset, "p2") is None


# ── the appliance ─────────────────────────────────────────────────────────────


def test_the_appliance_is_virtual_and_locked():
    payload = supplies.appliance_payload("entry1")
    assert payload["name"] == "Pet supplies"
    assert payload["kind"] == "virtual"
    assert payload["source"] == {"pawsistant": {"role": "supplies"}}
    assert payload["managed_by"] == {
        "integration": "pawsistant",
        "display_name": "Pawsistant",
        "icon": "mdi:paw",
        "locked_fields": ["name", "parts"],
        "config_entry_id": "entry1",
        "deletion_protected": True,
    }


def test_the_appliance_is_not_protected_without_an_entry():
    managed_by = supplies.appliance_payload(None)["managed_by"]
    assert "config_entry_id" not in managed_by
    assert "deletion_protected" not in managed_by


def test_usage_note():
    assert supplies.usage_note(["Roll", "carprofen"]) == "Used by carprofen, Roll"
    assert supplies.usage_note([]) == "Not used by any Pawsistant event type"


def test_desired_parts_has_one_part_per_supply_name():
    types = {
        "roll": {"name": "Roll", "supply": _supply()},
        "poop": {"name": "Poop"},
        "walk_roll": {"name": "Walk", "supply": _supply(name="poop bag rolls")},
        "carprofen": {"name": "Carprofen", "supply": _supply("p2", name="Carprofen")},
    }
    asset = _appliance([{"id": "p1", "name": "Poop bag rolls", "type": "consumable"}])
    parts = supplies.desired_parts(asset, types)
    assert parts == [
        {
            "name": "Carprofen",
            "type": "consumable",
            "notes": "Used by Carprofen",
        },
        {
            "id": "p1",
            "name": "Poop bag rolls",
            "type": "consumable",
            "notes": "Used by Roll, Walk",
        },
    ]


def test_desired_parts_adds_the_new_supply_and_drops_an_unused_one():
    asset = _appliance([{"id": "old", "name": "Kibble"}])
    parts = supplies.desired_parts(asset, {}, extra=" Rolls ")
    assert parts == [
        {
            "name": "Rolls",
            "type": "consumable",
            "notes": "Not used by any Pawsistant event type",
        }
    ]


def test_parts_differ():
    stored = [{"id": "p1", "name": "Rolls", "type": "consumable", "notes": "Used by Roll"}]
    asset = _appliance(stored)
    same = [dict(stored[0])]
    assert supplies.parts_differ(asset, same) is False
    assert supplies.parts_differ(asset, [{**stored[0], "notes": "x"}]) is True
    assert supplies.parts_differ(asset, [{**stored[0], "name": "Bags"}]) is True
    assert supplies.parts_differ(asset, [{**stored[0], "type": "wear"}]) is True
    assert supplies.parts_differ(asset, [{"name": "Rolls"}]) is True
    assert supplies.parts_differ(asset, [{**stored[0], "id": "p9"}]) is True
    assert supplies.parts_differ(asset, []) is True


def test_user_keys_update_sends_every_user_key():
    part = {
        "id": "p1",
        "name": "Rolls",
        "type": "consumable",
        "stock": 3,
        "reorder_at": None,
        "stock_unit": "roll",
        "consume_quantity": None,
        "create_buy_task": False,
        "restock_quantity": 8,
        "notes": "owner text",
    }
    assert supplies.user_keys_update(part, {"stock": 5, "vendor": "x"}) == {
        "id": "p1",
        "name": "Rolls",
        "type": "consumable",
        "stock": 5,
        "reorder_at": None,
        "stock_unit": "roll",
        "consume_quantity": None,
        "create_buy_task": False,
        "restock_quantity": 8,
    }


def test_a_reorder_point_turns_on_the_buy_task():
    part = {"id": "p1", "name": "Rolls", "create_buy_task": False}
    assert supplies.user_keys_update(part, {"reorder_at": 1})["create_buy_task"] is True
    assert supplies.user_keys_update(part, {"reorder_at": None})["create_buy_task"] is False


def test_stock_unique_id_matches_home_keeper():
    assert (
        supplies.stock_unique_id("a1", "p1") == "home_keeper_asset_a1_part_p1_stock"
    )


# ── linking care tasks ────────────────────────────────────────────────────────


def _task(task_id="t1", link=None):
    source = {"pawsistant": {"schedule_id": "s1"}}
    if link is not None:
        source["part"] = link
    return {"id": task_id, "source": source}


def _schedules():
    return {"s1": {"dog_id": "d1", "event_type": "carprofen", "task_id": "t1"}}


def test_a_care_task_is_linked_to_its_supply():
    types = {"carprofen": {"name": "Carprofen", "supply": _supply("p2", 0.5)}}
    calls = supplies.plan_links(_schedules(), types, {"t1": _task()})
    assert calls == [
        {"task_id": "t1", "asset_id": "a1", "part_id": "p2", "quantity": 0.5}
    ]


def test_a_matching_link_needs_no_call():
    types = {"carprofen": {"name": "Carprofen", "supply": _supply("p2", 0.5)}}
    link = {"asset_id": "a1", "part_id": "p2", "manual": True, "quantity": 0.5}
    assert supplies.plan_links(_schedules(), types, {"t1": _task(link=link)}) == []


@pytest.mark.parametrize(
    "link",
    [
        {"asset_id": "a1", "part_id": "p2", "quantity": 1},
        {"asset_id": "a1", "part_id": "p3", "quantity": 0.5},
        {"asset_id": "a9", "part_id": "p2", "quantity": 0.5},
        {"asset_id": "a1", "part_id": "p2"},
    ],
)
def test_a_different_link_is_replaced(link):
    types = {"carprofen": {"name": "Carprofen", "supply": _supply("p2", 0.5)}}
    calls = supplies.plan_links(_schedules(), types, {"t1": _task(link=link)})
    assert calls == [
        {"task_id": "t1", "asset_id": "a1", "part_id": "p2", "quantity": 0.5}
    ]


def test_a_task_without_a_supply_loses_its_link():
    types = {"carprofen": {"name": "Carprofen"}}
    link = {"asset_id": "a1", "part_id": "p2", "quantity": 1}
    calls = supplies.plan_links(_schedules(), types, {"t1": _task(link=link)})
    assert calls == [{"task_id": "t1", "asset_id": None, "part_id": None}]
    assert supplies.plan_links(_schedules(), types, {"t1": _task()}) == []


def test_a_schedule_whose_task_is_gone_is_skipped():
    types = {"carprofen": {"name": "Carprofen", "supply": _supply()}}
    assert supplies.plan_links(_schedules(), types, {}) == []


def test_link_quantity_reads_the_part_link():
    link = {"asset_id": "a1", "part_id": "p2", "quantity": 2}
    assert supplies.link_quantity(_task(link=link)) == ("a1", "p2", 2)
    assert supplies.link_quantity(_task()) == (None, None, None)


# ── what the card reads ───────────────────────────────────────────────────────


def test_the_card_gets_the_spares_entity_of_each_supply():
    types = {"roll": {"name": "Roll", "supply": _supply()}, "poop": {"name": "Poop"}}
    out = supplies.with_stock_entities(
        types, lambda a, p: f"number.{a}_{p}_spares"
    )
    assert out["roll"]["supply"]["entity_id"] == "number.a1_p1_spares"
    assert out["poop"] == {"name": "Poop"}
    # The stored registry is not changed: the entity id is derived, not stored.
    assert "entity_id" not in types["roll"]["supply"]
