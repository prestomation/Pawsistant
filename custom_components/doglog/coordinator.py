"""DataUpdateCoordinator for DogLog."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from pydoglog import DogLogClient, DogLogAuthError, DogLogAPIError
from pydoglog.auth import refresh_id_token
from pydoglog.models import Dog, DogEvent, Pack

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=5)


class DogLogCoordinator(DataUpdateCoordinator[dict[str, list[DogEvent]]]):
    """Coordinator that fetches DogLog events for all dogs."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: DogLogClient,
        pack: Pack,
        dogs: list[Dog],
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="DogLog",
            update_interval=SCAN_INTERVAL,
        )
        self.client = client
        self.pack = pack
        self.dogs = dogs
        self.entry = entry

    async def _async_update_data(self) -> dict[str, list[DogEvent]]:
        """Fetch events from DogLog API."""
        try:
            self.client.ensure_token()
        except Exception:
            # Token expired, try to refresh
            try:
                token_data = await self.hass.async_add_executor_job(
                    refresh_id_token, self.entry.data["refresh_token"]
                )
                self.client._id_token = token_data["id_token"]
                self.client._token_expiry = token_data.get("expires_at", 0)
            except Exception as err:
                raise ConfigEntryAuthFailed(
                    "Failed to refresh authentication token"
                ) from err

        try:
            events: list[DogEvent] = await self.hass.async_add_executor_job(
                self.client.list_events, self.pack.id, None, 200
            )
        except DogLogAuthError as err:
            raise ConfigEntryAuthFailed(
                "Authentication failed"
            ) from err
        except DogLogAPIError as err:
            raise UpdateFailed(f"Error fetching DogLog data: {err}") from err

        # Group events by dog name
        result: dict[str, list[DogEvent]] = {}
        for dog in self.dogs:
            result[dog.name] = [
                e for e in events if e.pet_name == dog.name or e.pet_id == dog.id
            ]

        return result
