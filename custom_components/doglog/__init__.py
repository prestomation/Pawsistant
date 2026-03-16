"""DogLog integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import device_registry as dr
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed

from pydoglog import AsyncDogLogClient
from pydoglog.auth import refresh_id_token
from pydoglog.models import EventType

from .coordinator import DogLogCoordinator

_LOGGER = logging.getLogger(__name__)

DOMAIN = "doglog"
PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up DogLog from a config entry."""
    refresh_token = entry.data["refresh_token"]
    uid = entry.data.get("uid", "")

    try:
        token_data = await hass.async_add_executor_job(
            refresh_id_token, refresh_token
        )
    except Exception as err:
        raise ConfigEntryAuthFailed("Failed to refresh token") from err

    new_refresh_token = token_data.get("refresh_token", refresh_token)

    # Persist rotated refresh token back to config entry
    if new_refresh_token != refresh_token:
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, "refresh_token": new_refresh_token},
        )

    client = AsyncDogLogClient(
        id_token=token_data["id_token"],
        refresh_token=new_refresh_token,
        uid=uid,
    )
    # Prevent the client from writing credentials to disk
    client._save = lambda: None

    packs = await client.get_packs()
    if not packs:
        _LOGGER.error("No packs found for user")
        return False

    dogs = await client.get_dogs()
    if not dogs:
        _LOGGER.error("No dogs found")
        return False

    coordinator = DogLogCoordinator(hass, entry, client, packs[0], dogs)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    # Look up TryFi device for each dog to wire up via_device_id
    # TryFi devices use identifier ("tryfi", <dog_id>)
    dev_reg = dr.async_get(hass)
    coordinator.tryfi_device_ids: dict[str, str | None] = {}
    for dog in dogs:
        # TryFi uses the dog's external ID as its device identifier
        # Search all tryfi devices for one whose name matches this dog
        tryfi_device = dev_reg.async_get_device(identifiers={("tryfi", dog.id)})
        if tryfi_device is None:
            # Fall back: search by name
            for device in dr.async_entries_for_config_entry(
                dev_reg, entry.entry_id
            ):
                pass  # not a tryfi device
            # Search entire registry by name match
            for device in list(dev_reg.devices.values()):
                if (
                    device.manufacturer == "TryFi"
                    and (device.name or "").lower() == dog.name.lower()
                ):
                    tryfi_device = device
                    break
        coordinator.tryfi_device_ids[dog.name] = (
            tryfi_device.id if tryfi_device else None
        )
        if tryfi_device:
            _LOGGER.debug(
                "Linked DogLog dog '%s' to TryFi device %s", dog.name, tryfi_device.id
            )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def handle_log_event(call: ServiceCall) -> None:
        """Handle the doglog.log_event service call."""
        dog_name = call.data["dog"]
        event_type_str = call.data["event_type"]
        note = call.data.get("note", "")
        value = call.data.get("value")

        event_type = EventType.from_name(event_type_str)

        extra = {}
        if value is not None:
            extra["value"] = value

        pack_id = coordinator.pack.id
        dog_id = None
        for dog in coordinator.dogs:
            if dog.name.lower() == dog_name.lower():
                dog_id = dog.id
                break

        if dog_id is None:
            _LOGGER.error("Dog '%s' not found", dog_name)
            return

        await client.create_event(
            pack_id,
            dog_id,
            event_type,
            note,
            dog_name,
        )

        await coordinator.async_request_refresh()

    hass.services.async_register(DOMAIN, "log_event", handle_log_event)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    hass.services.async_remove(DOMAIN, "log_event")
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
