"""Local JSON storage for DogLog using HA's Store helper.

All dog and event data is persisted to .storage/doglog via HA's atomic Store,
replacing the previous Firebase/pydoglog backend.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY = "doglog"
STORAGE_VERSION = 1

# Event types retained indefinitely (time-series data)
PERSISTENT_EVENT_TYPES = {"weight", "medicine", "vaccine"}

# High-frequency events older than this are pruned on coordinator refresh
DEFAULT_RETENTION_DAYS = 90

# All valid event types
VALID_EVENT_TYPES = {
    "food",
    "treat",
    "water",
    "walk",
    "pee",
    "poop",
    "medicine",
    "weight",
    "vaccine",
    "sleep",
    "grooming",
    "training",
    "teeth_brushing",
    "sick",
}


class DogLogStore:
    """Manage DogLog data in HA's local .storage directory.

    Data shape on disk:
    {
        "version": 1,
        "data": {
            "dogs": {
                "<dog_id>": {"name": "Sharky", "breed": "", "birth_date": ""}
            },
            "events": [
                {
                    "id": "<uuid>",
                    "dog_id": "<dog_id>",
                    "event_type": "pee",
                    "timestamp": "2026-03-18T10:30:00-04:00",
                    "note": "",
                    "value": null
                }
            ]
        }
    }

    Events list is kept newest-first in memory; the Store serialises it as-is.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialise the store (does not load from disk yet)."""
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._data: dict[str, Any] = {"dogs": {}, "events": []}

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    async def load(self) -> None:
        """Load persisted data from disk, initialising an empty store if absent."""
        data = await self._store.async_load()
        if data is None:
            self._data = {"dogs": {}, "events": []}
            _LOGGER.debug("DogLog store not found; initialised empty store")
        else:
            self._data = data
            _LOGGER.debug(
                "Loaded DogLog store: %d dogs, %d events",
                len(self._data.get("dogs", {})),
                len(self._data.get("events", [])),
            )
        # Ensure required keys exist even if file is from an older schema
        self._data.setdefault("dogs", {})
        self._data.setdefault("events", [])

    async def save(self) -> None:
        """Atomically persist current in-memory data to disk."""
        await self._store.async_save(self._data)

    # -------------------------------------------------------------------------
    # Dog management
    # -------------------------------------------------------------------------

    async def add_dog(
        self,
        name: str,
        breed: str = "",
        birth_date: str = "",
    ) -> str:
        """Add a new dog. Returns the generated dog_id (UUID)."""
        dog_id = str(uuid.uuid4())
        self._data["dogs"][dog_id] = {
            "name": name,
            "breed": breed,
            "birth_date": birth_date,
        }
        await self.save()
        _LOGGER.info("Added dog '%s' with id %s", name, dog_id)
        return dog_id

    async def remove_dog(self, dog_id: str) -> bool:
        """Remove a dog and all its events. Returns True if the dog existed."""
        if dog_id not in self._data["dogs"]:
            return False
        name = self._data["dogs"][dog_id].get("name", dog_id)
        del self._data["dogs"][dog_id]
        before = len(self._data["events"])
        self._data["events"] = [
            e for e in self._data["events"] if e["dog_id"] != dog_id
        ]
        removed_events = before - len(self._data["events"])
        await self.save()
        _LOGGER.info(
            "Removed dog '%s' and %d events", name, removed_events
        )
        return True

    def get_dogs(self) -> dict[str, dict[str, str]]:
        """Return all dogs as {dog_id: {name, breed, birth_date}}."""
        return dict(self._data["dogs"])

    def get_dog_by_name(
        self, name: str
    ) -> tuple[str, dict[str, str]] | None:
        """Find a dog by name (case-insensitive).

        Returns (dog_id, dog_dict) or None if not found.
        """
        for dog_id, dog in self._data["dogs"].items():
            if dog["name"].lower() == name.lower():
                return dog_id, dog
        return None

    # -------------------------------------------------------------------------
    # Event management
    # -------------------------------------------------------------------------

    async def add_event(
        self,
        dog_id: str,
        event_type: str,
        note: str = "",
        value: float | None = None,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        """Add a new event and return the created event dict."""
        if timestamp is None:
            timestamp = dt_util.now().isoformat()
        event: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "dog_id": dog_id,
            "event_type": event_type,
            "timestamp": timestamp,
            "note": note,
        }
        if value is not None:
            event["value"] = value
        # Insert at front so events list stays newest-first
        self._data["events"].insert(0, event)
        await self.save()
        return event

    async def delete_event(self, event_id: str) -> bool:
        """Delete an event by ID. Returns True if found and deleted."""
        before = len(self._data["events"])
        self._data["events"] = [
            e for e in self._data["events"] if e["id"] != event_id
        ]
        if len(self._data["events"]) < before:
            await self.save()
            return True
        return False

    async def import_events(self, events: list[dict[str, Any]]) -> int:
        """Bulk-import events from an external source (e.g. Firebase migration).

        Skips events whose ``id`` already exists in the store.
        Assigns a new UUID to any event that lacks an ``id``.
        Returns the number of events actually imported.
        """
        existing_ids: set[str] = {e["id"] for e in self._data["events"]}
        imported = 0
        for raw in events:
            # Normalise: ensure id present
            if not raw.get("id"):
                raw = dict(raw)
                raw["id"] = str(uuid.uuid4())
            if raw["id"] in existing_ids:
                continue
            self._data["events"].append(raw)
            existing_ids.add(raw["id"])
            imported += 1

        if imported > 0:
            # Re-sort newest-first after bulk insert
            self._data["events"].sort(
                key=lambda e: e.get("timestamp", ""), reverse=True
            )
            await self.save()
            _LOGGER.info("Imported %d events", imported)
        return imported

    def get_events(
        self,
        dog_id: str,
        event_type: str | None = None,
        since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Return events for a dog, filtered by type and/or start date.

        Results are in newest-first order (matching in-memory ordering).
        """
        result: list[dict[str, Any]] = []
        for event in self._data["events"]:
            if event.get("dog_id") != dog_id:
                continue
            if event_type is not None and event.get("event_type") != event_type:
                continue
            if since is not None:
                ts = _parse_timestamp(event.get("timestamp", ""))
                if ts < since:
                    continue
            result.append(event)
        return result

    async def prune_old_events(self) -> int:
        """Remove non-persistent events older than the retention window.

        Weight, medicine and vaccine events are never pruned.
        Returns the number of events removed.
        """
        cutoff = dt_util.now() - timedelta(days=DEFAULT_RETENTION_DAYS)
        before = len(self._data["events"])
        self._data["events"] = [
            e
            for e in self._data["events"]
            if e.get("event_type") in PERSISTENT_EVENT_TYPES
            or _parse_timestamp(e.get("timestamp", "")) >= cutoff
        ]
        removed = before - len(self._data["events"])
        if removed > 0:
            _LOGGER.info("Pruned %d old DogLog events (>%d days)", removed, DEFAULT_RETENTION_DAYS)
            await self.save()
        return removed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_timestamp(ts: str) -> datetime:
    """Parse an ISO 8601 timestamp string to a timezone-aware datetime.

    Falls back to datetime.min (UTC) if parsing fails so that malformed
    entries are treated as ancient and pruned safely.
    """
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError, AttributeError):
        return datetime.min.replace(tzinfo=timezone.utc)
