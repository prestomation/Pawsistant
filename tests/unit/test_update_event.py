"""Unit tests for PawsistantStore.update_event()."""
from __future__ import annotations

import sys
import types
import pathlib
import importlib.util
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

# Inject HA stubs
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
        storage_mod.Store = MagicMock
        sys.modules["homeassistant.helpers.storage"] = storage_mod
    if "homeassistant.util" not in sys.modules:
        util_mod = types.ModuleType("homeassistant.util")
        sys.modules["homeassistant.util"] = util_mod
    if "homeassistant.util.dt" not in sys.modules:
        dt_mod = types.ModuleType("homeassistant.util.dt")
        # Provide a now() that returns UTC-aware datetime
        dt_mod.now = lambda tz=None: datetime.now(tz or timezone.utc)
        dt_util_mod = dt_mod
        sys.modules["homeassistant.util.dt"] = dt_mod

_inject_stubs()

# Remove stale stubs so importlib loads from disk
for key in list(sys.modules):
    if key == "custom_components.pawsistant" or key.startswith("custom_components.pawsistant."):
        del sys.modules[key]

# Load const.py from real source
_repo_root = pathlib.Path(__file__).parent.parent.parent
_spec = importlib.util.spec_from_file_location(
    "custom_components.pawsistant.const",
    _repo_root / "custom_components" / "pawsistant" / "const.py"
)
_const_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_const_mod)
sys.modules["custom_components.pawsistant.const"] = _const_mod

# Load store.py from real source
_spec_store = importlib.util.spec_from_file_location(
    "custom_components.pawsistant.store",
    _repo_root / "custom_components" / "pawsistant" / "store.py"
)
_store_mod = importlib.util.module_from_spec(_spec_store)
_spec_store.loader.exec_module(_store_mod)
sys.modules["custom_components.pawsistant.store"] = _store_mod

PawsistantStore = _store_mod.PawsistantStore


def _parse_timestamp(s):
    """Parse ISO timestamp — mirrors store's internal helper."""
    if not s:
        return datetime(2000, 1, 1, tzinfo=timezone.utc)
    s = s.replace("Z", "+00:00")
    return datetime.fromisoformat(s)


import pytest


def _make_store():
    """Create a PawsistantStore with in-memory data (no HA hass object needed)."""
    s = PawsistantStore.__new__(PawsistantStore)
    s._hass = MagicMock()
    s._meta = {"known_years": [2025, 2026], "event_types": {}, "button_metrics": {}}
    s._loaded_years = {2025, 2026}
    s._year_events = {
        2025: [],
        2026: [],
    }
    s._year_stores = {}
    return s


def _add_event(store, year, event_id, timestamp, note="", event_type="walk", dog_id="dog1", value=None):
    """Helper to insert an event into a year file."""
    ev = {"id": event_id, "dog_id": dog_id, "event_type": event_type, "timestamp": timestamp, "note": note}
    if value is not None:
        ev["value"] = value
    store._year_events[year].append(ev)
    return ev


@pytest.mark.asyncio
async def test_update_note():
    """Update only the note field."""
    store = _make_store()
    _add_event(store, 2026, "ev1", "2026-04-22T10:00:00+00:00", note="old note")

    store._save_year = AsyncMock()
    store._save_meta = AsyncMock()
    store._ensure_year_loaded = AsyncMock()

    result = await store.update_event("ev1", note="new note")

    assert result is not None
    assert result["note"] == "new note"
    assert result["timestamp"] == "2026-04-22T10:00:00+00:00"
    store._save_year.assert_awaited_once_with(2026)


@pytest.mark.asyncio
async def test_update_timestamp_same_year():
    """Update timestamp within the same year."""
    store = _make_store()
    _add_event(store, 2026, "ev2", "2026-04-22T10:00:00+00:00", note="test")

    store._save_year = AsyncMock()
    store._save_meta = AsyncMock()
    store._ensure_year_loaded = AsyncMock()

    result = await store.update_event("ev2", timestamp="2026-04-22T14:00:00+00:00")

    assert result is not None
    assert result["timestamp"] == "2026-04-22T14:00:00+00:00"
    assert result["note"] == "test"
    store._save_year.assert_awaited_once_with(2026)


@pytest.mark.asyncio
async def test_update_timestamp_cross_year():
    """Move event from 2026 to 2025 by changing timestamp."""
    store = _make_store()
    _add_event(store, 2026, "ev3", "2026-01-01T10:00:00+00:00", note="cross year")

    store._save_year = AsyncMock()
    store._save_meta = AsyncMock()
    store._ensure_year_loaded = AsyncMock()
    store._record_year = MagicMock()

    result = await store.update_event("ev3", timestamp="2025-12-31T10:00:00+00:00")

    assert result is not None
    assert result["timestamp"] == "2025-12-31T10:00:00+00:00"
    # Event should be removed from 2026
    assert not any(e["id"] == "ev3" for e in store._year_events[2026])
    # Event should be added to 2025
    assert any(e["id"] == "ev3" for e in store._year_events[2025])
    # Both year files saved
    store._save_year.assert_any_call(2026)
    store._save_year.assert_any_call(2025)


@pytest.mark.asyncio
async def test_update_not_found():
    """Return None when event_id doesn't exist."""
    store = _make_store()
    store._save_year = AsyncMock()
    store._ensure_year_loaded = AsyncMock()

    result = await store.update_event("nonexistent", note="nothing")
    assert result is None


@pytest.mark.asyncio
async def test_update_value():
    """Update the value field (for weight events)."""
    store = _make_store()
    _add_event(store, 2026, "ev4", "2026-04-22T10:00:00+00:00", event_type="weight", value=45.0)

    store._save_year = AsyncMock()
    store._save_meta = AsyncMock()
    store._ensure_year_loaded = AsyncMock()

    result = await store.update_event("ev4", value=47.5)

    assert result is not None
    assert result["value"] == 47.5