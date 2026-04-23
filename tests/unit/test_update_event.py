"""Unit tests for PawsistantStore.update_event()."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys

# Ensure HA stubs exist before importing store
if "homeassistant" not in sys.modules:
    sys.modules["homeassistant"] = MagicMock()
    sys.modules["homeassistant.core"] = MagicMock()
    sys.modules["homeassistant.util"] = MagicMock()
    sys.modules["homeassistant.util.dt"] = MagicMock()

from custom_components.pawsistant.store import PawsistantStore


@pytest.fixture
def store():
    """Create a PawsistantStore with in-memory data."""
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
async def test_update_note(store):
    """Update only the note field."""
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
async def test_update_timestamp_same_year(store):
    """Update timestamp within the same year."""
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
async def test_update_timestamp_cross_year(store):
    """Move event from 2026 to 2025 by changing timestamp."""
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
async def test_update_not_found(store):
    """Return None when event_id doesn't exist."""
    store._save_year = AsyncMock()
    store._ensure_year_loaded = AsyncMock()

    result = await store.update_event("nonexistent", note="nothing")
    assert result is None


@pytest.mark.asyncio
async def test_update_value(store):
    """Update the value field (for weight events)."""
    _add_event(store, 2026, "ev4", "2026-04-22T10:00:00+00:00", event_type="weight", value=45.0)

    store._save_year = AsyncMock()
    store._save_meta = AsyncMock()
    store._ensure_year_loaded = AsyncMock()

    result = await store.update_event("ev4", value=47.5)

    assert result is not None
    assert result["value"] == 47.5