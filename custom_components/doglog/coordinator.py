"""DataUpdateCoordinator for DogLog."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from pydoglog import AsyncDogLogClient, DogLogAuthError, DogLogAPIError
from pydoglog.models import Dog, DogEvent, Pack

DOMAIN = "doglog"

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=5)


class DogLogCoordinator(DataUpdateCoordinator[dict[str, list[DogEvent]]]):
    """Coordinator that fetches DogLog events for all dogs."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: AsyncDogLogClient,
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
        self._entry = entry
        self.tryfi_identifiers: dict[str, tuple[str, str] | None] = {}

    def get_device_info(self, dog: Dog) -> DeviceInfo:
        """Return DeviceInfo for a dog."""
        return DeviceInfo(
            identifiers={(DOMAIN, dog.id)},
            name=dog.name,
            manufacturer="DogLog",
            model="Dog",
        )

    async def _async_update_data(self) -> dict[str, list[DogEvent]]:
        """Fetch events from DogLog API."""
        old_refresh_token = self.client.refresh_token

        try:
            await self.client.ensure_token()
        except DogLogAuthError as err:
            raise ConfigEntryAuthFailed(
                "Failed to refresh authentication token"
            ) from err

        # Persist new refresh token to config entry if it changed
        if self.client.refresh_token != old_refresh_token:
            self.hass.config_entries.async_update_entry(
                self._entry,
                data={**self._entry.data, "refresh_token": self.client.refresh_token},
            )

        # Lazily resolve TryFi device identifiers (TryFi may not be loaded at our setup time)
        if not all(self.tryfi_identifiers.get(dog.name) for dog in self.dogs):
            dev_reg = dr.async_get(self.hass)
            for dog in self.dogs:
                if self.tryfi_identifiers.get(dog.name):
                    continue
                for device in dev_reg.devices.values():
                    if (
                        device.manufacturer == "TryFi"
                        and (device.name or "").lower() == dog.name.lower()
                    ):
                        tryfi_id = next(
                            (i[1] for i in device.identifiers if i[0] == "tryfi"),
                            None,
                        )
                        if tryfi_id:
                            self.tryfi_identifiers[dog.name] = ("tryfi", tryfi_id)
                            _LOGGER.debug(
                                "Linked DogLog '%s' → TryFi device %s", dog.name, device.id
                            )
                        break

        try:
            events: list[DogEvent] = await self.client.list_events(
                self.pack.id, None, 200
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
