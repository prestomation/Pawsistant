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
