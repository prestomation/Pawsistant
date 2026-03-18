"""DataUpdateCoordinator for DogLog.

Data is read from the local DogLogStore (no network calls).  The coordinator
is refreshed immediately after each service call that mutates data, so sensors
reflect the change within the current HA tick.

Coordinator data shape (preserved from the old Firebase coordinator so that
sensor.py requires minimal changes):

    {
        "<dog_name>": [  # newest-first list of event dicts
            {
                "id": "<uuid>",
                "dog_id": "<dog_id>",
                "event_type": "pee",
                "timestamp": "2026-03-18T10:30:00-04:00",
                "note": "",
                "value": null   # may be absent for non-value events
            },
            ...
        ],
        ...
    }
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .store import DogLogStore

DOMAIN = "doglog"
_LOGGER = logging.getLogger(__name__)


class DogLogCoordinator(DataUpdateCoordinator[dict[str, list[dict[str, Any]]]]):
    """Coordinator that reads DogLog events from the local store.

    Because data is local there is no periodic poll interval — updates happen
    only when a service call explicitly triggers async_request_refresh().
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        store: DogLogStore,
    ) -> None:
        """Initialise the coordinator.

        Args:
            hass: The Home Assistant instance.
            entry: The config entry this coordinator belongs to.
            store: The DogLogStore instance shared across this entry.

        """
        super().__init__(
            hass,
            _LOGGER,
            name="DogLog",
            # No update_interval — data is push-driven (service calls trigger refresh)
        )
        self.store = store
        self._entry = entry

    # ------------------------------------------------------------------
    # DataUpdateCoordinator implementation
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict[str, list[dict[str, Any]]]:
        """Build coordinator data from the local store.

        Runs event pruning here so stale entries are cleaned up on every
        reload (at most once per coordinator refresh, which is infrequent).
        """
        try:
            await self.store.prune_old_events()
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Failed to prune old events: %s", err)

        dogs = self.store.get_dogs()
        result: dict[str, list[dict[str, Any]]] = {}
        for dog_id, dog_info in dogs.items():
            dog_name = dog_info["name"]
            result[dog_name] = self.store.get_events(dog_id)
        return result

    # ------------------------------------------------------------------
    # Device registry helpers
    # ------------------------------------------------------------------

    def get_device_info(self, dog_id: str, dog_name: str) -> DeviceInfo:
        """Return DeviceInfo for a dog (used by sensor entities)."""
        return DeviceInfo(
            identifiers={(DOMAIN, dog_id)},
            name=dog_name,
            manufacturer="DogLog",
            model="Dog",
        )
