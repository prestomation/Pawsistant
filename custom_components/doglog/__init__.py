"""Pawsistant (DogLog) integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
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
    """Set up Pawsistant from a config entry."""
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

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Bug A fix: Only register the service once across all config entries.
    # The handler looks up the coordinator from the entry's runtime_data,
    # so it works for any entry.
    if not hass.services.has_service(DOMAIN, "log_event"):
        async def handle_log_event(call: ServiceCall) -> None:
            """Handle the doglog.log_event service call."""
            dog_name = call.data["dog"]
            event_type_str = call.data["event_type"]
            note = call.data.get("note", "")
            value = call.data.get("value")

            event_type = EventType.from_name(event_type_str)

            # Bug C fix: Build extra kwargs to pass through to create_event
            extra: dict[str, object] = {}
            if value is not None:
                extra["value"] = value

            # Search all loaded config entries for the matching dog
            target_coordinator: DogLogCoordinator | None = None
            dog_id: str | None = None
            for cfg_entry in hass.config_entries.async_entries(DOMAIN):
                coord = getattr(cfg_entry, "runtime_data", None)
                if not isinstance(coord, DogLogCoordinator):
                    continue
                for dog in coord.dogs:
                    if dog.name.lower() == dog_name.lower():
                        target_coordinator = coord
                        dog_id = dog.id
                        break
                if dog_id is not None:
                    break

            if target_coordinator is None or dog_id is None:
                _LOGGER.error("Dog '%s' not found in any loaded pack", dog_name)
                return

            # Bug B fix: Ensure token is fresh before making the API call
            try:
                await target_coordinator.client.ensure_token()
            except Exception:
                _LOGGER.error("Failed to refresh token for service call")
                return

            # Bug D fix: Persist rotated token after ensure_token
            stored_token = target_coordinator._entry.data["refresh_token"]
            if target_coordinator.client.refresh_token != stored_token:
                hass.config_entries.async_update_entry(
                    target_coordinator._entry,
                    data={
                        **target_coordinator._entry.data,
                        "refresh_token": target_coordinator.client.refresh_token,
                    },
                )

            pack_id = target_coordinator.pack.id
            await target_coordinator.client.create_event(
                pack_id,
                dog_id,
                event_type,
                note,
                dog_name,
                **extra,
            )

            await target_coordinator.async_request_refresh()

        hass.services.async_register(DOMAIN, "log_event", handle_log_event)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Bug A fix: Only remove the service when the last config entry is unloaded
    remaining = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.entry_id != entry.entry_id
    ]
    if not remaining:
        hass.services.async_remove(DOMAIN, "log_event")

    return unload_ok
