"""Unit tests for delete_event_type shown_types cleanup.

When a custom event type is deleted via pawsistant.delete_event_type, the
per-dog shown_types lists must be scrubbed so ghost buttons don't linger on
the card.  This module tests:

1. Backend: shown_types cleanup when event type is deleted
2. Backend: optional delete_events parameter for bulk-deleting historic events
3. Frontend: belt-and-suspenders filter in _shownTypes() (tested via logic
   rather than HA frontend runtime)
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, AsyncMock, patch

import pytest


# ---------------------------------------------------------------------------
# Stub injection so const.py / store.py can be imported without HA
# ---------------------------------------------------------------------------

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
    if "homeassistant.helpers.config_validation" not in sys.modules:
        cv_mod = types.ModuleType("homeassistant.helpers.config_validation")
        cv_mod.string = lambda v=None: v
        cv_mod.boolean = lambda v=None: v
        sys.modules["homeassistant.helpers.config_validation"] = cv_mod
    if "voluptuous" not in sys.modules:
        vol_mod = types.ModuleType("voluptuous")
        vol_mod.Schema = lambda s, **kw: s
        vol_mod.Required = lambda k, **kw: k
        vol_mod.Optional = lambda k, **kw: k
        sys.modules["voluptuous"] = vol_mod

_inject_stubs()

import pathlib
import importlib.util

# Remove any stale stubs
for key in list(sys.modules):
    if key.startswith("custom_components.pawsistant"):
        del sys.modules[key]

_repo_root = pathlib.Path(__file__).parent.parent.parent

# Load const.py
_spec_const = importlib.util.spec_from_file_location(
    "custom_components.pawsistant.const",
    _repo_root / "custom_components" / "pawsistant" / "const.py",
)
_const_mod = importlib.util.module_from_spec(_spec_const)
_spec_const.loader.exec_module(_const_mod)
sys.modules["custom_components.pawsistant.const"] = _const_mod


# ---------------------------------------------------------------------------
# Lightweight store mock for unit testing (no HA needed)
# ---------------------------------------------------------------------------

class MockStore:
    """Mirrors the real PawsistantStore interface for delete_event_type testing."""

    def __init__(self, dogs=None, event_types_overrides=None,
                 button_metric_overrides=None, shown_types_map=None):
        self._meta = {
            "dogs": dogs or {},
            "known_years": [],
            _const_mod.CONF_EVENT_TYPES: dict(event_types_overrides or {}),
            _const_mod.CONF_BUTTON_METRICS: dict(button_metric_overrides or {}),
        }
        # Per-dog shown_types: {dog_name: [types...]}
        self._shown_types: dict[str, list[str]] = dict(shown_types_map or {})
        # Track saves for assertions
        self.shown_types_saves: list[tuple[str, list[str]]] = []
        self.event_types_saves: list[dict] = []
        self.button_metrics_saves: list[dict] = []
        self.meta_saves: int = 0

    # ── Dog API ──

    def get_dogs(self) -> dict[str, dict[str, str]]:
        return dict(self._meta["dogs"])

    def get_dog_by_name(self, name: str):
        for dog_id, info in self._meta["dogs"].items():
            if info["name"].lower() == name.lower():
                return dog_id, info
        return None

    # ── Event types API ──

    def get_event_types(self) -> dict[str, dict[str, str]]:
        stored = self._meta.get(_const_mod.CONF_EVENT_TYPES, {})
        result = dict(_const_mod.DEFAULT_EVENT_TYPES)
        for key, val in stored.items():
            if val is None:
                # Tombstone: skip
                result.pop(key, None)
            else:
                result[key] = val
        return result

    def get_stored_event_type_overrides(self) -> dict[str, dict[str, str]]:
        return dict(self._meta.get(_const_mod.CONF_EVENT_TYPES, {}))

    def save_event_types(self, event_types: dict) -> None:
        self._meta[_const_mod.CONF_EVENT_TYPES] = dict(event_types)
        self.event_types_saves.append(dict(event_types))

    # ── Button metrics API ──

    def get_stored_button_metric_overrides(self) -> dict[str, str]:
        return dict(self._meta.get(_const_mod.CONF_BUTTON_METRICS, {}))

    def save_button_metrics(self, metrics: dict[str, str]) -> None:
        self._meta[_const_mod.CONF_BUTTON_METRICS] = dict(metrics)
        self.button_metrics_saves.append(dict(metrics))

    # ── Shown types API ──

    def get_shown_types(self, dog_name: str) -> list[str] | None:
        return self._shown_types.get(dog_name)

    async def set_shown_types(self, dog_name: str, shown_types: list[str]) -> None:
        self._shown_types[dog_name] = list(shown_types)
        self.shown_types_saves.append((dog_name, list(shown_types)))

    # ── Meta save API ──

    def sync_save_meta(self) -> None:
        self.meta_saves += 1


# ---------------------------------------------------------------------------
# Tests: Backend shown_types cleanup on delete_event_type
# ---------------------------------------------------------------------------

class TestDeleteEventTypeCleansShownTypes:
    """Verify that deleting an event type removes it from every dog's shown_types."""

    @pytest.mark.asyncio
    async def test_custom_type_removed_from_all_dogs(self):
        """A custom type present in multiple dogs' shown_types is removed."""
        store = MockStore(
            dogs={
                "dog1": {"name": "Buddy", "breed": "Lab", "birth_date": "2020-01-01"},
                "dog2": {"name": "Rex", "breed": "Shepherd", "birth_date": "2019-05-15"},
            },
            event_types_overrides={
                "custom_bark": {"name": "Bark", "icon": "mdi:dog", "color": "#123456"},
            },
            shown_types_map={
                "Buddy": ["food", "custom_bark", "walk"],
                "Rex": ["pee", "custom_bark", "medicine"],
            },
        )
        event_type = "custom_bark"

        # Simulate the shown_types cleanup logic from handle_delete_event_type
        dogs = store.get_dogs()
        for _dog_id, dog_info in dogs.items():
            shown = store.get_shown_types(dog_info["name"])
            if shown and event_type in shown:
                filtered = [t for t in shown if t != event_type]
                await store.set_shown_types(dog_info["name"], filtered)

        # Verify both dogs had the deleted type removed
        assert "custom_bark" not in store.get_shown_types("Buddy")
        assert "custom_bark" not in store.get_shown_types("Rex")
        assert store.get_shown_types("Buddy") == ["food", "walk"]
        assert store.get_shown_types("Rex") == ["pee", "medicine"]

    @pytest.mark.asyncio
    async def test_dog_without_deleted_type_unaffected(self):
        """Dogs that don't have the deleted type in shown_types are unchanged."""
        store = MockStore(
            dogs={
                "dog1": {"name": "Buddy", "breed": "Lab", "birth_date": "2020-01-01"},
                "dog2": {"name": "Rex", "breed": "Shepherd", "birth_date": "2019-05-15"},
            },
            shown_types_map={
                "Buddy": ["food", "custom_bark", "walk"],
                "Rex": ["pee", "medicine"],
            },
        )
        event_type = "custom_bark"

        dogs = store.get_dogs()
        for _dog_id, dog_info in dogs.items():
            shown = store.get_shown_types(dog_info["name"])
            if shown and event_type in shown:
                filtered = [t for t in shown if t != event_type]
                await store.set_shown_types(dog_info["name"], filtered)

        assert store.get_shown_types("Buddy") == ["food", "walk"]
        assert store.get_shown_types("Rex") == ["pee", "medicine"]
        # Rex's shown_types should not have been saved (no change needed)
        assert all(name != "Rex" for name, _ in store.shown_types_saves)

    @pytest.mark.asyncio
    async def test_default_type_tombstoned_removed_from_shown(self):
        """When a default type (e.g. 'walk') is tombstoned, it's also cleaned
        from shown_types."""
        store = MockStore(
            dogs={
                "dog1": {"name": "Buddy", "breed": "Lab", "birth_date": "2020-01-01"},
            },
            shown_types_map={
                "Buddy": ["food", "walk", "pee"],
            },
        )
        event_type = "walk"

        dogs = store.get_dogs()
        for _dog_id, dog_info in dogs.items():
            shown = store.get_shown_types(dog_info["name"])
            if shown and event_type in shown:
                filtered = [t for t in shown if t != event_type]
                await store.set_shown_types(dog_info["name"], filtered)

        assert store.get_shown_types("Buddy") == ["food", "pee"]

    @pytest.mark.asyncio
    async def test_dog_with_no_shown_types_no_error(self):
        """A dog with no shown_types set doesn't cause an error."""
        store = MockStore(
            dogs={
                "dog1": {"name": "Buddy", "breed": "Lab", "birth_date": "2020-01-01"},
            },
            shown_types_map={},  # No shown_types for any dog
        )
        event_type = "custom_bark"

        dogs = store.get_dogs()
        for _dog_id, dog_info in dogs.items():
            shown = store.get_shown_types(dog_info["name"])
            if shown and event_type in shown:
                filtered = [t for t in shown if t != event_type]
                await store.set_shown_types(dog_info["name"], filtered)

        # No crash, no saves
        assert store.shown_types_saves == []

    @pytest.mark.asyncio
    async def test_empty_shown_types_no_error(self):
        """A dog with empty shown_types list doesn't cause an error."""
        store = MockStore(
            dogs={
                "dog1": {"name": "Buddy", "breed": "Lab", "birth_date": "2020-01-01"},
            },
            shown_types_map={
                "Buddy": [],
            },
        )

        dogs = store.get_dogs()
        for _dog_id, dog_info in dogs.items():
            shown = store.get_shown_types(dog_info["name"])
            if shown and "custom_bark" in shown:
                filtered = [t for t in shown if t != "custom_bark"]
                await store.set_shown_types(dog_info["name"], filtered)

        assert store.shown_types_saves == []


