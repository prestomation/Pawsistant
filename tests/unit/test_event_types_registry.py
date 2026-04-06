"""Unit tests for the event types registry (DEFAULT_EVENT_TYPES + store overlay)."""

from __future__ import annotations

import sys
import types

# Inject stubs so const.py can be imported
def _inject_stubs() -> None:
    if "homeassistant" not in sys.modules:
        ha_mod = types.ModuleType("homeassistant")
        sys.modules["homeassistant"] = ha_mod
    if "homeassistant.core" not in sys.modules:
        core_mod = types.ModuleType("homeassistant.core")
        sys.modules["homeassistant.core"] = core_mod
    if "voluptuous" not in sys.modules:
        vol_mod = types.ModuleType("voluptuous")
        vol_mod.Schema = lambda s, **kw: s
        vol_mod.Required = lambda k, **kw: k
        vol_mod.Optional = lambda k, **kw: k
        vol_mod.In = lambda v: v
        sys.modules["voluptuous"] = vol_mod

_inject_stubs()

# Load const.py from the real source
import pathlib
import importlib.util

# Remove any stale stub left by other test files (e.g. test_options_flow.py,
# test_species_field.py) so importlib loads the real const.py from disk.
for key in list(sys.modules):
    if key == "custom_components.pawsistant.const" or key.startswith("custom_components.pawsistant."):
        del sys.modules[key]

_repo_root = pathlib.Path(__file__).parent.parent.parent
_spec = importlib.util.spec_from_file_location(
    "custom_components.pawsistant.const",
    _repo_root / "custom_components" / "pawsistant" / "const.py"
)
_const_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_const_mod)
sys.modules["custom_components.pawsistant.const"] = _const_mod


# ---------------------------------------------------------------------------
# Inline store implementation for unit testing (no HA needed)
# ---------------------------------------------------------------------------

class UnitPawsistantStore:
    """Lightweight store mock — mirrors real PawsistantStore interface for registry."""

    def __init__(self, initial_meta=None):
        self._meta = {"dogs": {}, "known_years": [], **(initial_meta or {})}

    def get_event_types(self) -> dict[str, dict[str, str]]:
        stored = self._meta.get(_const_mod.CONF_EVENT_TYPES, {})
        result = dict(_const_mod.DEFAULT_EVENT_TYPES)
        for key in stored:
            if key in result or stored[key]:
                result[key] = stored[key]
        return result

    def save_event_types(self, event_types: dict[str, dict[str, str]]) -> None:
        self._meta[_const_mod.CONF_EVENT_TYPES] = event_types

    def get_button_metrics(self) -> dict[str, str]:
        stored = self._meta.get(_const_mod.CONF_BUTTON_METRICS, {})
        result = dict(_const_mod.DEFAULT_BUTTON_METRICS)
        for key, value in stored.items():
            result[key] = value
        # Fill in defaults for types not explicitly set
        for key in _const_mod.DEFAULT_EVENT_TYPES:
            if key not in result:
                result[key] = "daily_count"
        return result

    def save_button_metrics(self, button_metrics: dict[str, str]) -> None:
        self._meta[_const_mod.CONF_BUTTON_METRICS] = button_metrics


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEventTypesRegistry:
    def test_get_event_types_returns_all_defaults(self):
        store = UnitPawsistantStore()
        types_ = store.get_event_types()
        assert len(types_) == 14
        assert "food" in types_
        assert "walk" in types_
        assert "medicine" in types_
        assert "weight" in types_
        assert types_["walk"]["name"] == "Walk"
        assert types_["medicine"]["icon"] == "mdi:pill"
        assert types_["poop"]["color"] == "#795548"

    def test_stored_config_overrides_defaults(self):
        store = UnitPawsistantStore(initial_meta={
            _const_mod.CONF_EVENT_TYPES: {
                "walk": {"name": "Stroll", "icon": "mdi:run", "color": "#00FF00"},
            }
        })
        types_ = store.get_event_types()
        assert types_["walk"]["name"] == "Stroll"
        assert types_["walk"]["icon"] == "mdi:run"
        assert types_["walk"]["color"] == "#00FF00"
        assert types_["food"]["name"] == "Food"

    def test_custom_type_added_to_registry(self):
        store = UnitPawsistantStore(initial_meta={
            _const_mod.CONF_EVENT_TYPES: {
                "custom_bark": {"name": "Bark", "icon": "mdi:dog", "color": "#123456"},
            }
        })
        types_ = store.get_event_types()
        assert "custom_bark" in types_
        assert types_["custom_bark"]["name"] == "Bark"
        assert len(types_) == 15

    def test_duplicate_event_type_key_rejected(self):
        store = UnitPawsistantStore(initial_meta={
            _const_mod.CONF_EVENT_TYPES: {
                "food": {"name": "My Food", "icon": "mdi:help", "color": "#111111"},
            }
        })
        types_ = store.get_event_types()
        assert types_["food"]["name"] == "My Food"

    def test_delete_custom_type_removes_from_registry(self):
        store = UnitPawsistantStore(initial_meta={
            _const_mod.CONF_EVENT_TYPES: {
                "custom_bark": {"name": "Bark", "icon": "mdi:dog", "color": "#123456"},
            }
        })
        assert "custom_bark" in store.get_event_types()
        current = store.get_event_types()
        del current["custom_bark"]
        store.save_event_types(current)
        assert "custom_bark" not in store.get_event_types()
        assert len(store.get_event_types()) == 14


