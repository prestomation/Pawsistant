"""Supplies: pure rules for stock that an event type uses.

An event type can **use a supply**. Each log of that type takes a set amount off a
count that Home Keeper keeps. Poop bag rolls and medicine tablets are two settings of
the same feature, so nothing here knows about bags or pills.

The count lives on a part of one virtual appliance, "Pet supplies", that Pawsistant
manages in Home Keeper. Pawsistant owns the appliance name and its list of parts. The
user owns every count, reorder point, unit and pack size.

This module has no Home Assistant imports so it can be unit tested alone. The calls
to Home Keeper live in :mod:`supply_link`.
"""

from __future__ import annotations

import math
from typing import Any

# The namespace we own under an appliance's opaque ``source``, and the role that marks
# the one appliance that holds our supplies.
SOURCE_NS = "pawsistant"
ROLE = "supplies"
APPLIANCE_NAME = "Pet supplies"
# Home Keeper locks these on our appliance: the name, and the list of parts.
LOCKED_FIELDS = ["name", "parts"]

MAX_SUPPLY_NAME_LEN = 60

# The part keys that belong to the user, not to us. Home Keeper's ``update_asset``
# writes all of them from what we send, so we always send every one.
PART_USER_KEYS = (
    "stock",
    "reorder_at",
    "stock_unit",
    "consume_quantity",
    "create_buy_task",
    "restock_quantity",
)


class SupplyError(ValueError):
    """A supply setting that cannot be stored."""


def normalize_supply_input(raw: Any) -> dict[str, Any] | None:
    """Check a ``supply`` from a service call. Return ``{name, amount}`` or None.

    ``None`` clears the supply. A supply names the thing (``"Poop bag rolls"``) and the
    amount one log takes. The amount can be a fraction, for half a tablet.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise SupplyError("supply must be a mapping with a name and an amount")
    name = str(raw.get("name") or "").strip()
    if not name:
        raise SupplyError("supply needs a name")
    if len(name) > MAX_SUPPLY_NAME_LEN:
        raise SupplyError(
            f"supply name must be at most {MAX_SUPPLY_NAME_LEN} characters"
        )
    try:
        amount = float(raw.get("amount", 1))
    except (TypeError, ValueError) as err:
        raise SupplyError("supply amount must be a number") from err
    if not math.isfinite(amount) or amount <= 0:
        raise SupplyError("supply amount must be greater than zero")
    return {"name": name, "amount": amount}


def event_type_supply(event_type: dict[str, Any] | None) -> dict[str, Any] | None:
    """The stored supply of an event type, or None when it has none we can use."""
    supply = (event_type or {}).get("supply")
    if not isinstance(supply, dict):
        return None
    if not supply.get("asset_id") or not supply.get("part_id"):
        return None
    return supply


def is_our_appliance(asset: dict[str, Any]) -> bool:
    """True for the appliance that holds our supplies."""
    source = asset.get("source")
    if not isinstance(source, dict):
        return False
    ours = source.get(SOURCE_NS)
    return isinstance(ours, dict) and ours.get("role") == ROLE


def find_appliance(assets: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Our supplies appliance among Home Keeper's appliances, or None."""
    return next((a for a in assets if is_our_appliance(a)), None)


def find_part_by_name(asset: dict[str, Any], name: str) -> dict[str, Any] | None:
    """The part called *name* on *asset*, ignoring case and outer spaces."""
    wanted = name.strip().casefold()
    return next(
        (
            p
            for p in asset.get("parts") or []
            if str(p.get("name") or "").strip().casefold() == wanted
        ),
        None,
    )


def find_part_by_id(asset: dict[str, Any], part_id: str) -> dict[str, Any] | None:
    """The part with *part_id* on *asset*, or None."""
    return next((p for p in asset.get("parts") or [] if p.get("id") == part_id), None)


def appliance_payload(config_entry_id: str | None) -> dict[str, Any]:
    """The ``home_keeper.add_asset`` data that creates our supplies appliance."""
    managed_by: dict[str, Any] = {
        "integration": SOURCE_NS,
        "display_name": "Pawsistant",
        "icon": "mdi:paw",
        "locked_fields": list(LOCKED_FIELDS),
    }
    # Home Keeper honours deletion protection only with an entry id, which is how it
    # finds out that we went away.
    if config_entry_id:
        managed_by["config_entry_id"] = config_entry_id
        managed_by["deletion_protected"] = True
    return {
        "name": APPLIANCE_NAME,
        "kind": "virtual",
        "source": {SOURCE_NS: {"role": ROLE}},
        "managed_by": managed_by,
    }


def usage_note(type_names: list[str]) -> str:
    """The part's notes: which event types use it."""
    if not type_names:
        return "Not used by any Pawsistant event type"
    return "Used by " + ", ".join(sorted(type_names, key=str.casefold))