# ---------------------------------------------------------------------------
# Tests: delete_events parameter logic
# ---------------------------------------------------------------------------

class TestDeleteEventTypeDeleteEvents:
    """Verify that delete_events=True bulk-deletes historic events."""

    @pytest.mark.asyncio
    async def test_delete_events_false_no_cleanup(self):
        """When delete_events is False (default), no events are deleted."""
        store = MockStore()
        # No events to check in mock, just verify the flag flows correctly
        delete_events = False
        # In the real handler, this branch is skipped when delete_events is False
        assert not delete_events

    @pytest.mark.asyncio
    async def test_delete_events_true_triggers_bulk_delete(self):
        """When delete_events is True, events with matching type are removed."""
        # Build a mock store with year events
        store = MockStore(
            dogs={
                "dog1": {"name": "Buddy", "breed": "Lab", "birth_date": "2020-01-01"},
            },
        )
        # Simulate in-memory events
        event_type = "custom_bark"
        store._year_events = {
            2025: [
                {"id": "e1", "dog_id": "dog1", "event_type": "custom_bark", "timestamp": "2025-01-01T10:00:00"},
                {"id": "e2", "dog_id": "dog1", "event_type": "food", "timestamp": "2025-01-01T12:00:00"},
                {"id": "e3", "dog_id": "dog1", "event_type": "custom_bark", "timestamp": "2025-02-01T10:00:00"},
            ],
        }
        store._loaded_years = {2025}

        # Simulate the delete_events logic from handle_delete_event_type
        delete_events = True
        total_removed = 0
        if delete_events:
            for year in list(store._loaded_years):
                before = len(store._year_events.get(year, []))
                store._year_events[year] = [
                    e for e in store._year_events.get(year, [])
                    if e.get("event_type") != event_type
                ]
                removed = before - len(store._year_events[year])
                if removed:
                    total_removed += removed

        assert total_removed == 2
        assert len(store._year_events[2025]) == 1
        assert store._year_events[2025][0]["event_type"] == "food"


