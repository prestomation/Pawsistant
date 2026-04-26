"""Unit tests for PawsistantStore.get_all_events()."""
from __future__ import annotations

import sys
import types
import pathlib
import importlib.util
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

# ---------------------------------------------------------------------------
# HA stubs (same pattern as other unit tests in this directory)
# ---------------------------------------------------------------------------

def _inject_stubs() -> None:
    if "homeassistant" not in sys.modules:
        sys.modules["homeassistant"] = types.ModuleType("homeassistant")
    if "homeassistant.core" not in sys.modules:
        sys.modules["homeassistant.core"] = types.ModuleType("homeassistant.core")
    if "homeassistant.helpers" not in sys.modules:
        sys.modules["homeassistant.helpers"] = types.ModuleType("homeassistant.helpers")
    if "homeassistant.helpers.storage" not in sys.modules:
        storage_mod = types.ModuleType("homeassistant.helpers.storage")
        storage_mod.Store = MagicMock
        sys.modules["homeassistant.helpers.storage"] = storage_mod
    if "homeassistant.util" not in sys.modules:
        sys.modules["homeassistant.util"] = types.ModuleType("homeassistant.util")
    if "homeassistant.util.dt" not in sys.modules:
        dt_mod = types.ModuleType("homeassistant.util.dt")
        dt_mod.now = lambda tz=None: datetime.now(tz or timezone.utc)
        sys.modules["homeassistant.util.dt"] = dt_mod


_inject_stubs()

# Remove stale stubs so importlib loads from disk
for key in list(sys.modules):
    if key == "custom_components.pawsistant" or key.startswith("custom_components.pawsistant."):
        del sys.modules[key]

_repo_root = pathlib.Path(__file__).parent.parent.parent

_spec_const = importlib.util.spec_from_file_location(
    "custom_components.pawsistant.const",
    _repo_root / "custom_components" / "pawsistant" / "const.py",
)
_const_mod = importlib.util.module_from_spec(_spec_const)
_spec_const.loader.exec_module(_const_mod)
sys.modules["custom_components.pawsistant.const"] = _const_mod

_spec_store = importlib.util.spec_from_file_location(
    "custom_components.pawsistant.store",
    _repo_root / "custom_components" / "pawsistant" / "store.py",
)
_store_mod = importlib.util.module_from_spec(_spec_store)
_spec_store.loader.exec_module(_store_mod)
sys.modules["custom_components.pawsistant.store"] = _store_mod

PawsistantStore = _store_mod.PawsistantStore

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_store(years: list[int] | None = None, loaded: set[int] | None = None):
    """Create a PawsistantStore with pre-populated in-memory data."""
    s = PawsistantStore.__new__(PawsistantStore)
    s._hass = MagicMock()
    known = years or []
    s._meta = {"known_years": list(known), "event_types": {}, "button_metrics": {}}
    s._loaded_years = set(loaded) if loaded is not None else set(known)
    s._year_events = {y: [] for y in (years or [])}
    s._year_stores = {}
    return s


def _add(store, year, event_id, timestamp, dog_id="dog1", event_type="walk", note=""):
    ev = {
        "id": event_id,
        "dog_id": dog_id,
        "event_type": event_type,
        "timestamp": timestamp,
        "note": note,
    }
    store._year_events.setdefault(year, []).append(ev)
    return ev


# ---------------------------------------------------------------------------
# Tests for get_all_events
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_all_events_basic():
    """Returns all events for a dog across multiple years."""
    store = _make_store([2024, 2025, 2026])
    _add(store, 2024, "e1", "2024-06-01T10:00:00+00:00")
    _add(store, 2025, "e2", "2025-03-15T08:00:00+00:00")
    _add(store, 2026, "e3", "2026-01-10T12:00:00+00:00")

    store._ensure_year_loaded = AsyncMock()

    result = await store.get_all_events("dog1")

    assert len(result) == 3
    ids = {e["id"] for e in result}
    assert ids == {"e1", "e2", "e3"}
    # _ensure_year_loaded called for each known year
    assert store._ensure_year_loaded.await_count == 3


@pytest.mark.asyncio
async def test_get_all_events_filters_by_dog():
    """Only returns events for the requested dog_id."""
    store = _make_store([2026])
    _add(store, 2026, "e1", "2026-04-01T10:00:00+00:00", dog_id="dog1")
    _add(store, 2026, "e2", "2026-04-02T10:00:00+00:00", dog_id="dog2")

    store._ensure_year_loaded = AsyncMock()

    result = await store.get_all_events("dog1")

    assert len(result) == 1
    assert result[0]["id"] == "e1"


@pytest.mark.asyncio
async def test_get_all_events_filters_by_event_type():
    """Filters by event_type when provided."""
    store = _make_store([2026])
    _add(store, 2026, "e1", "2026-04-01T10:00:00+00:00", event_type="walk")
    _add(store, 2026, "e2", "2026-04-01T11:00:00+00:00", event_type="pee")
    _add(store, 2026, "e3", "2026-04-01T12:00:00+00:00", event_type="walk")

    store._ensure_year_loaded = AsyncMock()

    result = await store.get_all_events("dog1", event_type="walk")

    assert len(result) == 2
    assert all(e["event_type"] == "walk" for e in result)


@pytest.mark.asyncio
async def test_get_all_events_empty():
    """Returns empty list when no events exist for the dog."""
    store = _make_store([2026])
    _add(store, 2026, "e1", "2026-04-01T10:00:00+00:00", dog_id="other_dog")

    store._ensure_year_loaded = AsyncMock()

    result = await store.get_all_events("dog1")

    assert result == []


@pytest.mark.asyncio
async def test_get_all_events_no_known_years():
    """Returns empty list when there are no known years."""
    store = _make_store([])
    store._ensure_year_loaded = AsyncMock()

    result = await store.get_all_events("dog1")

    assert result == []
    store._ensure_year_loaded.assert_not_called()


@pytest.mark.asyncio
async def test_get_all_events_loads_unloaded_years():
    """Ensures _ensure_year_loaded is called for years not yet in memory."""
    store = _make_store(years=[2024, 2025, 2026], loaded=set())

    async def _fake_ensure(year):
        store._loaded_years.add(year)
        if year == 2024:
            store._year_events[2024] = [
                {"id": "old", "dog_id": "dog1", "event_type": "walk",
                 "timestamp": "2024-05-01T10:00:00+00:00", "note": ""}
            ]

    store._ensure_year_loaded = _fake_ensure

    result = await store.get_all_events("dog1")

    assert len(result) == 1
    assert result[0]["id"] == "old"
