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
        # the first call raises, the retry without the seed succeeds.
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
