"""DogLog integration for Home Assistant.

All dog and event data is stored locally in HA's .storage directory using a
year-partitioned layout — no cloud dependency required.

Storage files:
  .storage/doglog                   — dogs registry + known_years index
  .storage/doglog_events_YYYY       — events for each calendar year

Services:
  doglog.log_event      — Log an activity for a named dog
  doglog.delete_event   — Delete an event by ID
  doglog.add_dog        — Register a new dog
  doglog.remove_dog     — Remove a dog and all its events
  doglog.list_events    — Fire a HA event with query results (for automations)
  doglog.import_events  — Bulk-import events from a JSON array (Firebase migration)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CoreState, EVENT_HOMEASSISTANT_STARTED, HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .coordinator import DogLogCoordinator
from .store import DogLogStore, VALID_EVENT_TYPES

_LOGGER = logging.getLogger(__name__)

DOMAIN = "doglog"
PLATFORMS = ["sensor"]
URL_BASE = "/doglog"
CARD_VERSION = "2.1.1"

# ---------------------------------------------------------------------------
# Service schemas
# ---------------------------------------------------------------------------

LOG_EVENT_SCHEMA = vol.Schema(
    {
        vol.Required("dog"): cv.string,
        vol.Required("event_type"): vol.In(VALID_EVENT_TYPES),
        vol.Optional("note", default=""): cv.string,
        vol.Optional("value"): vol.Coerce(float),
        vol.Optional("timestamp"): cv.string,
    }
)

DELETE_EVENT_SCHEMA = vol.Schema(
    {
        vol.Required("event_id"): cv.string,
    }
)

ADD_DOG_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
        vol.Optional("breed", default=""): cv.string,
        vol.Optional("birth_date", default=""): cv.string,
    }
)

REMOVE_DOG_SCHEMA = vol.Schema(
    {
        vol.Required("dog"): cv.string,
    }
)

LIST_EVENTS_SCHEMA = vol.Schema(
    {
        vol.Required("dog"): cv.string,
        vol.Optional("event_type"): vol.In(VALID_EVENT_TYPES),
        vol.Optional("days", default=7): vol.All(int, vol.Range(min=1, max=3650)),
    }
)

IMPORT_EVENTS_SCHEMA = vol.Schema(
    {
        vol.Required("events"): list,
    }
)


# ---------------------------------------------------------------------------
# Frontend registration helpers
# ---------------------------------------------------------------------------


class PawsistantCardRegistration:
    """Handles registering the Pawsistant card as a Lovelace resource."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    @property
    def _resource_mode(self) -> str:
        """Return the Lovelace resource mode (HA 2026+ uses resource_mode)."""
        lovelace = self.hass.data.get("lovelace")
        if lovelace is None:
            return "yaml"
        # HA 2026.2+ uses resource_mode attribute
        if hasattr(lovelace, "resource_mode"):
            return lovelace.resource_mode
        # HA 2025.x used mode
        if hasattr(lovelace, "mode"):
            return lovelace.mode
        return "yaml"

    @property
    def _resources(self):
        lovelace = self.hass.data.get("lovelace")
        if lovelace is None:
            return None
        if hasattr(lovelace, "resources"):
            return lovelace.resources
        return None

    async def async_register(self) -> None:
        """Register static path and add to Lovelace resources."""
        await self._register_static_path()
        if self._resource_mode == "storage":
            await self._ensure_resources_loaded()
            await self._register_lovelace_resource()

    async def _register_static_path(self) -> None:
        frontend_dir = Path(__file__).parent / "frontend"
        try:
            await self.hass.http.async_register_static_paths(
                [StaticPathConfig(URL_BASE, str(frontend_dir), False)]
            )
            _LOGGER.debug("Registered static path %s -> %s", URL_BASE, frontend_dir)
        except RuntimeError:
            _LOGGER.debug("Static path %s already registered", URL_BASE)

    async def _ensure_resources_loaded(self) -> None:
        resources = self._resources
        if resources and not resources.loaded:
            await resources.async_load()

    async def _register_lovelace_resource(self) -> None:
        resources = self._resources
        if resources is None:
            return
        card_url = f"{URL_BASE}/pawsistant-card.js?v={CARD_VERSION}"
        existing = [r for r in resources.async_items() if URL_BASE in r.get("url", "")]
        if not existing:
            await resources.async_create_item({"res_type": "module", "url": card_url})
            _LOGGER.info("Auto-registered Pawsistant card resource: %s", card_url)
        else:
            for r in existing:
                if r.get("url") != card_url:
                    try:
                        await resources.async_update_item(
                            r["id"], {"res_type": "module", "url": card_url}
                        )
                        _LOGGER.info("Updated Pawsistant card resource to %s", card_url)
                    except Exception:  # noqa: BLE001
                        pass

    async def async_unregister(self) -> None:
        """Remove the card from Lovelace resources on unload."""
        if self._resource_mode != "storage":
            return
        resources = self._resources
        if resources is None:
            return
        to_remove = [r for r in resources.async_items() if URL_BASE in r.get("url", "")]
        for r in to_remove:
            try:
                await resources.async_delete_item(r["id"])
            except Exception:  # noqa: BLE001
                pass


