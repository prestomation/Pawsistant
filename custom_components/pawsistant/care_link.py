"""Optional link to the Home Keeper task tracker.

Pawsistant is one example client of Home Keeper's public, integration-agnostic
task-contribution contract (see Home Keeper's ``docs/INTEGRATING.md``). Everything
Home-Keeper-specific lives in this single module so the rest of Pawsistant stays
unaware of it; if Home Keeper isn't installed, every function here degrades to a
no-op.

The link works in both directions, behaving like "the same button":

* **Pawsistant → Home Keeper** — when a care activity that has a schedule is logged,
  :func:`complete_task` marks the linked Home Keeper task done (passing our
  :data:`ORIGIN` marker).
* **Home Keeper → Pawsistant** — Home Keeper fires ``home_keeper_task_completed`` on
  every completion; :func:`parse_completion_event` recognises the ones that belong to
  us so the caller can mirror them into a logged event.

Loop prevention uses two independent guards: the ``origin`` marker (we ignore the echo
of a completion we initiated), and the caller mirroring inbound completions by writing
straight to the store rather than re-entering the ``log_event`` service path.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Home Keeper's public contract.
HK_DOMAIN = "home_keeper"
HK_EVENT_TASK_COMPLETED = "home_keeper_task_completed"
# Marker we pass to home_keeper.complete_task so we can ignore the resulting event.
ORIGIN = "pawsistant"
# Namespace under a Home Keeper task's opaque ``source`` dict that we own.
SOURCE_NS = "pawsistant"


def home_keeper_available(hass: HomeAssistant) -> bool:
    """Return True if a Home Keeper config entry is set up."""
    return bool(hass.config_entries.async_entries(HK_DOMAIN))


def _has(hass: HomeAssistant, service: str) -> bool:
    return hass.services.has_service(HK_DOMAIN, service)


def _device_id_for_dog(hass: HomeAssistant, dog_id: str) -> str | None:
    """Resolve the registry device id of a pet, so the task's entities attach to it."""
    from homeassistant.helpers import device_registry as dr

    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, dog_id)})
    return device.id if device else None


def _recurrence_payload(schedule: dict[str, Any]) -> dict[str, Any]:
    """Translate a stored care schedule into Home Keeper add_task recurrence fields."""
    if schedule.get("recurrence_type") == "fixed":
        return {
            "recurrence_type": "fixed",
            "interval": schedule.get("interval", 1),
            "freq": schedule.get("freq", "MONTHLY"),
            "anchor": schedule.get("anchor"),
        }
    return {
        "recurrence_type": "floating",
        "interval": schedule.get("interval", 1),
        "unit": schedule.get("unit", "weeks"),
    }


def _task_name(store, dog_id: str, event_type: str) -> str:
    dog = store.get_dogs().get(dog_id, {})
    et_meta = store.get_event_types().get(event_type, {})
    return f"{dog.get('name', 'Pet')}: {et_meta.get('name', event_type)}"


def _config_entry_id(hass: HomeAssistant) -> str | None:
    """Return our config entry id for Home Keeper's orphan-detection and deep-link."""
    entries = hass.config_entries.async_entries(DOMAIN)
    return entries[0].entry_id if entries else None


def _completion_prompt(store, dog_id: str, event_type: str) -> str:
    """Short hint shown in Home Keeper near the Done button."""
    dog = store.get_dogs().get(dog_id, {})
    et_meta = store.get_event_types().get(event_type, {})
    dog_name = dog.get("name", "Pet")
    event_name = et_meta.get("name", event_type)
    return f"Log as {dog_name}'s {event_name.lower()}?"


