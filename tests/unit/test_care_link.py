"""Unit tests for the Home Keeper cross-integration link (care_link).

Focus: the loop-prevention logic in ``parse_completion_event`` (the inbound,
Home-Keeper-→-Pawsistant direction) and the recurrence payload mapping. These are
pure functions, so we stub only the few HA/const symbols care_link imports and load
the module directly — no live Home Assistant required.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
from datetime import datetime, timezone
from types import SimpleNamespace


def _load_care_link():
    cached = sys.modules.get("custom_components.pawsistant.care_link")
    if cached is not None:
        return cached

    # Minimal HA + const stubs (care_link only needs HomeAssistant for typing and
    # DOMAIN as a constant).
    if "homeassistant" not in sys.modules:
        sys.modules["homeassistant"] = types.ModuleType("homeassistant")
    if "homeassistant.core" not in sys.modules:
        core = types.ModuleType("homeassistant.core")
        core.HomeAssistant = object
        sys.modules["homeassistant.core"] = core
    # create_task lazily imports device_registry to resolve a pet's device id; a stub
    # that returns no device keeps device_id out of the payload (None is filtered).
    if "homeassistant.helpers" not in sys.modules:
        sys.modules["homeassistant.helpers"] = types.ModuleType("homeassistant.helpers")
    if "homeassistant.helpers.device_registry" not in sys.modules:
        dr = types.ModuleType("homeassistant.helpers.device_registry")
        dr.async_get = lambda hass: SimpleNamespace(
            async_get_device=lambda identifiers=None: None
        )
        sys.modules["homeassistant.helpers.device_registry"] = dr
        sys.modules["homeassistant.helpers"].device_registry = dr

    pkg = sys.modules.get("custom_components.pawsistant")
    if pkg is None:
        pkg = types.ModuleType("custom_components.pawsistant")
        pkg.__path__ = []
        pkg.__package__ = "custom_components.pawsistant"
        sys.modules["custom_components.pawsistant"] = pkg
        cc = types.ModuleType("custom_components")
        cc.pawsistant = pkg
        sys.modules["custom_components"] = cc
    if "custom_components.pawsistant.const" not in sys.modules:
        const = types.ModuleType("custom_components.pawsistant.const")
        const.DOMAIN = "pawsistant"
        sys.modules["custom_components.pawsistant.const"] = const

    path = (
        pathlib.Path(__file__).parent.parent.parent
        / "custom_components"
        / "pawsistant"
        / "care_link.py"
    )
    spec = importlib.util.spec_from_file_location(
        "custom_components.pawsistant.care_link", path
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["custom_components.pawsistant.care_link"] = mod
    spec.loader.exec_module(mod)
    return mod


care_link = _load_care_link()


def _event(data: dict):
    return SimpleNamespace(data=data)


def _our_source(**kw):
    base = {"dog_id": "d1", "event_type": "medicine", "schedule_id": "s1"}
    base.update(kw)
    return {care_link.SOURCE_NS: base}


class TestParseCompletionEvent:
    def test_ignores_our_own_origin_echo(self):
        # The echo of a completion WE initiated must be ignored (primary loop guard).
        event = _event({"origin": care_link.ORIGIN, "source": _our_source()})
        assert care_link.parse_completion_event(event) is None

    def test_ignores_event_without_source(self):
        assert care_link.parse_completion_event(_event({"origin": None})) is None

    def test_ignores_foreign_source(self):
        # A task contributed by some other integration is not ours.
        event = _event({"origin": None, "source": {"battery_notes": {"x": 1}}})
        assert care_link.parse_completion_event(event) is None

    def test_ignores_non_dict_source(self):
        event = _event({"origin": None, "source": "nope"})
        assert care_link.parse_completion_event(event) is None

    def test_parses_our_completion(self):
        event = _event(
            {
                "origin": None,
                "completed_at": "2026-06-14T10:00:00+00:00",
                "source": _our_source(),
            }
        )
        link = care_link.parse_completion_event(event)
        assert link == {
            "dog_id": "d1",
            "event_type": "medicine",
            "schedule_id": "s1",
            "completed_at": "2026-06-14T10:00:00+00:00",
        }

    def test_parses_completion_from_other_origin(self):
        # A manual / device-button completion (origin set by some other client) is
        # still mirrored, since it isn't OUR origin.
        event = _event({"origin": "home_keeper_ui", "source": _our_source()})
        assert care_link.parse_completion_event(event) is not None


class TestParseUncompletionEvent:
    def test_ignores_our_own_origin_echo(self):
        # The echo of an undo WE initiated must be ignored (primary loop guard).
        event = _event(
            {
                "origin": care_link.ORIGIN,
                "ts": "2026-06-14T10:00:00+00:00",
                "source": _our_source(),
            }
        )
        assert care_link.parse_uncompletion_event(event) is None

    def test_ignores_foreign_source(self):
        event = _event(
            {
                "origin": None,
                "ts": "2026-06-14T10:00:00+00:00",
                "source": {"battery_notes": {"x": 1}},
            }
        )
        assert care_link.parse_uncompletion_event(event) is None

    def test_ignores_event_without_ts(self):
        # An older Home Keeper fired the undo event with no ts at all. Without it there
        # is nothing to match a logged event against, so guessing would delete the
        # wrong entry — ignore instead.
        event = _event({"origin": None, "source": _our_source()})
        assert care_link.parse_uncompletion_event(event) is None

    def test_parses_our_undo(self):
        event = _event(
            {
                "origin": None,
                "ts": "2026-06-14T10:00:00+00:00",
                "source": _our_source(),
            }
        )
        assert care_link.parse_uncompletion_event(event) == {
            "dog_id": "d1",
            "event_type": "medicine",
            "schedule_id": "s1",
            "ts": "2026-06-14T10:00:00+00:00",
        }

    def test_parses_undo_from_other_origin(self):
        # An undo done in Home Keeper's own UI (or by another client) is still mirrored.
        event = _event(
            {
                "origin": "home_keeper_ui",
                "ts": "2026-06-14T10:00:00+00:00",
                "source": _our_source(),
            }
        )
        assert care_link.parse_uncompletion_event(event) is not None


class TestRecurrencePayload:
    def test_floating_payload(self):
        out = care_link._recurrence_payload(
            {"recurrence_type": "floating", "interval": 2, "unit": "weeks"}
        )
        assert out == {"recurrence_type": "floating", "interval": 2, "unit": "weeks"}

    def test_fixed_payload(self):
        out = care_link._recurrence_payload(
            {
                "recurrence_type": "fixed",
                "interval": 1,
                "freq": "MONTHLY",
                "anchor": "2026-01-01T08:00:00",
            }
        )
        assert out == {
            "recurrence_type": "fixed",
            "interval": 1,
            "freq": "MONTHLY",
            "anchor": "2026-01-01T08:00:00",
        }

    def test_defaults_to_floating(self):
        out = care_link._recurrence_payload({"interval": 3})
        assert out["recurrence_type"] == "floating"
        assert out["unit"] == "weeks"


class _Store:
    def get_dogs(self):
        return {"d1": {"name": "Buddy"}}

    def get_event_types(self):
        return {"medicine": {"name": "Medicine"}}


class _Services:
    """Records add_task calls and replays a scripted behavior per call."""

    def __init__(self, behavior):
        self._behavior = behavior
        self.calls: list[dict] = []

    def has_service(self, domain, service):
        return True

    async def async_call(self, domain, service, data, blocking=True, return_response=False):
        self.calls.append(dict(data))
        return self._behavior(dict(data))


class _Hass:
    def __init__(self, services):
        self.services = services
        self.config_entries = SimpleNamespace(async_entries=lambda domain: [])


_SCHEDULE = {
    "dog_id": "d1",
    "event_type": "medicine",
    "recurrence_type": "floating",
    "interval": 2,
    "unit": "weeks",
}


class TestCreateTaskSeed:
    async def test_forwards_last_completed_seed(self):
        services = _Services(lambda data: {"task_id": "t1"})
        hass = _Hass(services)
        task_id = await care_link.create_task(
            hass, _Store(), "s1", dict(_SCHEDULE), last_completed="2026-06-01T09:00:00"
        )
        assert task_id == "t1"
        assert len(services.calls) == 1
        assert services.calls[0]["last_completed"] == "2026-06-01T09:00:00"

    async def test_no_seed_omits_field(self):
        services = _Services(lambda data: {"task_id": "t1"})
        hass = _Hass(services)
        await care_link.create_task(hass, _Store(), "s1", dict(_SCHEDULE))
        assert len(services.calls) == 1
        assert "last_completed" not in services.calls[0]

    async def test_retries_without_seed_when_rejected(self):
        # Simulate an older Home Keeper whose strict schema rejects last_completed:
        # the first call raises an error naming the key, the retry without it succeeds.
        def behavior(data):
            if "last_completed" in data:
                raise ValueError("extra keys not allowed @ data['last_completed']")
            return {"task_id": "t2"}

        services = _Services(behavior)
        hass = _Hass(services)
        task_id = await care_link.create_task(
            hass, _Store(), "s1", dict(_SCHEDULE), last_completed="2026-06-01T09:00:00"
        )
        assert task_id == "t2"
        assert len(services.calls) == 2
        assert "last_completed" in services.calls[0]
        assert "last_completed" not in services.calls[1]

    async def test_no_retry_when_failure_unrelated_to_seed(self):
        # A failure with no seed in play is reported, not retried.
        def behavior(data):
            raise RuntimeError("home keeper exploded")

        services = _Services(behavior)
        hass = _Hass(services)
        task_id = await care_link.create_task(hass, _Store(), "s1", dict(_SCHEDULE))
        assert task_id is None
        assert len(services.calls) == 1

    async def test_no_retry_when_seed_present_but_error_unrelated(self):
        # Home Keeper persists the task before reloading the entry, so a failure that
        # ISN'T about last_completed (e.g. a post-persist reload error) must NOT be
        # retried — retrying would create a second, duplicate task.
        def behavior(data):
            raise RuntimeError("config entry reload failed")

        services = _Services(behavior)
        hass = _Hass(services)
        task_id = await care_link.create_task(
            hass, _Store(), "s1", dict(_SCHEDULE), last_completed="2026-06-01T09:00:00"
        )
        assert task_id is None
        assert len(services.calls) == 1  # no retry


class TestDeleteCompletion:
    async def test_sends_ts_and_our_origin(self):
        services = _Services(lambda data: None)
        await care_link.delete_completion(
            _Hass(services), "t1", "2026-06-14T10:00:00+00:00"
        )
        assert services.calls == [
            {
                "task_id": "t1",
                "ts": "2026-06-14T10:00:00+00:00",
                "origin": care_link.ORIGIN,
            }
        ]

    async def test_no_call_without_a_ts(self):
        # Nothing identifies the completion, so calling would be a guess.
        services = _Services(lambda data: None)
        await care_link.delete_completion(_Hass(services), "t1", None)
        assert services.calls == []

    async def test_no_call_without_a_task(self):
        services = _Services(lambda data: None)
        await care_link.delete_completion(_Hass(services), None, "2026-06-14T10:00:00Z")
        assert services.calls == []

    async def test_home_keeper_failure_is_swallowed(self):
        # A Home Keeper error must never break the Pawsistant delete that triggered it.
        def behavior(data):
            raise RuntimeError("home keeper exploded")

        await care_link.delete_completion(
            _Hass(_Services(behavior)), "t1", "2026-06-14T10:00:00+00:00"
        )


class _HealStore:
    """Store double for the reconcile heal pass: events in, deletions recorded."""

    def __init__(self, events):
        self._events = list(events)
        self.deleted: list[str] = []

    @staticmethod
    def _lenient(ts):
        # Mirrors store._parse_timestamp, which assumes UTC for a naive value. The
        # real get_events filters with that, so a naive event still reaches the heal
        # loop and has to be rejected there rather than never being returned.
        parsed = datetime.fromisoformat(ts)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    async def get_events(self, dog_id, event_type=None, since=None):
        return [
            e
            for e in self._events
            if e["dog_id"] == dog_id
            and e["event_type"] == event_type
            and (since is None or self._lenient(e["timestamp"]) >= since)
        ]

    async def delete_event(self, event_id):
        self.deleted.append(event_id)
        return True


_HEAL_SCHEDULE = {"dog_id": "d1", "event_type": "medicine"}


def _mirror(event_id, timestamp, note=care_link.MIRROR_NOTE):
    return {
        "id": event_id,
        "dog_id": "d1",
        "event_type": "medicine",
        "timestamp": timestamp,
        "note": note,
    }


class TestHealOrphanedMirrors:
    async def test_drops_a_mirror_whose_completion_is_gone(self):
        store = _HealStore(
            [_mirror("e1", "2026-06-14T10:00:00+00:00"), _mirror("e2", "2026-06-20T10:00:00+00:00")]
        )
        task = {
            "created": "2026-01-01T00:00:00+00:00",
            "completions": [{"ts": "2026-06-14T10:00:00+00:00"}],
        }
        removed = await care_link._heal_orphaned_mirrors(store, _HEAL_SCHEDULE, task)
        assert removed == 1
        assert store.deleted == ["e2"]  # e1 still has its completion

    async def test_never_touches_an_event_the_user_logged(self):
        # Same instant, no mirror marker: this is the user's own entry.
        store = _HealStore([_mirror("e1", "2026-06-20T10:00:00+00:00", note="gave it")])
        task = {
            "created": "2026-01-01T00:00:00+00:00",
            "completions": [{"ts": "2026-06-14T10:00:00+00:00"}],
        }
        assert await care_link._heal_orphaned_mirrors(store, _HEAL_SCHEDULE, task) == 0
        assert store.deleted == []

    async def test_keeps_mirrors_older_than_the_retained_history(self):
        # Home Keeper caps completion history. An entry that merely aged out of it is
        # not an orphan, so anything before the oldest retained completion is off-limits.
        store = _HealStore([_mirror("old", "2026-01-05T10:00:00+00:00")])
        task = {
            "created": "2026-01-01T00:00:00+00:00",
            "completions": [{"ts": "2026-06-14T10:00:00+00:00"}],
        }
        assert await care_link._heal_orphaned_mirrors(store, _HEAL_SCHEDULE, task) == 0
        assert store.deleted == []

    async def test_empty_history_falls_back_to_the_task_creation_date(self):
        # The reported bug: one completion, undone, so no history is left. Events after
        # the task was created are orphans; anything before it predates the link.
        store = _HealStore(
            [_mirror("before", "2025-12-01T10:00:00+00:00"), _mirror("after", "2026-06-14T10:00:00+00:00")]
        )
        task = {"created": "2026-01-01T00:00:00+00:00", "completions": []}
        removed = await care_link._heal_orphaned_mirrors(store, _HEAL_SCHEDULE, task)
        assert removed == 1
        assert store.deleted == ["after"]

    async def test_does_nothing_without_a_trustworthy_window(self):
        # No history and no readable creation date: refuse to guess rather than delete.
        store = _HealStore([_mirror("e1", "2026-06-14T10:00:00+00:00")])
        assert (
            await care_link._heal_orphaned_mirrors(store, _HEAL_SCHEDULE, {"completions": []})
            == 0
        )
        assert store.deleted == []

    async def test_never_deletes_an_event_with_a_naive_timestamp(self):
        # A hand-edited entry can carry a timestamp with no offset. Guessing its zone
        # could put it on the wrong side of the comparison, so it is never a candidate.
        store = _HealStore([_mirror("e1", "2026-06-20T10:00:00")])
        task = {
            "created": "2026-01-01T00:00:00+00:00",
            "completions": [{"ts": "2026-06-14T10:00:00+00:00"}],
        }
        assert await care_link._heal_orphaned_mirrors(store, _HEAL_SCHEDULE, task) == 0
        assert store.deleted == []

    async def test_matches_a_re_serialised_timestamp(self):
        # The completion round-tripped through Home Keeper and came back spelled with
        # 'Z' instead of '+00:00'. Same instant, so the mirror must survive.
        store = _HealStore([_mirror("e1", "2026-06-14T10:00:00+00:00")])
        task = {
            "created": "2026-01-01T00:00:00+00:00",
            "completions": [{"ts": "2026-06-14T10:00:00Z"}],
        }
        assert await care_link._heal_orphaned_mirrors(store, _HEAL_SCHEDULE, task) == 0
        assert store.deleted == []