def desired_parts(
    asset: dict[str, Any], event_types: dict[str, dict[str, Any]], extra: str | None = None
) -> list[dict[str, Any]]:
    """The part list we send to ``home_keeper.update_managed_asset``.

    One consumable part for each supply name the event types use, plus *extra* when a
    new supply is being added. A stored part keeps its ``id``. A stored part that no
    event type uses is left out, and Home Keeper removes it only if nobody counts it.
    """
    users: dict[str, list[str]] = {}
    display: dict[str, str] = {}
    for meta in event_types.values():
        supply = (meta or {}).get("supply")
        if not isinstance(supply, dict) or not supply.get("name"):
            continue
        name = str(supply["name"]).strip()
        key = name.casefold()
        display.setdefault(key, name)
        users.setdefault(key, []).append(str(meta.get("name") or ""))
    if extra:
        key = extra.strip().casefold()
        display.setdefault(key, extra.strip())
        users.setdefault(key, [])
    parts: list[dict[str, Any]] = []
    for key in sorted(display):
        part: dict[str, Any] = {
            "name": display[key],
            "type": "consumable",
            "notes": usage_note([n for n in users[key] if n]),
        }
        stored = find_part_by_name(asset, display[key])
        if stored is not None:
            part["id"] = stored["id"]
            # The part keeps the name it was created with, so a change of case in an
            # event type does not rename a count the user already knows.
            part["name"] = stored.get("name") or part["name"]
        parts.append(part)
    return parts


def parts_differ(asset: dict[str, Any], parts: list[dict[str, Any]]) -> bool:
    """True when *parts* would change what Home Keeper holds for the owner keys."""
    stored = asset.get("parts") or []
    if len(stored) != len(parts):
        return True
    for want in parts:
        have = find_part_by_id(asset, want.get("id", "")) if want.get("id") else None
        if have is None:
            return True
        for key in ("name", "type", "notes"):
            if (have.get(key) or "") != (want.get(key) or ""):
                return True
    return False


def user_keys_update(part: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
    """The full user-key set for one part, with *changes* on top.

    Home Keeper's ``update_asset`` takes every user key of a sent part, so a key we
    leave out would be cleared. A reorder point turns on the Buy task, because that is
    the reason to set one.
    """
    merged = {key: part.get(key) for key in PART_USER_KEYS}
    merged.update({k: v for k, v in changes.items() if k in PART_USER_KEYS})
    if "reorder_at" in changes and changes["reorder_at"] is not None:
        merged["create_buy_task"] = True
    # Home Keeper checks each sent part as a whole part, so the name and type go too.
    # They are owner keys on our appliance, and Home Keeper keeps the stored ones.
    return {"id": part["id"], "name": part.get("name"), "type": part.get("type"), **merged}


def stock_unique_id(asset_id: str, part_id: str) -> str:
    """The unique ID of Home Keeper's spares ``number`` entity for one part."""
    return f"home_keeper_asset_{asset_id}_part_{part_id}_stock"


def link_quantity(task: dict[str, Any]) -> tuple[str | None, str | None, Any]:
    """The part link a Home Keeper task has now: ``(asset_id, part_id, quantity)``."""
    link = (task.get("source") or {}).get("part")
    if not isinstance(link, dict):
        return None, None, None
    return link.get("asset_id"), link.get("part_id"), link.get("quantity")


def plan_links(
    schedules: dict[str, dict[str, Any]],
    event_types: dict[str, dict[str, Any]],
    tasks: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """The ``set_task_consumable`` calls that make each care task match its supply.

    A care schedule's task takes its event type's supply amount on each completion,
    so Home Keeper draws the stock whether the dose is logged here or ticked in Home
    Keeper. A task whose event type has no supply loses a link it has. A task that
    already matches gets no call.
    """
    calls: list[dict[str, Any]] = []
    for schedule in schedules.values():
        task = tasks.get(schedule.get("task_id") or "")
        if task is None:
            continue
        supply = event_type_supply(event_types.get(schedule.get("event_type") or ""))
        have = link_quantity(task)
        if supply is None:
            if have[1] is not None:
                calls.append({"task_id": task["id"], "asset_id": None, "part_id": None})
            continue
        want = (supply["asset_id"], supply["part_id"], float(supply["amount"]))
        if have[0] == want[0] and have[1] == want[1] and have[2] is not None:
            if float(have[2]) == want[2]:
                continue
        calls.append(
            {
                "task_id": task["id"],
                "asset_id": want[0],
                "part_id": want[1],
                "quantity": want[2],
            }
        )
    return calls


def with_stock_entities(
    event_types: dict[str, dict[str, Any]], resolve
) -> dict[str, dict[str, Any]]:
    """Copy *event_types*, adding the spares entity id to each supply the card reads.

    *resolve* maps ``(asset_id, part_id)`` to an entity id or None. The stored event
    types are left as they are: the entity id is derived, not stored.
    """
    out: dict[str, dict[str, Any]] = {}
    for key, meta in event_types.items():
        supply = event_type_supply(meta)
        if supply is None:
            out[key] = meta
            continue
        entity_id = resolve(supply["asset_id"], supply["part_id"])
        out[key] = {**meta, "supply": {**supply, "entity_id": entity_id}}
    return out
