"""Unit tests for button metrics persistence — regression test for the
'updating one custom event type metric resets another' bug.

Bug: In handle_update_event_type, save_button_metrics() was called with a
     filtered dict that only kept DEFAULT_BUTTON_METRICS keys + the current
     event_type key.  Custom event types not being updated would be dropped.

Fix: save_button_metrics(metrics) now saves the full resolved metrics dict.
"""

from __future__ import annotations

import sys
import types
import pathlib
import importlib.util

# ── Inject stubs ──────────────────────────────────────────────────────────────

def _inject_stubs() -> None:
    if "homeassistant" not in sys.modules:
        ha_mod = types.ModuleType("homeassistant")
        sys.modules["homeassistant"] = ha_mod
    if "homeassistant.core" not in sys.modules:
        core_mod = types.ModuleType("homeassistant.core")
        sys.modules["homeassistant.core"] = core_mod
    if "homeassistant.helpers" not in sys.modules:
        helpers_mod = types.ModuleType("homeassistant.helpers")
        sys.modules["homeassistant.helpers"] = helpers_mod
    if "homeassistant.helpers.storage" not in sys.modules:
        storage_mod = types.ModuleType("homeassistant.helpers.storage")
        storage_mod.Store = type("Store", (), {})
        sys.modules["homeassistant.helpers.storage"] = storage_mod
    if "homeassistant.util" not in sys.modules:
        util_mod = types.ModuleType("homeassistant.util")
        sys.modules["homeassistant.util"] = util_mod
    if "homeassistant.util.dt" not in sys.modules:
        dt_mod = types.ModuleType("homeassistant.util.dt")
        from datetime import datetime, timezone
        dt_mod.now = lambda tz=None: datetime.now(tz or timezone.utc)
        sys.modules["homeassistant.util.dt"] = dt_mod

_inject_stubs()

# Remove stale custom_components modules so importlib loads from disk
for key in list(sys.modules):
    if key == "custom_components.pawsistant" or key.startswith("custom_components.pawsistant."):
        del sys.modules[key]

_repo_root = pathlib.Path(__file__).parent.parent.parent

# Load const.py
_spec = importlib.util.spec_from_file_location(
    "custom_components.pawsistant.const",
    _repo_root / "custom_components" / "pawsistant" / "const.py"
)
_const_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_const_mod)
sys.modules["custom_components.pawsistant.const"] = _const_mod

# Load store.py
_spec_store = importlib.util.spec_from_file_location(
    "custom_components.pawsistant.store",
    _repo_root / "custom_components" / "pawsistant" / "store.py"
)
_store_mod = importlib.util.module_from_spec(_spec_store)
_store_mod = importlib.util.module_from_spec(_spec_store)
_store_mod_obj = importlib.util.module_from_spec(_spec_store)
_spec_store.loader.exec_module(_store_mod_obj)
sys.modules["custom_components.pawsistant.store"] = _store_mod_obj

PawsistantStore = _store_mod_obj.PawsistantStore

from unittest.mock import MagicMock
import pytest


def _make_store():
    """Create a PawsistantStore with in-memory data (no HA hass object needed)."""
    s = PawsistantStore.__new__(PawsistantStore)
    s._hass = MagicMock()
    s._meta = {"known_years": [2025, 2026], "event_types": {}, "button_metrics": {}}
    s._loaded_years = {2025, 2026}
    s._year_events = {2025: [], 2026: []}
    s._year_stores = {}
    return s


class TestButtonMetricsPersistence:
    """Regression: updating one custom event type's metric must not reset another."""

    def test_update_custom_metric_preserves_other_custom_metric(self):
        """Simulate the exact bug scenario:
        1. User changes 'sick' metric to 'days_since'
        2. User changes 'teeth_cleaning' metric to 'days_since'
        3. 'sick' should still be 'days_since' — NOT reset to 'daily_count'

        The bug was that save_button_metrics() was called with a filtered dict
        that only kept DEFAULT_BUTTON_METRICS keys + the current event_type,
        dropping overrides for other custom event types.
        """
        store = _make_store()

        # Step 1: Set 'sick' metric to 'days_since'
        metrics = store.get_button_metrics()
        metrics["sick"] = "days_since"
        store.save_button_metrics(metrics)

        # Verify sick is saved
        assert store.get_button_metrics()["sick"] == "days_since"

        # Step 2: Set 'teeth_cleaning' metric to 'days_since'
        # This is where the bug manifested: the old code filtered the metrics
        # dict to only include DEFAULT_BUTTON_METRICS keys + 'teeth_cleaning',
        # which dropped 'sick' since it's not in DEFAULT_BUTTON_METRICS.
        metrics = store.get_button_metrics()
        metrics["teeth_cleaning"] = "days_since"
        store.save_button_metrics(metrics)

        # Both should be preserved
        result = store.get_button_metrics()
        assert result["sick"] == "days_since", (
            "Bug regression: 'sick' metric was reset to default after "
            "updating 'teeth_cleaning'. The save_button_metrics call must "
            "preserve all custom event type overrides, not just the one being updated."
        )
        assert result["teeth_cleaning"] == "days_since"

    def test_update_custom_metric_preserves_default_metrics(self):
        """Updating a custom event type's metric must not lose default metrics
        like medicine=days_since or weight=last_value."""
        store = _make_store()

        metrics = store.get_button_metrics()
        metrics["sick"] = "days_since"
        store.save_button_metrics(metrics)

        metrics = store.get_button_metrics()
        metrics["teeth_cleaning"] = "days_since"
        store.save_button_metrics(metrics)

        result = store.get_button_metrics()
        assert result["medicine"] == "days_since"
        assert result["weight"] == "last_value"
        assert result["vaccine"] == "days_since"
        assert result["walk"] == "daily_count"

    def test_update_multiple_custom_metrics_sequentially(self):
        """Set 3 custom event types to non-default metrics, then verify all persist."""
        store = _make_store()

        custom_types = ["sick", "teeth_cleaning", "nail_trim"]
        for et in custom_types:
            metrics = store.get_button_metrics()
            metrics[et] = "days_since"
            store.save_button_metrics(metrics)

        result = store.get_button_metrics()
        for et in custom_types:
            assert result[et] == "days_since", (
                f"Custom metric for '{et}' was lost"
            )

    def test_get_button_metrics_includes_custom_types_not_in_defaults(self):
        """get_button_metrics() must return custom event types that have
        metric overrides, not just the 4 DEFAULT_BUTTON_METRICS keys."""
        store = _make_store()
        metrics = store.get_button_metrics()
        metrics["sick"] = "days_since"
        store.save_button_metrics(metrics)

        # get_button_metrics resolves defaults + overrides
        result = store.get_button_metrics()
        assert "sick" in result
        assert result["sick"] == "days_since"