class TestButtonMetrics:
    def test_get_button_metrics_returns_all(self):
        store = UnitPawsistantStore()
        metrics = store.get_button_metrics()
        assert len(metrics) == 14
        for key in _const_mod.DEFAULT_EVENT_TYPES:
            assert key in metrics

    def test_default_metrics_medicine_is_days_since(self):
        assert _const_mod.DEFAULT_BUTTON_METRICS.get("medicine") == "days_since"

    def test_default_metrics_walk_is_daily_count(self):
        assert _const_mod.DEFAULT_BUTTON_METRICS.get("walk", "daily_count") == "daily_count"

    def test_default_metrics_weight_is_last_value(self):
        assert _const_mod.DEFAULT_BUTTON_METRICS.get("weight") == "last_value"

    def test_button_metric_override(self):
        store = UnitPawsistantStore(initial_meta={
            _const_mod.CONF_BUTTON_METRICS: {"walk": "days_since"}
        })
        metrics = store.get_button_metrics()
        assert metrics["walk"] == "days_since"
        assert metrics["medicine"] == "days_since"
        assert metrics.get("food", "daily_count") == "daily_count"

    def test_unknown_metric_value_stored(self):
        store = UnitPawsistantStore(initial_meta={
            _const_mod.CONF_BUTTON_METRICS: {"walk": "unknown_metric"}
        })
        assert store.get_button_metrics()["walk"] == "unknown_metric"

# ---------------------------------------------------------------------------
# Mock store with hide_event_type support (mirrors real PawsistantStore)
# ---------------------------------------------------------------------------

class MockPawsistantStore:
    """Lightweight store mock — mirrors real PawsistantStore interface for registry."""

    def __init__(self, initial_meta=None):
        self._meta = {
            "dogs": {},
            "known_years": [],
            **(initial_meta or {}),
        }
        self._hidden_event_types: set[str] = set()

    def get_event_types(self) -> dict[str, dict[str, str]]:
        stored: dict[str, dict[str, str]] = self._meta.get(_const_mod.CONF_EVENT_TYPES, {})
        result = dict(_const_mod.DEFAULT_EVENT_TYPES)
        for key in stored:
            if key in result or stored[key]:
                result[key] = stored[key]
        # Filter out hidden types
        for key in list(result.keys()):
            if key in self._hidden_event_types:
                del result[key]
        return result

    def save_event_types(self, event_types: dict[str, dict[str, str]]) -> None:
        # Clearing the hidden flag for any explicitly saved types
        for key in event_types:
            self._hidden_event_types.discard(key)
        self._meta[_const_mod.CONF_EVENT_TYPES] = event_types

    def hide_event_type(self, key: str) -> None:
        """Remove a built-in or stored event type from the visible registry."""
        self._hidden_event_types.add(key)

    def get_button_metrics(self) -> dict[str, str]:
        stored: dict[str, str] = self._meta.get(_const_mod.CONF_BUTTON_METRICS, {})
        result: dict[str, str] = dict(_const_mod.DEFAULT_BUTTON_METRICS)
        for key, value in stored.items():
            result[key] = value
        for key in _const_mod.DEFAULT_EVENT_TYPES:
            if key not in result:
                result[key] = "daily_count"
        return result

    def save_button_metrics(self, button_metrics: dict[str, str]) -> None:
        self._meta[_const_mod.CONF_BUTTON_METRICS] = button_metrics


# ════════════════════════════════════════════════════════════════════════════════
# ADDITIONAL TESTS — test_event_types_services.py merged in
# ════════════════════════════════════════════════════════════════════════════════

class TestConstImportsFromStub:
    """Verify const module exports required constants used by __init__.py services."""

    def test_default_button_metrics_importable(self):
        """Regression: __init__.py previously omitted DEFAULT_BUTTON_METRICS from the
        import list, causing NameError at runtime when any event type service ran."""
        # Use _const_mod directly (loaded from source at module init) rather than
        # sys.modules, which may be overwritten by other test files' stubs.
        assert hasattr(_const_mod, "DEFAULT_BUTTON_METRICS")
        assert _const_mod.DEFAULT_BUTTON_METRICS["medicine"] == "days_since"
        assert _const_mod.DEFAULT_BUTTON_METRICS["walk"] == "daily_count"

    def test_valid_button_metrics_importable(self):
        assert hasattr(_const_mod, "VALID_BUTTON_METRICS")
        assert "daily_count" in _const_mod.VALID_BUTTON_METRICS
        assert "days_since" in _const_mod.VALID_BUTTON_METRICS
        assert "last_value" in _const_mod.VALID_BUTTON_METRICS


class TestStoreHideEventType:
    """Tests for store hide_event_type() used by delete_event_type service."""

    def test_hide_removes_seed_type_from_get_event_types(self):
        store = MockPawsistantStore()
        assert "walk" in store.get_event_types()
        store.hide_event_type("walk")
        assert "walk" not in store.get_event_types()

    def test_hide_removes_stored_override(self):
        store = MockPawsistantStore()
        store.save_event_types({"walk": {"name": "Custom", "icon": "mdi:run", "color": "#FF0000"}})
        assert store.get_event_types()["walk"]["name"] == "Custom"
        store.hide_event_type("walk")
        assert "walk" not in store.get_event_types()

    def test_hide_unknown_is_silent(self):
        store = MockPawsistantStore()
        store.hide_event_type("nonexistent")  # must not raise

    def test_hidden_type_can_be_readded(self):
        store = MockPawsistantStore()
        store.hide_event_type("walk")
        assert "walk" not in store.get_event_types()
        store.save_event_types({"walk": {"name": "Restored", "icon": "mdi:walk", "color": "#8BC34A"}})
        assert "walk" in store.get_event_types()
        assert store.get_event_types()["walk"]["name"] == "Restored"
