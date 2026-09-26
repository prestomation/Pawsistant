"""Supplies in Home Keeper: the service calls behind :mod:`supplies`.

Pawsistant keeps one virtual appliance, "Pet supplies", in Home Keeper. Each supply
an event type uses is a part on it. Home Keeper keeps the count, the reorder point and
the Buy task. This module makes the calls; the rules are in :mod:`supplies`.

A log draws stock in one of two ways, never both:

* The pet has a care schedule for the event type. Its Home Keeper task is linked to
  the part with ``set_task_consumable``, so Home Keeper draws the stock when the task
  is completed, from Pawsistant or from Home Keeper, and gives it back on an undo.
* It has none. Pawsistant calls ``adjust_part_stock`` and keeps the delta Home Keeper
  really applied on the event, so a delete of the event can give exactly that back.

Like :mod:`care_link`, every call is guarded. Without Home Keeper, or with a Home
Keeper that has no appliance services, each function does nothing.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant, SupportsResponse

from . import supplies
from .care_link import HK_DOMAIN, _config_entry_id, _has, home_keeper_available

_LOGGER = logging.getLogger(__name__)


async def _call(
    hass: HomeAssistant, service: str, data: dict[str, Any], *, response: bool = False
) -> dict[str, Any] | None:
    """Call a Home Keeper service. Log and return None when it fails."""
    if not _has(hass, service):
        return None
    try:
        result = await hass.services.async_call(
            HK_DOMAIN, service, data, blocking=True, return_response=response
        )
    except Exception as err:  # noqa: BLE001 — a log must never fail on a stock call
        _LOGGER.warning("Home Keeper %s failed: %s", service, err)
        return None
    return result if response else {}


async def list_assets(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Every Home Keeper appliance. Our own call has no user, so it sees them all."""
    resp = await _call(hass, "list_assets", {}, response=True)
    return list((resp or {}).get("assets") or [])


async def find_appliance(hass: HomeAssistant) -> dict[str, Any] | None:
    """Our supplies appliance, or None."""
    return supplies.find_appliance(await list_assets(hass))


async def ensure_appliance(hass: HomeAssistant) -> dict[str, Any] | None:
    """Find our supplies appliance, or create it. None without Home Keeper."""
    if not home_keeper_available(hass) or not _has(hass, "update_managed_asset"):
        return None
    asset = await find_appliance(hass)
    if asset is not None:
        return asset
    if await _call(hass, "add_asset", supplies.appliance_payload(_config_entry_id(hass))) is None:
        return None
    return await find_appliance(hass)


async def sync_parts(
    hass: HomeAssistant, event_types: dict[str, dict[str, Any]], extra: str | None = None
) -> dict[str, Any] | None:
    """Make the appliance's part list match the supplies the event types use.

    Returns the appliance as Home Keeper holds it after the change, or None.
    """
    asset = await ensure_appliance(hass)
    if asset is None:
        return None
    parts = supplies.desired_parts(asset, event_types, extra)
    if supplies.parts_differ(asset, parts):
        await _call(
            hass,
            "update_managed_asset",
            {"asset_id": asset["id"], "name": supplies.APPLIANCE_NAME, "parts": parts},
        )
        asset = await find_appliance(hass) or asset
    return asset


async def resolve_supply(
    hass: HomeAssistant,
    event_types: dict[str, dict[str, Any]],
    wanted: dict[str, Any],
) -> dict[str, Any] | None:
    """Turn ``{name, amount}`` into the stored ``{asset_id, part_id, name, amount}``.

    Adds the part to our appliance when it is new. None when Home Keeper cannot hold
    it, so the caller can refuse the setting instead of storing a supply with no count.
    """
    asset = await sync_parts(hass, event_types, extra=wanted["name"])
    if asset is None:
        return None
    part = supplies.find_part_by_name(asset, wanted["name"])
    if part is None:
        return None
    return {
        "asset_id": asset["id"],
        "part_id": part["id"],
        "name": part.get("name") or wanted["name"],
        "amount": wanted["amount"],
    }


async def draw(hass: HomeAssistant, supply: dict[str, Any], amount: float) -> float | None:
    """Take *amount* off the supply's count. Return the delta really applied.

    The count stops at zero, so the applied delta can be smaller than asked for. A Home
    Keeper that returns no response gives no figure; the asked delta is then the best
    guess. None when nothing was called, and for a supply with no part to draw from.
    """
    if not supply.get("asset_id") or not supply.get("part_id"):
        return None
    data = {
        "asset_id": supply["asset_id"],
        "part_id": supply["part_id"],
        "delta": -float(amount),
    }
    if not _has(hass, "adjust_part_stock"):
        return None
    if hass.services.supports_response(HK_DOMAIN, "adjust_part_stock") == SupportsResponse.NONE:
        return None if await _call(hass, "adjust_part_stock", data) is None else -float(amount)
    resp = await _call(hass, "adjust_part_stock", data, response=True)
    if resp is None:
        return None
    applied = resp.get("applied_delta")
    return float(applied) if applied is not None else -float(amount)


async def give_back(hass: HomeAssistant, asset_id: str, part_id: str, applied: float) -> None:
    """Undo a :func:`draw` that applied *applied* (a negative number)."""
    if not applied:
        return
    await _call(
        hass,
        "adjust_part_stock",
        {"asset_id": asset_id, "part_id": part_id, "delta": -float(applied)},
    )


async def update_stock(
    hass: HomeAssistant, supply: dict[str, Any], changes: dict[str, Any]
) -> bool:
    """Write the user's count, reorder point, unit or pack size on a supply's part."""
    asset = await find_appliance(hass)
    if asset is None or asset.get("id") != supply.get("asset_id"):
        return False
    part = supplies.find_part_by_id(asset, supply["part_id"])
    if part is None:
        return False
    payload = supplies.user_keys_update(part, changes)
    return (
        await _call(hass, "update_asset", {"asset_id": asset["id"], "parts": [payload]})
        is not None
    )


async def sync_links(hass: HomeAssistant, store) -> None:
    """Link each care task to its event type's supply, and unlink the rest."""
    schedules = store.get_care_schedules()
    if not schedules or not _has(hass, "set_task_consumable"):
        return
    resp = await _call(hass, "list_tasks", {}, response=True)
    if resp is None:
        return
    tasks = {t["id"]: t for t in resp.get("tasks") or [] if t.get("id")}
    for data in supplies.plan_links(schedules, store.get_event_types(), tasks):
        await _call(hass, "set_task_consumable", data)


def stock_entity_id(hass: HomeAssistant, asset_id: str, part_id: str) -> str | None:
    """The entity id of Home Keeper's spares number for one part, or None."""
    from homeassistant.helpers import entity_registry as er

    return er.async_get(hass).async_get_entity_id(
        "number", HK_DOMAIN, supplies.stock_unique_id(asset_id, part_id)
    )


async def hand_back(hass: HomeAssistant) -> None:
    """On removal, give the appliance to the user, or delete it if it counts nothing.

    Deleting a counted appliance would delete the user's counts with it.
    """
    asset = await find_appliance(hass)
    if asset is None:
        return
    counted = any(p.get("stock") is not None for p in asset.get("parts") or [])
    if counted:
        await _call(hass, "update_asset", {"asset_id": asset["id"], "managed_by": None})
    else:
        await _call(hass, "delete_asset", {"asset_id": asset["id"], "force": True})