async def create_task(
    hass: HomeAssistant, store, schedule_id: str, schedule: dict[str, Any]
) -> str | None:
    """Create the Home Keeper task for *schedule* and return its task_id (or None).

    The task is tagged with an opaque ``source`` namespaced under :data:`SOURCE_NS`
    so we can find it again; ``add_task`` returns the new id in its service response.
    A ``managed_by`` block declares Pawsistant as the owner so Home Keeper shows a
    "Managed by Pawsistant" chip and locks the device/name fields.
    """
    if not _has(hass, "add_task"):
        return None
    dog_id = schedule["dog_id"]
    event_type = schedule["event_type"]
    data: dict[str, Any] = {
        "name": _task_name(store, dog_id, event_type),
        "device_id": _device_id_for_dog(hass, dog_id),
        "source": {
            SOURCE_NS: {
                "dog_id": dog_id,
                "event_type": event_type,
                "schedule_id": schedule_id,
            }
        },
        "managed_by": {
            "integration": SOURCE_NS,
            "display_name": "Pawsistant",
            "icon": "mdi:paw",
            "locked_fields": ["device_id", "name"],
            "config_entry_id": _config_entry_id(hass),
            "completion_prompt": _completion_prompt(store, dog_id, event_type),
            "deletion_protected": True,
        },
        **_recurrence_payload(schedule),
    }
    data = {k: v for k, v in data.items() if v is not None}
    try:
        resp = await hass.services.async_call(
            HK_DOMAIN, "add_task", data, blocking=True, return_response=True
        )
    except Exception as err:  # noqa: BLE001 — never let an HK error break our flow
        _LOGGER.warning("Home Keeper add_task failed for schedule %s: %s", schedule_id, err)
        return None
    return (resp or {}).get("task_id")


async def complete_task(hass: HomeAssistant, task_id: str, completed_at: str | None) -> None:
    """Mark a linked Home Keeper task complete (passing our origin marker)."""
    if not task_id or not _has(hass, "complete_task"):
        return
    data: dict[str, Any] = {"task_id": task_id, "origin": ORIGIN}
    if completed_at:
        data["completed_at"] = completed_at
    try:
        await hass.services.async_call(HK_DOMAIN, "complete_task", data, blocking=True)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Home Keeper complete_task failed for %s: %s", task_id, err)


async def delete_task(hass: HomeAssistant, task_id: str | None) -> None:
    """Delete a linked Home Keeper task (no-op if absent)."""
    if not task_id or not _has(hass, "delete_task"):
        return
    try:
        await hass.services.async_call(
            HK_DOMAIN, "delete_task", {"task_id": task_id}, blocking=True
        )
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Home Keeper delete_task failed for %s: %s", task_id, err)


def parse_completion_event(event) -> dict[str, Any] | None:
    """Return our source payload from a completion event, or None to ignore it.

    Returns ``None`` when the event is the echo of a completion we initiated
    (``origin`` is ours) or when the task isn't one of ours.
    """
    data = event.data or {}
    if data.get("origin") == ORIGIN:
        return None
    source = data.get("source")
    if not isinstance(source, dict):
        return None
    src = source.get(SOURCE_NS)
    if not isinstance(src, dict):
        return None
    return {
        "dog_id": src.get("dog_id"),
        "event_type": src.get("event_type"),
        "schedule_id": src.get("schedule_id"),
        "completed_at": data.get("completed_at"),
    }


async def reconcile(hass: HomeAssistant, store) -> None:
    """Self-heal: recreate Home Keeper tasks for schedules whose task is missing.

    Covers tasks a user deleted directly in Home Keeper, or schedules created while
    Home Keeper was absent. Best-effort and guarded — does nothing if Home Keeper or
    ``list_tasks`` is unavailable.
    """
    schedules = store.get_care_schedules()
    if not schedules or not home_keeper_available(hass) or not _has(hass, "list_tasks"):
        return
    try:
        resp = await hass.services.async_call(
            HK_DOMAIN, "list_tasks", {}, blocking=True, return_response=True
        )
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Home Keeper list_tasks failed during reconcile: %s", err)
        return
    live_ids = {t.get("id") for t in (resp or {}).get("tasks", [])}
    for schedule_id, schedule in schedules.items():
        if schedule.get("task_id") in live_ids:
            continue
        new_task_id = await create_task(hass, store, schedule_id, schedule)
        if new_task_id and new_task_id != schedule.get("task_id"):
            await store.update_care_schedule(schedule_id, task_id=new_task_id)
            _LOGGER.info(
                "Recreated missing Home Keeper task for care schedule %s", schedule_id
            )
