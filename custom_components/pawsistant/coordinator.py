"""DataUpdateCoordinator for Pawsistant.

Data is read from the local PawsistantStore (no network calls).  The coordinator
is refreshed immediately after each service call that mutates data, so sensors
reflect the change within the current HA tick.

``get_events()`` on the store is now async (it may lazy-load additional year
files), so the coordinator awaits it for every dog on each refresh.

Coordinator data shape (preserved from the old Firebase coordinator so that
sensor.py requires minimal changes):

    {
        "<dog_id>": [  # newest-first list of event dicts
            {
                "id": "<uuid>",
                "dog_id": "<dog_id>",
                "event_type": "pee",
                "timestamp": "2026-03-18T10:30:00-04:00",
                "note": "",
                # "value": 65.2   ← present only for weight/medicine etc.
            },
            ...
        ],
        ...
    }
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
try:
    from homeassistant.helpers.device_registry import DeviceInfo
except ImportError:
    from homeassistant.helpers.entity import DeviceInfo  # type: ignore[no-redef]
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .store import PawsistantStore
_LOGGER = logging.getLogger(__name__)

# Periodic refresh interval — needed so time-based sensors (days_since_medicine,
# daily counts) update even when no service calls fire.
SCAN_INTERVAL = timedelta(minutes=5)


class PawsistantCoordinator(DataUpdateCoordinator[dict[str, list[dict[str, Any]]]]):
    """Coordinator that reads Pawsistant events from the local year-partitioned store."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        store: PawsistantStore,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Pawsistant",
            update_interval=SCAN_INTERVAL,
        )
        self.store = store
        self._entry = entry
        # Track last prune time so pruning only happens once per day
        self._last_prune: datetime | None = None

    async def _async_update_data(self) -> dict[str, list[dict[str, Any]]]:
        """Build coordinator data from the local store."""
        # Only prune once per day, not on every 5-min refresh
        now = datetime.now(tz=timezone.utc)
        if self._last_prune is None or (now - self._last_prune).total_seconds() >= 86400:
            try:
                await self.store.prune_old_events()
                self._last_prune = now
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Pawsistant: failed to prune old events: %s", err)

        dogs = self.store.get_dogs()
        result: dict[str, list[dict[str, Any]]] = {}
        for dog_id, dog_info in dogs.items():
            dog_name = dog_info["name"]
            try:
                result[dog_id] = await self.store.get_events(dog_id)
            except Exception as err:
                raise UpdateFailed(
                    f"Pawsistant: failed to load events for '{dog_name}': {err}"
                ) from err
        return result

    def get_device_info(self, dog_id: str, dog_name: str) -> DeviceInfo:
        """Return DeviceInfo for a dog (used by sensor entities)."""
        return DeviceInfo(
            identifiers={(DOMAIN, dog_id)},
            name=dog_name,
            manufacturer="Pawsistant",
            model="Dog",
        )