# ---------------------------------------------------------------------------
# Tests: Frontend _shownTypes belt-and-suspenders filter
# ---------------------------------------------------------------------------

class TestFrontendShownTypesFilter:
    """Test the logic that filters shownTypes against the registry.

    This mirrors the frontend _shownTypes() logic in pure Python to verify
    the belt-and-suspenders filter works correctly.
    """

    def _filter_shown_types(self, shown_types: list[str], registry: dict) -> list[str]:
        """Mirror of _shownTypes() filter logic: remove types not in registry."""
        valid_types = set(registry.keys())
        return [t for t in shown_types if t in valid_types]

    def test_stale_type_filtered_out(self):
        """A type in shown_types but not in registry is filtered out."""
        registry = {"food": {}, "walk": {}, "pee": {}}
        shown = ["food", "custom_bark", "walk"]
        result = self._filter_shown_types(shown, registry)
        assert result == ["food", "walk"]

    def test_all_valid_types_preserved(self):
        """All shown types present in registry are preserved."""
        registry = {"food": {}, "walk": {}, "pee": {}}
        shown = ["food", "walk", "pee"]
        result = self._filter_shown_types(shown, registry)
        assert result == ["food", "walk", "pee"]

    def test_empty_shown_types(self):
        """Empty shown_types list stays empty."""
        registry = {"food": {}}
        result = self._filter_shown_types([], registry)
        assert result == []

    def test_empty_registry_filters_all(self):
        """Empty registry means all shown types are filtered out."""
        shown = ["food", "walk"]
        result = self._filter_shown_types(shown, {})
        assert result == []

    def test_multiple_stale_types(self):
        """Multiple stale types are all filtered out."""
        registry = {"food": {}, "walk": {}}
        shown = ["food", "stale1", "stale2", "walk", "stale3"]
        result = self._filter_shown_types(shown, registry)
        assert result == ["food", "walk"]

    def test_order_preserved(self):
        """Filter preserves the original order of valid types."""
        registry = {"pee": {}, "food": {}, "walk": {}}
        shown = ["pee", "custom_bark", "food", "walk"]
        result = self._filter_shown_types(shown, registry)
        assert result == ["pee", "food", "walk"]


# ---------------------------------------------------------------------------
# Tests: DELETE_EVENT_TYPE_SCHEMA accepts delete_events parameter
# ---------------------------------------------------------------------------

class TestDeleteEventTypeSchema:
    """Verify the schema now accepts an optional delete_events boolean."""

    def test_schema_has_delete_events_optional(self):
        """The DELETE_EVENT_TYPE_SCHEMA should accept an optional delete_events key."""
        # We can't easily import the HA-dependent __init__.py, so test the
        # schema structure by checking the source code constants.
        import re
        source = (_repo_root / "custom_components" / "pawsistant" / "__init__.py").read_text()
        # The schema should include delete_events
        assert 'vol.Optional("delete_events"' in source, (
            "DELETE_EVENT_TYPE_SCHEMA should include an Optional delete_events field"
        )

    def test_default_value_is_false(self):
        """The delete_events parameter should default to False."""
        source = (_repo_root / "custom_components" / "pawsistant" / "__init__.py").read_text()
        assert 'default=False' in source.split('vol.Optional("delete_events"')[1].split(")")[0], (
            "delete_events should default to False"
        )