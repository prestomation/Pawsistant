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

Undo travels the same two ways, because a mistaken "done" is as much a shared fact as
the "done" itself. Deleting a logged event calls :func:`delete_completion`, and Home
Keeper's ``home_keeper_task_uncompleted`` comes back through
:func:`parse_uncompletion_event`. Both directions identify the completion by its
timestamp, which is how Home Keeper keys its own history.

Loop prevention uses two independent guards: the ``origin`` marker (we ignore the echo
of a completion or undo we initiated), and the caller mirroring inbound changes by
writing straight to the store rather than re-entering the ``log_event`` /
``delete_event`` service paths.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Home Keeper's public contract.
HK_DOMAIN = "home_keeper"
HK_EVENT_TASK_COMPLETED = "home_keeper_task_completed"
# Fired when a completion is undone. Carries the ``ts`` of the completion that was
# removed, which is what lets us find the one logged event it stood for.
HK_EVENT_TASK_UNCOMPLETED = "home_keeper_task_uncompleted"
# Home Keeper fires this (at its setup and on reload) to ask companion integrations
# to (re-)announce themselves to its discovery registry. We both register at our own
# setup and respond to this ping, so discovery works regardless of startup order.
HK_EVENT_REGISTER_COMPANIONS = "home_keeper_register_companions"
# Marker we pass to home_keeper.complete_task so we can ignore the resulting event.
ORIGIN = "pawsistant"
# Namespace under a Home Keeper task's opaque ``source`` dict that we own.
SOURCE_NS = "pawsistant"
# Note written on an event we logged on Home Keeper's behalf. It is what marks an event
# as a *mirror* rather than something the user logged, which the reconcile heal pass
# relies on before it deletes anything.
MIRROR_NOTE = "via Home Keeper"


def home_keeper_available(hass: HomeAssistant) -> bool:
    """Return True if a Home Keeper config entry is set up."""
    return bool(hass.config_entries.async_entries(HK_DOMAIN))


