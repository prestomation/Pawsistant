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

No sensitive data is included since Pawsistant has no cloud auth or credentials.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import PawsistantCoordinator

_LOGGER = logging.getLogger(__name__)

# No fields to redact — Pawsistant is local-only with no credentials or tokens.
TO_REDACT: set[str] = set()


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
    # Storage file sizes (.storage/pawsistant*)
    # ------------------------------------------------------------------
    storage_dir = Path(hass.config.config_dir) / ".storage"
    storage_files: dict[str, int] = {}
    if storage_dir.is_dir():
        for path in sorted(storage_dir.glob("pawsistant*")):
            try:
                storage_files[path.name] = path.stat().st_size
            except OSError as err:
                _LOGGER.debug("Could not stat %s: %s", path.name, err)
                storage_files[path.name] = -1

    # ------------------------------------------------------------------
    # HA version
    # ------------------------------------------------------------------
    ha_version = hass.config.version if hasattr(hass.config, "version") else "unknown"
    # Prefer the attribute used by HA 2024+
    if hasattr(hass, "config") and hasattr(hass.config, "version"):
        ha_version = str(hass.config.version)

    # ------------------------------------------------------------------
    # Integration version (from manifest)
    # ------------------------------------------------------------------
    integration_version = "unknown"
    manifest_path = Path(__file__).parent / "manifest.json"
    try:
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        integration_version = manifest_data.get("version", "unknown")
    except (OSError, json.JSONDecodeError) as err:
        _LOGGER.debug("Could not read manifest.json: %s", err)

    # ------------------------------------------------------------------
    # Known / loaded years from the store
    # ------------------------------------------------------------------
    known_years = store.known_years()
    loaded_years = store.loaded_years()

    diagnostics: dict[str, Any] = {
        "config_entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "integration_version": integration_version,
        "ha_version": str(ha_version),
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
    }

    return diagnostics
