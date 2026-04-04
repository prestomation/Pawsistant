"""Local JSON storage for Pawsistant — year-partitioned design.

Storage layout in HA's .storage directory:

    pawsistant
        Dogs registry + metadata only.  No events.
        Shape:  {"dogs": {dog_id: {name, breed, birth_date}},
                 "known_years": [2025, 2026, ...]}

    pawsistant_events_2025
    pawsistant_events_2026
    ...
        One file per calendar year of event data.
        Shape:  {"events": [{id, dog_id, event_type, timestamp, note, value?}, ...]}
        Events are stored newest-first within each file.

Benefits of partitioning
------------------------
* Routine sensor reads (today's counts, most-recent timestamps) only touch the
  current year's file — typically a few hundred events.
* Historical queries (weight trend, medicine history across years) lazy-load
  older year files on demand.
* Pruning operates per year file, never touching other years.
* Migration: if an old flat store with an "events" key is found on first load,
  events are transparently migrated to year files.

------------------------------
pawsistant files don't, the load() method will attempt to read from the old
keys and write to the new ones.  This ensures existing users don't lose data
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

STORAGE_KEY_META = "pawsistant"
STORAGE_KEY_EVENTS_PREFIX = "pawsistant_events_"
STORAGE_VERSION = 1


# Event types that are retained indefinitely — never pruned
PERSISTENT_EVENT_TYPES = {"weight", "medicine", "vaccine"}

# High-frequency events older than this are pruned per year file.
# Set to 3 years — generous enough for full history but prevents unbounded growth.
DEFAULT_RETENTION_DAYS = 1095

# All valid event types (used for service schema validation)
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
# ---------------------------------------------------------------------------
# PawsistantStore
# ---------------------------------------------------------------------------
class PawsistantStore:
    """Year-partitioned local storage for Pawsistant.

    Usage pattern
    -------------
    1.  ``await store.load()``               — call once at integration setup
    2.  ``await store.get_events(dog_id)``   — coordinator refresh
    3.  ``await store.add_event(...)``        — after service call
    4.  ``await store.prune_old_events()``   — called by coordinator on refresh
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialise (does not touch disk yet — call load() after creation)."""
        self._hass = hass
        self._meta_store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY_META)

        # In-memory meta: dogs dict + known_years list
        self._meta: dict[str, Any] = {"dogs": {}, "known_years": []}

        # year → Store instance (created lazily)
        self._year_stores: dict[int, Store] = {}
        # year → list[event_dict] (newest-first, loaded lazily)
        self._year_events: dict[int, list[dict[str, Any]]] = {}
        # which years have been loaded from disk
        self._loaded_years: set[int] = set()

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _get_year_store(self, year: int) -> Store:
        """Return (or create) the Store for a given year."""
        if year not in self._year_stores:
            self._year_stores[year] = Store(
                self._hass,
                STORAGE_VERSION,
                f"{STORAGE_KEY_EVENTS_PREFIX}{year}",
            )
        return self._year_stores[year]

    async def _ensure_year_loaded(self, year: int) -> None:
        """Load a year's events from disk if not already in memory."""
        if year in self._loaded_years:
            return
        store = self._get_year_store(year)
        raw = await store.async_load()
        if raw is None:
            self._year_events[year] = []
        else:
            self._year_events[year] = raw.get("events", [])
        self._loaded_years.add(year)
        _LOGGER.debug(
            "Loaded year %d: %d events", year, len(self._year_events[year])
        )

    async def _save_year(self, year: int) -> None:
        """Atomically persist a year's events to disk."""
        store = self._get_year_store(year)
        await store.async_save({"events": self._year_events.get(year, [])})

    async def _save_meta(self) -> None:
        """Persist the meta store (dogs + known_years)."""
        await self._meta_store.async_save(self._meta)

    def _record_year(self, year: int) -> None:
        """Add year to the known_years index (no-op if already present)."""
        known: list[int] = self._meta.setdefault("known_years", [])
        if year not in known:
            known.append(year)
            known.sort()

    @staticmethod
    def _year_of_timestamp(timestamp: str | None) -> int:
        """Extract the calendar year from an ISO timestamp string.

        Falls back to the current year if the timestamp is absent/invalid.
        """
        if not timestamp:
            return dt_util.now().year
        year = _parse_timestamp(timestamp).year
        # Sanity-check: reject years outside a plausible range
        current_year = dt_util.now().year
        if year < 2000 or year > current_year + 1:
            return current_year
        return year

    # -----------------------------------------------------------------------
    # -----------------------------------------------------------------------

    # -----------------------------------------------------------------------
    # Migration: flat → partitioned
    # -----------------------------------------------------------------------

    async def _maybe_migrate_flat_events(self) -> None:
        """If the old single-file store contained an 'events' list, migrate it.

        The old store used a single file with both dogs and events.
        This method moves those events into year-partitioned files and removes
        the events key from the meta store.
        """
        flat_events: list[dict[str, Any]] = self._meta.pop("events", [])
        if not flat_events:
            return

        _LOGGER.info(
            "Pawsistant: migrating %d events from flat store to year-partitioned files",
            len(flat_events),
        )

        # Group by year
        by_year: dict[int, list[dict[str, Any]]] = {}
        for event in flat_events:
            year = self._year_of_timestamp(event.get("timestamp"))
            by_year.setdefault(year, []).append(event)

        # Persist each year (merge with anything already on disk)
        for year, year_events in sorted(by_year.items()):
            await self._ensure_year_loaded(year)
            existing_ids = {e["id"] for e in self._year_events[year]}
            added = 0
            for ev in year_events:
                ev = dict(ev)  # always copy to avoid mutating caller's data
                if ev.get("id") and ev["id"] in existing_ids:
                    continue
                if not ev.get("id"):
                    ev["id"] = str(uuid.uuid4())
                self._year_events[year].append(ev)
                existing_ids.add(ev["id"])
                added += 1
            # Re-sort newest-first
            self._year_events[year].sort(
                key=lambda e: e.get("timestamp", ""), reverse=True
            )
            self._record_year(year)
            await self._save_year(year)
            _LOGGER.info(
                "Migration: wrote %d events to pawsistant_events_%d", added, year
            )

        # Save meta without events key
        await self._save_meta()
        _LOGGER.info("Pawsistant flat-store migration complete")

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    async def load(self) -> None:
        """Load meta + current year + previous year from disk.

        Loading two years by default ensures cross-year queries (e.g. "days
        since last medicine" in January) work without extra async calls.

        a one-time migration is performed automatically.
        """
        raw = await self._meta_store.async_load()
        if raw is None:
            if not self._meta.get("dogs"):
                self._meta = {"dogs": {}, "known_years": []}
                _LOGGER.debug("Pawsistant: no existing store found, starting fresh")
        else:
            self._meta = raw
            _LOGGER.debug(
                "Pawsistant: loaded meta — %d dogs, known years: %s",
                len(self._meta.get("dogs", {})),
                self._meta.get("known_years", []),
            )

        # Ensure expected keys present
        self._meta.setdefault("dogs", {})
        self._meta.setdefault("known_years", [])

        # Migrate old flat-event format if present
        if "events" in self._meta:
            await self._maybe_migrate_flat_events()

        # Pre-load current year and previous year
        current_year = dt_util.now().year
        await self._ensure_year_loaded(current_year)
        await self._ensure_year_loaded(current_year - 1)

    # -----------------------------------------------------------------------
    # Dog management
    # -----------------------------------------------------------------------

    async def add_dog(
        self,
        name: str,
        breed: str = "",
        birth_date: str = "",
        species: str = "Dog",
    ) -> str:
        """Register a new dog. Returns the generated dog_id (UUID).

        Raises ValueError if a dog with the same name (case-insensitive) already exists.
        """
        existing = self.get_dog_by_name(name)
        if existing is not None:
            raise ValueError(
                f"Pawsistant: a dog named '{existing[1]['name']}' already exists"
            )

        dog_id = str(uuid.uuid4())
        self._meta["dogs"][dog_id] = {
            "name": name,
            "breed": breed,
            "birth_date": birth_date,
            "species": species or "Dog",
        }
        await self._save_meta()
        _LOGGER.info("Pawsistant: added dog '%s' (id=%s)", name, dog_id)
        return dog_id

    async def remove_dog(self, dog_id: str) -> bool:
        """Remove a dog and all its events across every year file.

        Returns True if the dog existed and was removed.
        """
        if dog_id not in self._meta["dogs"]:
            return False

        name = self._meta["dogs"][dog_id].get("name", dog_id)
        del self._meta["dogs"][dog_id]

        # Ensure all known years are loaded so we can scrub events completely
        for year in self._meta.get("known_years", []):
            await self._ensure_year_loaded(year)

        total_removed = 0
        for year in list(self._loaded_years):
            before = len(self._year_events.get(year, []))
            self._year_events[year] = [
                e
                for e in self._year_events.get(year, [])
                if e.get("dog_id") != dog_id
            ]
            removed = before - len(self._year_events[year])
            if removed:
                total_removed += removed
                await self._save_year(year)

        await self._save_meta()
        _LOGGER.info(
            "Pawsistant: removed dog '%s' and %d events", name, total_removed
        )
        return True

    def get_dogs(self) -> dict[str, dict[str, str]]:
        """Return all dogs as {dog_id: {name, breed, birth_date}}."""
        return dict(self._meta["dogs"])

    def get_dog_by_name(
        self, name: str
    ) -> tuple[str, dict[str, str]] | None:
        """Find a dog by name (case-insensitive).

        Returns ``(dog_id, dog_dict)`` or ``None`` if not found.
        """
        for dog_id, dog in self._meta["dogs"].items():
            if dog["name"].lower() == name.lower():
                return dog_id, dog
        return None

    # -----------------------------------------------------------------------
    # Event management
    # -----------------------------------------------------------------------

    async def add_event(
        self,
        dog_id: str,
        event_type: str,
        note: str = "",
        value: float | None = None,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        """Log a new event.

        The event is written to the year file that matches its timestamp
        (defaulting to the current year when no timestamp is provided).
        Returns the created event dict.
        """
        if timestamp is None:
            timestamp = dt_util.now().isoformat()

        year = self._year_of_timestamp(timestamp)
        await self._ensure_year_loaded(year)
        self._record_year(year)

        event: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "dog_id": dog_id,
            "event_type": event_type,
            "timestamp": timestamp,
            "note": note,
        }
        if value is not None:
            event["value"] = value

        # Insert and re-sort newest-first so backdated events land in the correct position
        self._year_events.setdefault(year, []).append(event)
        self._year_events[year].sort(
            key=lambda e: e.get("timestamp", ""), reverse=True
        )
        await self._save_year(year)

        # Persist updated known_years index if this year was new
        if year not in (self._meta.get("known_years") or []):
            await self._save_meta()

        return event

    async def delete_event(self, event_id: str) -> bool:
        """Delete an event by ID.

        Searches all known year files (loading them if necessary).
        Returns True if found and deleted, False if the event ID does not exist.
        """
        for year in self._meta.get("known_years", []):
            await self._ensure_year_loaded(year)

        for year in sorted(self._loaded_years, reverse=True):
            events = self._year_events.get(year, [])
            new_events = [e for e in events if e.get("id") != event_id]
            if len(new_events) < len(events):
                self._year_events[year] = new_events
                await self._save_year(year)
                _LOGGER.debug("Deleted event %s from year %d", event_id, year)
                return True
        return False

    async def get_events(
        self,
        dog_id: str,
        event_type: str | None = None,
        since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Return events for a dog, optionally filtered by type and start date.

        Year files are lazy-loaded as needed:
        - If ``since`` spans prior years, those year files are loaded on demand.
        - If ``since`` is None, only currently loaded years are searched
          (current year + previous year after ``load()``).

        Results are newest-first.
        """
        current_year = dt_util.now().year

        # Determine which years to search
        if since is not None:
            since_year = since.year
            # Ensure all years from since_year to current_year are in memory
            for year in range(since_year, current_year + 1):
                await self._ensure_year_loaded(year)
            search_years = range(current_year, since_year - 1, -1)
        else:
            # Default: only already-loaded years (current + previous)
            search_years = sorted(self._loaded_years, reverse=True)

        result: list[dict[str, Any]] = []
        for year in search_years:
            if year not in self._loaded_years:
                continue
            for event in self._year_events.get(year, []):
                if event.get("dog_id") != dog_id:
                    continue
                if event_type is not None and event.get("event_type") != event_type:
                    continue
                if since is not None:
                    ts = _parse_timestamp(event.get("timestamp", ""))
                    if ts < since:
                        # Events are newest-first within a year — once we fall
                        # below `since` there are no more matches in this year
                        break
                result.append(event)
        return result

    async def import_events(self, events: list[dict[str, Any]]) -> int:
        """Bulk-import events, partitioning them by year.

        Designed for one-time migration from external sources.  Events whose
        ``id`` already exists in any loaded year are skipped; unrecognised years
        are lazy-loaded from disk before merging.  Entries missing required
        fields (event_type) are skipped with a warning.

        Returns the count of events actually imported.
        """
        if not events:
            return 0

        # Group incoming events by year
        by_year: dict[int, list[dict[str, Any]]] = {}
        for raw in events:
            if not isinstance(raw, dict):
                _LOGGER.warning(
                    "import_events: skipping non-dict entry: %r", raw
                )
                continue
            if not raw.get("event_type"):
                _LOGGER.warning(
                    "import_events: skipping entry missing 'event_type': %r", raw
                )
                continue
            raw = dict(raw)  # don't mutate caller's dicts
            if not raw.get("id"):
                raw["id"] = str(uuid.uuid4())
            year = self._year_of_timestamp(raw.get("timestamp"))
            by_year.setdefault(year, []).append(raw)

        total_imported = 0
        for year, year_batch in sorted(by_year.items()):
            await self._ensure_year_loaded(year)
            self._record_year(year)
            existing_ids: set[str] = {
                e["id"] for e in self._year_events.get(year, [])
            }
            added_this_year = 0
            for ev in year_batch:
                if ev["id"] in existing_ids:
                    continue
                self._year_events.setdefault(year, []).append(ev)
                existing_ids.add(ev["id"])
                added_this_year += 1

            if added_this_year:
                # Re-sort newest-first after bulk insert
                self._year_events[year].sort(
                    key=lambda e: e.get("timestamp", ""), reverse=True
                )
                await self._save_year(year)
                total_imported += added_this_year
                _LOGGER.info(
                    "import_events: added %d events to year %d",
                    added_this_year,
                    year,
                )

        if total_imported:
            await self._save_meta()  # persist any new known_years entries

        return total_imported

    async def prune_old_events(self) -> int:
        """Remove non-persistent events older than the retention window.

        Operates independently on each loaded year file.  Weight, medicine,
        and vaccine events are never pruned — they form the longitudinal
        history that's the core value of Pawsistant.

        Returns the total number of events removed.
        """
        cutoff = dt_util.now() - timedelta(days=DEFAULT_RETENTION_DAYS)
        total_removed = 0

        for year in list(self._loaded_years):
            events = self._year_events.get(year, [])
            if not events:
                continue
            new_events = [
                e
                for e in events
                if e.get("event_type") in PERSISTENT_EVENT_TYPES
                or _parse_timestamp(e.get("timestamp", "")) >= cutoff
            ]
            removed = len(events) - len(new_events)
            if removed:
                self._year_events[year] = new_events
                await self._save_year(year)
                total_removed += removed
                _LOGGER.debug(
                    "Pruned %d old events from year %d", removed, year
                )

        if total_removed:
            _LOGGER.info(
                "Pawsistant: pruned %d events older than %d days",
                total_removed,
                DEFAULT_RETENTION_DAYS,
            )
        return total_removed

    # -----------------------------------------------------------------------
    # Diagnostics
    # -----------------------------------------------------------------------

    def loaded_years(self) -> list[int]:
        """Return the list of currently in-memory years (for diagnostics)."""
        return sorted(self._loaded_years)

    def known_years(self) -> list[int]:
        """Return all years that have ever had data (from the meta index)."""
        return list(self._meta.get("known_years", []))
# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------
def _parse_timestamp(ts: str) -> datetime:
    """Parse an ISO 8601 timestamp string to a timezone-aware datetime.

    Returns ``datetime.min`` (UTC) on failure so that malformed entries are
    treated as ancient and are safely pruned.
    """
    try:
        dt = datetime.fromisoformat(ts)
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError, AttributeError):
        return datetime.min.replace(tzinfo=timezone.utc)