async def register_companion(hass: HomeAssistant, entry_id: str) -> None:
    """Announce Pawsistant to Home Keeper's companion discovery registry.

    Best-effort and entirely optional: if Home Keeper isn't installed (or is an
    older version without the ``register_companion`` service) this is a no-op.
    Registering makes Pawsistant show up under Home Keeper's Settings → Companions,
    with a "Configure" link back to our own options (where care schedules live).
    """
    if not _has(hass, "register_companion"):
        return
    try:
        await hass.services.async_call(
            HK_DOMAIN,
            "register_companion",
            {
                "domain": DOMAIN,
                "name": "Pawsistant",
                "icon": "mdi:paw",
                "description": (
                    "Pet care tracker — logs walks, meals, meds and weight, and can "
                    "schedule recurring pet-care chores as Home Keeper tasks."
                ),
                "config_entry_id": entry_id,
                "docs_url": "https://github.com/prestomation/Pawsistant",
                "capabilities": ["care_schedules"],
            },
            blocking=False,
        )
    except Exception:  # noqa: BLE001 — discovery is best-effort; never break setup
        _LOGGER.debug("Home Keeper companion registration failed", exc_info=True)


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
    hass: HomeAssistant,
    store,
    schedule_id: str,
    schedule: dict[str, Any],
    *,
    last_completed: str | None = None,
) -> str | None:
    """Create the Home Keeper task for *schedule* and return its task_id (or None).

    The task is tagged with an opaque ``source`` namespaced under :data:`SOURCE_NS`
    so we can find it again; ``add_task`` returns the new id in its service response.
    A ``managed_by`` block declares Pawsistant as the owner so Home Keeper shows a
    "Managed by Pawsistant" chip and locks the device/name fields.

    ``last_completed`` is an optional "last done" seed (the pet's most recent logged
    event of this type). When given, Home Keeper measures the first due date from it
    rather than treating the task as due now. Only passed at initial creation — the
    reconcile path recreates a missing task without it, so a task deleted in Home
    Keeper comes back as due-now rather than re-seeded from a stale date. Older Home
    Keeper versions that don't know the field will reject the call; the task is simply
    created without a schedule link until Home Keeper is updated.
    """
    if not _has(hass, "add_task"):
        return None
    dog_id = schedule["dog_id"]
    event_type = schedule["event_type"]
    managed_by: dict[str, Any] = {
        "integration": SOURCE_NS,
        "display_name": "Pawsistant",
        "icon": "mdi:paw",
        "locked_fields": ["device_id", "name"],
        "completion_prompt": _completion_prompt(store, dog_id, event_type),
    }
    # Home Keeper requires a config_entry_id before it will honour deletion
    # protection (it's how it detects us going away and lets the user clean up).
    # Only opt into protection when we can supply one.
    entry_id = _config_entry_id(hass)
    if entry_id:
        managed_by["config_entry_id"] = entry_id
        managed_by["deletion_protected"] = True
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
        "managed_by": managed_by,
        "last_completed": last_completed,
        **_recurrence_payload(schedule),
    }
    data = {k: v for k, v in data.items() if v is not None}
    try:
        resp = await hass.services.async_call(
            HK_DOMAIN, "add_task", data, blocking=True, return_response=True
        )
    except Exception as err:  # noqa: BLE001 — never let an HK error break our flow
        # Retry without the seed ONLY when the failure is an older Home Keeper's
        # strict add_task schema rejecting the unknown ``last_completed`` key
        # (detected by the key name in the error). Retrying on any other failure is
        # unsafe: Home Keeper persists the task *before* it reloads the entry, so a
        # post-persist error would otherwise make us create a second, duplicate task.
        if "last_completed" in data and "last_completed" in str(err):
            data.pop("last_completed")
            _LOGGER.debug(
                "Home Keeper add_task rejected the last_completed seed for schedule "
                "%s; retrying without it (older Home Keeper?)",
                schedule_id,
            )
            try:
                resp = await hass.services.async_call(
                    HK_DOMAIN, "add_task", data, blocking=True, return_response=True
                )
            except Exception as err2:  # noqa: BLE001
                _LOGGER.warning(
                    "Home Keeper add_task failed for schedule %s: %s", schedule_id, err2
                )
                return None
        else:
            _LOGGER.warning(
                "Home Keeper add_task failed for schedule %s: %s", schedule_id, err
            )
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


async def delete_completion(
    hass: HomeAssistant, task_id: str | None, ts: str | None
) -> None:
    """Undo a linked Home Keeper completion (passing our origin marker).

    The counterpart of :func:`complete_task`: when the logged event that stood for a
    completion is deleted, the completion goes with it. A ``ts`` Home Keeper doesn't
    hold is a no-op on its side, so a stale call is safe. No-op without Home Keeper, or
    on an older version that predates the service.
    """
    if not task_id or not ts or not _has(hass, "delete_completion"):
        return
    try:
        await hass.services.async_call(
            HK_DOMAIN,
            "delete_completion",
            {"task_id": task_id, "ts": ts, "origin": ORIGIN},
            blocking=True,
        )
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning(
            "Home Keeper delete_completion failed for %s at %s: %s", task_id, ts, err
        )


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


