"""Diagnostics support for Pawsistant.

Provides a downloadable debug dump via Settings → Devices & Services →
Pawsistant → Download diagnostics.

The dump includes:
- Number of dogs configured
- Event counts per type (totals, not individual events)
- Current sensor states (entity_id → state)
- Storage file sizes (.storage/pawsistant*)
- HA version
- Integration version (from manifest)
- Lovelace card registration state (see ``_card_registration``)

No sensitive data is included since Pawsistant has no cloud auth or credentials.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import CARD_VERSION, DOMAIN, URL_BASE
from .coordinator import PawsistantCoordinator

_LOGGER = logging.getLogger(__name__)

# No fields to redact — Pawsistant is local-only with no credentials or tokens.
TO_REDACT: set[str] = set()


def _card_file_info() -> dict[str, Any]:
    """Return whether the card bundle is on disk, and its size.

    This does file I/O, so run it in an executor job.
    """
    card_file = Path(__file__).parent / "frontend" / "pawsistant-card.js"
    # stat() can still fail after is_file() says yes — a permission error, or the
    # file going away between the two calls. Report -1 rather than crashing the
    # whole diagnostics dump over the least important field in it.
    exists = card_file.is_file()
    try:
        size = card_file.stat().st_size if exists else 0
    except OSError as err:
        _LOGGER.debug("Could not stat %s: %s", card_file, err)
        size = -1
    return {"card_file_exists": exists, "card_file_size": size}


def _storage_file_sizes(config_dir: str) -> dict[str, int]:
    """Return the size of each .storage/pawsistant* file.

    This does file I/O, so run it in an executor job.
    """
    storage_dir = Path(config_dir) / ".storage"
    sizes: dict[str, int] = {}
    if storage_dir.is_dir():
        for path in sorted(storage_dir.glob("pawsistant*")):
            try:
                sizes[path.name] = path.stat().st_size
            except OSError as err:
                _LOGGER.debug("Could not stat %s: %s", path.name, err)
                sizes[path.name] = -1
    return sizes


def _card_registration(
    hass: HomeAssistant, card_file: dict[str, Any]
) -> dict[str, Any]:
    """Report why the Lovelace card is (or isn't) reaching the browser.

    Nearly every "the card doesn't show up" report comes down to one of four
    states, and they are indistinguishable from the outside — so name each one:

    - ``card_file_exists`` false: the built bundle never made it onto disk
      (a source checkout instead of a HACS/zip install).
    - ``resource_mode`` ``"yaml"``: Lovelace is YAML-managed, so we are not
      allowed to self-register; the user must add the resource themselves.
    - ``resource_registered`` false in storage mode: registration genuinely
      failed, and this is our bug.
    - everything true but ``lovelace_dashboards`` empty: the install is fine and
      the user is looking at HA 2026's new Overview (``home``) panel, which is
      not a Lovelace dashboard and loads no custom cards at all.
    """
    info: dict[str, Any] = {
        "card_version": CARD_VERSION,
        "url_base": URL_BASE,
        **card_file,
    }

    lovelace = hass.data.get("lovelace")
    if lovelace is None:
        # The Lovelace component isn't loaded, so there is nothing to register
        # into and no dashboards to enumerate.
        info["resource_mode"] = "unavailable"
        info["resource_registered"] = False
        return info

    mode = getattr(lovelace, "resource_mode", None) or getattr(lovelace, "mode", None)
    info["resource_mode"] = mode or "unknown"

    resources = getattr(lovelace, "resources", None)
    if resources is None:
        info["resource_registered"] = False
    else:
        try:
            ours = [
                r for r in resources.async_items() if URL_BASE in r.get("url", "")
            ]
        except Exception as err:  # noqa: BLE001 — diagnostics must never raise
            _LOGGER.debug("Could not read Lovelace resources: %s", err)
            ours = []
            info["resource_error"] = str(err)
        info["resource_registered"] = bool(ours)
        info["resource_urls"] = [r.get("url", "") for r in ours]

    # Which Lovelace dashboards exist at all. An empty list on HA 2026.x means
    # the user has only the new Overview panel, where no custom card can render.
    try:
        dashboards = getattr(lovelace, "dashboards", None) or {}
        info["lovelace_dashboards"] = sorted(k for k in dashboards if k)
    except Exception as err:  # noqa: BLE001 — diagnostics must never raise
        _LOGGER.debug("Could not read Lovelace dashboards: %s", err)

    return info


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for the Pawsistant config entry."""
    coordinator: PawsistantCoordinator = entry.runtime_data
    store = coordinator.store

    # ------------------------------------------------------------------
    # Dogs
    # ------------------------------------------------------------------
    dogs = store.get_dogs()
    num_dogs = len(dogs)

    # ------------------------------------------------------------------
    # Event counts per type (aggregate across all dogs and loaded years)
    # ------------------------------------------------------------------
    event_counts: dict[str, int] = {}
    for dog_id in dogs:
        events = await store.get_events(dog_id)
        for event in events:
            etype = event.get("event_type", "unknown")
            event_counts[etype] = event_counts.get(etype, 0) + 1

    # ------------------------------------------------------------------
    # Current sensor states for all Pawsistant entities
    # ------------------------------------------------------------------
    sensor_states: dict[str, str] = {}
    all_states = hass.states.async_all(DOMAIN)
    for state in all_states:
        sensor_states[state.entity_id] = state.state

    # Also grab sensor platform entities
    sensor_states_all: dict[str, str] = {}
    for state in hass.states.async_all():
        if state.entity_id.startswith("sensor.") and any(
            dog_info["name"].lower().replace(" ", "_") in state.entity_id
            for dog_info in dogs.values()
        ):
            sensor_states_all[state.entity_id] = state.state

    # ------------------------------------------------------------------
    # Files and versions. File I/O runs in the executor, not in the event loop.
    # ------------------------------------------------------------------
    storage_files = await hass.async_add_executor_job(
        _storage_file_sizes, hass.config.config_dir
    )
    card_file = await hass.async_add_executor_job(_card_file_info)
    integration = await async_get_integration(hass, DOMAIN)

    # ------------------------------------------------------------------
    # Known / loaded years from the store
    # ------------------------------------------------------------------
    known_years = store.known_years()
    loaded_years = store.loaded_years()

    diagnostics: dict[str, Any] = {
        "config_entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "integration_version": str(integration.version),
        "ha_version": HA_VERSION,
        "num_dogs": num_dogs,
        "dogs": {
            dog_id: {
                "name": dog_info["name"],
                "breed": dog_info.get("breed", ""),
                "birth_date": dog_info.get("birth_date", ""),
            }
            for dog_id, dog_info in dogs.items()
        },
        "event_counts_by_type": event_counts,
        "total_events_loaded": sum(event_counts.values()),
        "known_years": known_years,
        "loaded_years": loaded_years,
        "storage_files": storage_files,
        "sensor_states": sensor_states_all,
        "card_registration": _card_registration(hass, card_file),
    }

    return diagnostics