async def _ensure_frontend_registered(hass: HomeAssistant) -> None:
    """Register frontend resources, deferring if HA hasn't fully started yet."""
    reg = PawsistantCardRegistration(hass)

    async def _do_register(_event=None) -> None:
        await reg.async_register()

    if hass.state == CoreState.running:
        await _do_register()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _do_register)


# ---------------------------------------------------------------------------
# Frontend registration (also called from async_setup for clean startup)
# ---------------------------------------------------------------------------


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register the Pawsistant Lovelace card at integration load time."""
    await _ensure_frontend_registered(hass)
    return True


# ---------------------------------------------------------------------------
# Integration setup
# ---------------------------------------------------------------------------


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up DogLog from a config entry.

    Creates the DogLogStore, loads data from disk, and registers all services.
    On first run (no dogs in store) the initial dog from the config-flow data
    is automatically added.
    """
    # Register frontend resources (safe to call multiple times due to guard)
    await _ensure_frontend_registered(hass)

    store = DogLogStore(hass)
    await store.load()

    # Seed the store with the initial dog captured during config flow
    if not store.get_dogs():
        initial_dog = entry.data.get("initial_dog", {})
        dog_name = initial_dog.get("name", "")
        if dog_name:
            await store.add_dog(
                name=dog_name,
                breed=initial_dog.get("breed", ""),
                birth_date=initial_dog.get("birth_date", ""),
            )
            _LOGGER.info("Created initial dog '%s' from config entry", dog_name)

    coordinator = DogLogCoordinator(hass, entry, store)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # ------------------------------------------------------------------
    # Register services — only once, regardless of how many entries exist
    # (In practice there is always exactly one entry, but guard anyway.)
    # ------------------------------------------------------------------

    def _get_store_and_coord() -> tuple[DogLogStore, DogLogCoordinator]:
        """Return the active store and coordinator for the single entry."""
        for cfg_entry in hass.config_entries.async_entries(DOMAIN):
            coord = getattr(cfg_entry, "runtime_data", None)
            if isinstance(coord, DogLogCoordinator):
                return coord.store, coord
        raise RuntimeError("No active DogLog coordinator found")

    def _find_dog_id(store: DogLogStore, dog_name: str) -> str | None:
        """Return the dog_id for *dog_name* (case-insensitive) or None."""
        result = store.get_dog_by_name(dog_name)
        return result[0] if result else None

    if not hass.services.has_service(DOMAIN, "log_event"):

        async def handle_log_event(call: ServiceCall) -> None:
            """Handle doglog.log_event."""
            store, coord = _get_store_and_coord()
            dog_name: str = call.data["dog"]
            event_type: str = call.data["event_type"]
            note: str = call.data.get("note", "")
            value: float | None = call.data.get("value")
            timestamp: str | None = call.data.get("timestamp")

            dog_id = _find_dog_id(store, dog_name)
            if dog_id is None:
                _LOGGER.error("doglog.log_event: dog '%s' not found", dog_name)
                return

            event = await store.add_event(
                dog_id=dog_id,
                event_type=event_type,
                note=note,
                value=value,
                timestamp=timestamp,
            )
            _LOGGER.debug(
                "Logged %s event for '%s' (id=%s)", event_type, dog_name, event["id"]
            )
            await coord.async_request_refresh()

        hass.services.async_register(
            DOMAIN, "log_event", handle_log_event, schema=LOG_EVENT_SCHEMA
        )

    if not hass.services.has_service(DOMAIN, "delete_event"):

        async def handle_delete_event(call: ServiceCall) -> None:
            """Handle doglog.delete_event."""
            store, coord = _get_store_and_coord()
            event_id: str = call.data["event_id"]
            deleted = await store.delete_event(event_id)
            if deleted:
                _LOGGER.debug("Deleted event %s", event_id)
                await coord.async_request_refresh()
            else:
                _LOGGER.warning(
                    "doglog.delete_event: event id '%s' not found", event_id
                )

        hass.services.async_register(
            DOMAIN, "delete_event", handle_delete_event, schema=DELETE_EVENT_SCHEMA
        )

    if not hass.services.has_service(DOMAIN, "add_dog"):

        async def handle_add_dog(call: ServiceCall) -> None:
            """Handle doglog.add_dog."""
            store, coord = _get_store_and_coord()
            name: str = call.data["name"].strip()
            if not name:
                _LOGGER.error("doglog.add_dog: name must not be empty")
                return
            dog_id = await store.add_dog(
                name=name,
                breed=call.data.get("breed", ""),
                birth_date=call.data.get("birth_date", ""),
            )
            _LOGGER.info("Added dog '%s' via service (id=%s)", name, dog_id)
            await coord.async_request_refresh()

        hass.services.async_register(
            DOMAIN, "add_dog", handle_add_dog, schema=ADD_DOG_SCHEMA
        )

    if not hass.services.has_service(DOMAIN, "remove_dog"):

        async def handle_remove_dog(call: ServiceCall) -> None:
            """Handle doglog.remove_dog."""
            store, coord = _get_store_and_coord()
            dog_name: str = call.data["dog"]
            result = store.get_dog_by_name(dog_name)
            if result is None:
                _LOGGER.error(
                    "doglog.remove_dog: dog '%s' not found", dog_name
                )
                return
            dog_id, _ = result
            await store.remove_dog(dog_id)
            _LOGGER.info("Removed dog '%s' via service", dog_name)
            await coord.async_request_refresh()

        hass.services.async_register(
            DOMAIN, "remove_dog", handle_remove_dog, schema=REMOVE_DOG_SCHEMA
        )

    if not hass.services.has_service(DOMAIN, "list_events"):

        async def handle_list_events(call: ServiceCall) -> None:
            """Handle doglog.list_events.

            Fires a ``doglog_events`` HA event containing the matching events so
            that automations can react to the results.  Older year files are
            lazy-loaded by the store as needed.
            """
            from datetime import timedelta
            from homeassistant.util import dt as dt_util

            store, _coord = _get_store_and_coord()
            dog_name: str = call.data["dog"]
            event_type: str | None = call.data.get("event_type")
            days: int = call.data.get("days", 7)

            result = store.get_dog_by_name(dog_name)
            if result is None:
                _LOGGER.error(
                    "doglog.list_events: dog '%s' not found", dog_name
                )
                return
            dog_id, _ = result
            since = dt_util.now() - timedelta(days=days)
            # get_events is async — may lazy-load historical year files
            events = await store.get_events(dog_id, event_type=event_type, since=since)

            hass.bus.async_fire(
                "doglog_events",
                {
                    "dog": dog_name,
                    "event_type": event_type,
                    "days": days,
                    "events": events,
                },
            )

        hass.services.async_register(
            DOMAIN, "list_events", handle_list_events, schema=LIST_EVENTS_SCHEMA
        )

    if not hass.services.has_service(DOMAIN, "import_events"):

        async def handle_import_events(call: ServiceCall) -> None:
            """Handle doglog.import_events.

            Accepts a list of event dicts (e.g. exported from Firebase) and
            bulk-imports them into the local store.  Duplicate IDs are skipped.
            """
            store, coord = _get_store_and_coord()
            raw_events: list[Any] = call.data["events"]
            if not isinstance(raw_events, list):
                _LOGGER.error("doglog.import_events: 'events' must be a list")
                return
            count = await store.import_events(raw_events)
            _LOGGER.info("import_events: imported %d new events", count)
            if count > 0:
                await coord.async_request_refresh()

        hass.services.async_register(
            DOMAIN, "import_events", handle_import_events, schema=IMPORT_EVENTS_SCHEMA
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Remove services only when the last DogLog entry is unloaded
    remaining = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.entry_id != entry.entry_id
    ]
    if not remaining:
        for service in (
            "log_event",
            "delete_event",
            "add_dog",
            "remove_dog",
            "list_events",
            "import_events",
        ):
            hass.services.async_remove(DOMAIN, service)

    return unload_ok