def _parse_our_task_event(event) -> dict[str, Any] | None:
    """Return the source block of a Home Keeper task event that belongs to us.

    Returns ``None`` when the event is the echo of a change we initiated (``origin``
    is ours) or when the task isn't one of ours. Shared by the completion and
    uncompletion parsers so the two can't drift apart on what "ours" means.
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
    }


def parse_completion_event(event) -> dict[str, Any] | None:
    """Return our source payload from a completion event, or None to ignore it.

    Returns ``None`` when the event is the echo of a completion we initiated
    (``origin`` is ours) or when the task isn't one of ours.
    """
    link = _parse_our_task_event(event)
    if link is None:
        return None
    return {**link, "completed_at": (event.data or {}).get("completed_at")}


def parse_uncompletion_event(event) -> dict[str, Any] | None:
    """Return our source payload from an undo event, or None to ignore it.

    Same filtering as :func:`parse_completion_event`, plus the ``ts`` of the completion
    Home Keeper removed. Without that timestamp there is nothing to match a logged
    event against, so an event that somehow lacks it is ignored rather than guessed at
    (an older Home Keeper fired the undo event with no ``ts`` at all).
    """
    link = _parse_our_task_event(event)
    if link is None:
        return None
    ts = (event.data or {}).get("ts")
    if not ts:
        return None
    return {**link, "ts": ts}


def _parse_iso(value: Any) -> datetime | None:
    """Parse an ISO timestamp for the heal pass, or None if it can't be trusted.

    A *naive* timestamp is rejected rather than assumed to be in some zone. Home
    Keeper always writes aware values, and so does the mirror path, so a naive one
    only turns up if a user hand-edited an entry — and guessing its zone could put it
    on the wrong side of the comparison that decides whether to delete it. Refusing to
    read it means it is never a deletion candidate, which is the safe direction to
    fail in.
    """
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None


async def _heal_orphaned_mirrors(store, schedule: dict[str, Any], task: dict) -> int:
    """Delete logged events that mirror a Home Keeper completion that no longer exists.

    The event listeners keep the two sides together while both are running; this closes
    the gap for undos that happened while Pawsistant was down, and repairs installs that
    diverged before the undo link existed at all.

    Deleting logged data on a heuristic deserves narrow guards, so this only ever
    removes an event that clears **both**:

    * it carries our mirror marker as its note, so an event the user logged themselves
      is never a candidate — even one at the same instant; and
    * it is no older than the window Home Keeper can still speak for. Completion
      history is capped, so an entry that merely aged out of it is not an orphan. The
      floor is the oldest retained completion, or the task's own creation date when the
      history is empty (which is also what protects the events belonging to a schedule
      whose task was just recreated from scratch).

    Returns the number of events removed.
    """
    dog_id = schedule.get("dog_id")
    event_type = schedule.get("event_type")
    if not dog_id or not event_type:
        return 0
    kept = {
        parsed
        for parsed in (
            _parse_iso(entry.get("ts")) for entry in task.get("completions") or []
        )
        if parsed is not None
    }
    floor = min(kept) if kept else _parse_iso(task.get("created"))
    if floor is None:
        return 0  # no trustworthy window; leave the log alone
    removed = 0
    for event in await store.get_events(dog_id, event_type, since=floor):
        if event.get("note") != MIRROR_NOTE:
            continue
        when = _parse_iso(event.get("timestamp"))
        if when is None or when < floor or when in kept:
            continue
        if await store.delete_event(event["id"]):
            removed += 1
            _LOGGER.info(
                "Removed %s event mirroring a Home Keeper completion that was undone "
                "while Pawsistant was not running (%s)",
                event_type,
                event.get("timestamp"),
            )
    return removed


async def reconcile(hass: HomeAssistant, store) -> None:
    """Self-heal the link in both directions.

    Recreates Home Keeper tasks for schedules whose task is missing (covering tasks a
    user deleted directly in Home Keeper, or schedules created while Home Keeper was
    absent), and for schedules whose task is still there, drops mirrored events left
    behind by completions that were undone while we weren't listening (see
    :func:`_heal_orphaned_mirrors`).

    Best-effort and guarded — does nothing if Home Keeper or ``list_tasks`` is
    unavailable.
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
    live = {t["id"]: t for t in (resp or {}).get("tasks", []) if t.get("id")}
    for schedule_id, schedule in schedules.items():
        task = live.get(schedule.get("task_id"))
        if task is not None:
            await _heal_orphaned_mirrors(store, schedule, task)
            continue
        new_task_id = await create_task(hass, store, schedule_id, schedule)
        if new_task_id and new_task_id != schedule.get("task_id"):
            await store.update_care_schedule(schedule_id, task_id=new_task_id)
            _LOGGER.info(
                "Recreated missing Home Keeper task for care schedule %s", schedule_id
            )
