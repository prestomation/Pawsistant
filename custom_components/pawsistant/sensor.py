"""Sensor platform for Pawsistant integration.

All sensors read from PawsistantCoordinator.data which has the shape:
    { "<dog_id>": [ {event_dict}, ... ] }   (newest-first)

Backward-compatible entity IDs are preserved so existing HA dashboards and
automations continue to work:
    sensor.<dog_name_slug>_most_recent_pee
    sensor.<dog_name_slug>_daily_pee_count
    sensor.<dog_name_slug>_poop_count_today
    sensor.<dog_name_slug>_weight
    sensor.<dog_name_slug>_days_since_medicine
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfMass, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DEFAULT_SPECIES, DOMAIN
from .coordinator import PawsistantCoordinator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# MDI icon map keyed by event_type string
EVENT_TYPE_ICONS: dict[str, str] = {
    "food": "mdi:food-drumstick",
    "treat": "mdi:cookie",
    "walk": "mdi:walk",
    "pee": "mdi:water",
    "poop": "mdi:emoticon-poop",
    "teeth": "mdi:toothbrush",
    "grooming": "mdi:content-cut",
    "training": "mdi:school",
    "medicine": "mdi:pill",
    "weight": "mdi:scale-bathroom",
    "water": "mdi:cup-water",
    "sleep": "mdi:sleep",
    "vaccine": "mdi:needle",
    "sick": "mdi:emoticon-sick",
}
MOST_RECENT_EVENT_TYPES: list[str] = [
    "food",
    "treat",
    "walk",
    "pee",
    "poop",
    "water",
    "sleep",
    "teeth",
    "grooming",
    "training",
    "medicine",
    "vaccine",
    "sick",
]

# Sensor types that show "count today"
DAILY_COUNT_EVENT_TYPES: list[str] = [
    "food",
    "treat",
    "walk",
    "pee",
    "poop",
    "water",
]


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def _slug(name: str) -> str:
    """Convert a name to a lowercase, underscore-separated slug."""
    return name.lower().replace(" ", "_")


def _to_datetime(ts: Any) -> datetime:
    """Parse an event timestamp to a timezone-aware datetime.

    Accepts:
    - ISO 8601 string (from local store)
    - datetime object (already parsed)
    - numeric: milliseconds if > 1e12, else seconds (legacy Firebase format)
    """
    if isinstance(ts, datetime):
        return ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)
    if isinstance(ts, str):
        try:
            dt = datetime.fromisoformat(ts)
            return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            pass
    # Numeric fallback
    try:
        numeric = float(ts)
        if numeric > 1e12:
            numeric /= 1000
        return datetime.fromtimestamp(numeric, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return datetime.min.replace(tzinfo=timezone.utc)


def _get_most_recent_event(
    events: list[dict[str, Any]], event_type: str
) -> dict[str, Any] | None:
    """Return the first (newest) event of *event_type*, or None."""
    for event in events:
        if event.get("event_type") == event_type:
            return event
    return None


def _count_today(events: list[dict[str, Any]], event_type: str) -> int:
    """Count events of *event_type* that occurred today (local timezone)."""
    today = dt_util.now().date()
    count = 0
    for event in events:
        if event.get("event_type") != event_type:
            continue
        event_date = (
            _to_datetime(event.get("timestamp"))
            .astimezone(dt_util.DEFAULT_TIME_ZONE)
            .date()
        )
        if event_date == today:
            count += 1
    return count


def _days_since(events: list[dict[str, Any]], event_type: str) -> float | None:
    """Return decimal days since the most recent *event_type* event, or None."""
    event = _get_most_recent_event(events, event_type)
    if event is None:
        return None
    delta = dt_util.now() - _to_datetime(event.get("timestamp"))
    return round(delta.total_seconds() / 86400, 1)


# ---------------------------------------------------------------------------
# Sensor descriptions (typed dataclasses)
# ---------------------------------------------------------------------------


@dataclass(kw_only=True)
class PawsistantMostRecentSensorDescription(SensorEntityDescription):
    """Describe a Pawsistant most-recent-event sensor."""

    event_type: str = ""


@dataclass(kw_only=True)
class PawsistantDailyCountSensorDescription(SensorEntityDescription):
    """Describe a Pawsistant daily-count sensor."""

    event_type: str = ""


# ---------------------------------------------------------------------------
# Platform setup
# ---------------------------------------------------------------------------


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Pawsistant sensor entities from a config entry."""
    coordinator: PawsistantCoordinator = entry.runtime_data
    entities: list[SensorEntity] = []

    dogs = coordinator.store.get_dogs()  # {dog_id: {name, breed, birth_date}}

    for dog_id, dog_info in dogs.items():
        dog_name = dog_info["name"]
        species = dog_info.get("species", DEFAULT_SPECIES) or DEFAULT_SPECIES
        slug = _slug(dog_name)

        # ------------------------------------------------------------------
        # Most-recent-event sensors
        # ------------------------------------------------------------------
        for event_type in MOST_RECENT_EVENT_TYPES:
            display_name = event_type.replace("_", " ").title()
            description = PawsistantMostRecentSensorDescription(
                key=f"most_recent_{event_type}",
                name=f"Most Recent {display_name}",
                icon=EVENT_TYPE_ICONS.get(event_type, "mdi:paw"),
                device_class=SensorDeviceClass.TIMESTAMP,
                event_type=event_type,
            )
            entities.append(
                PawsistantMostRecentSensor(coordinator, description, dog_id, dog_name, species)
            )

        # ------------------------------------------------------------------
        # Daily-count sensors
        # ------------------------------------------------------------------
        for event_type in DAILY_COUNT_EVENT_TYPES:
            # Backward-compatible: "walk" → "walks" in the key
            display_key = event_type + "s" if event_type == "walk" else event_type
            description = PawsistantDailyCountSensorDescription(
                key=f"daily_{display_key}_count",
                name=f"Daily {event_type.replace('_', ' ').title()} Count",
                icon=EVENT_TYPE_ICONS.get(event_type, "mdi:paw"),
                state_class=SensorStateClass.TOTAL,
                event_type=event_type,
            )
            entities.append(
                PawsistantDailyCountSensor(coordinator, description, dog_id, dog_name, species)
            )

        # ------------------------------------------------------------------
        # Weight sensor
        # ------------------------------------------------------------------
        entities.append(PawsistantWeightSensor(coordinator, dog_id, dog_name, species))

        # ------------------------------------------------------------------
        # Days since last medicine sensor
        # ------------------------------------------------------------------
        entities.append(PawsistantDaysSinceMedicineSensor(coordinator, dog_id, dog_name, species))

        # ------------------------------------------------------------------
        # Recent timeline sensor (last 24h events for dashboard)
        # ------------------------------------------------------------------
        entities.append(PawsistantRecentTimelineSensor(coordinator, dog_id, dog_name, species))

    async_add_entities(entities)


# ---------------------------------------------------------------------------
# Helper mixin for device_info
# ---------------------------------------------------------------------------


class _PawsistantSensorBase(CoordinatorEntity[PawsistantCoordinator], SensorEntity):
    """Base class providing shared dog-device binding."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PawsistantCoordinator,
        dog_id: str,
        dog_name: str,
        species: str = DEFAULT_SPECIES,
    ) -> None:
        """Initialise with coordinator and dog identity."""
        super().__init__(coordinator)
        self._dog_id = dog_id
        self._dog_name = dog_name
        self._species = species or DEFAULT_SPECIES
        self._attr_device_info = coordinator.get_device_info(dog_id, dog_name, self._species)

    def _dog_events(self) -> list[dict[str, Any]]:
        """Shortcut to this dog's event list from coordinator data."""
        if self.coordinator.data is None:
            return []
        return self.coordinator.data.get(self._dog_id, [])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the dog name, species, event type registry, button metrics,
        and shown_types on every sensor so the card can render dynamic metadata."""
        attrs = {
            "dog": self._dog_name,
            "species": self._species,
            "event_types": self.coordinator.event_types,
            "button_metrics": self.coordinator.button_metrics,
        }
        # Include server-side shown_types if set for this dog
        shown = self.coordinator.store.get_shown_types(self._dog_name)
        if shown is not None:
            attrs["shown_types"] = shown
        return attrs


# ---------------------------------------------------------------------------
# Concrete sensor classes
# ---------------------------------------------------------------------------


class PawsistantMostRecentSensor(_PawsistantSensorBase):
    """Sensor: timestamp of the most recent event of a given type."""

    entity_description: PawsistantMostRecentSensorDescription

    def __init__(
        self,
        coordinator: PawsistantCoordinator,
        description: PawsistantMostRecentSensorDescription,
        dog_id: str,
        dog_name: str,
        species: str = DEFAULT_SPECIES,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, dog_id, dog_name, species)
        self.entity_description = description
        # Unique ID anchored to dog_id so it survives dog renames
        self._attr_unique_id = f"pawsistant_{dog_id}_{description.key}"

    @property
    def native_value(self) -> datetime | None:
        """Return the most recent event timestamp (timezone-aware datetime).

        SensorDeviceClass.TIMESTAMP requires a datetime, not a string.
        HA will display it in the user's configured timezone automatically.
        """
        event = _get_most_recent_event(
            self._dog_events(), self.entity_description.event_type
        )
        if event is None:
            return None
        return _to_datetime(event.get("timestamp"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return event_id and optional note/value as extra attributes."""
        attrs: dict[str, Any] = {**super().extra_state_attributes}
        event = _get_most_recent_event(
            self._dog_events(), self.entity_description.event_type
        )
        if event is None:
            return attrs
        attrs["event_id"] = event.get("id", "")
        if event.get("note"):
            attrs["note"] = event["note"]
        if event.get("value") is not None:
            attrs["value"] = event["value"]
        return attrs


class PawsistantDailyCountSensor(_PawsistantSensorBase):
    """Sensor: count of events of a given type today."""

    entity_description: PawsistantDailyCountSensorDescription

    def __init__(
        self,
        coordinator: PawsistantCoordinator,
        description: PawsistantDailyCountSensorDescription,
        dog_id: str,
        dog_name: str,
        species: str = DEFAULT_SPECIES,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, dog_id, dog_name, species)
        self.entity_description = description
        self._attr_unique_id = f"pawsistant_{dog_id}_{description.key}"

    @property
    def native_value(self) -> int:
        """Return the count of matching events today."""
        return _count_today(self._dog_events(), self.entity_description.event_type)


class PawsistantWeightSensor(_PawsistantSensorBase):
    """Sensor: most recent weight value (lbs)."""

    _attr_native_unit_of_measurement = UnitOfMass.POUNDS
    _attr_device_class = SensorDeviceClass.WEIGHT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:scale-bathroom"

    def __init__(
        self,
        coordinator: PawsistantCoordinator,
        dog_id: str,
        dog_name: str,
        species: str = DEFAULT_SPECIES,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, dog_id, dog_name, species)
        self._attr_unique_id = f"pawsistant_{dog_id}_weight"
        self._attr_name = "Weight"

    @property
    def native_value(self) -> float | None:
        """Return the most recent weight in lbs, or None if no record exists."""
        event = _get_most_recent_event(self._dog_events(), "weight")
        if event is None:
            return None
        val = event.get("value")
        return float(val) if val is not None else None


class PawsistantDaysSinceMedicineSensor(_PawsistantSensorBase):
    """Sensor: days since the last medicine event was logged.

    Useful for reminder automations: if this value exceeds the expected
    dosing interval the automation can fire a notification.
    """

    _attr_native_unit_of_measurement = UnitOfTime.DAYS
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:pill"

    def __init__(
        self,
        coordinator: PawsistantCoordinator,
        dog_id: str,
        dog_name: str,
        species: str = DEFAULT_SPECIES,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, dog_id, dog_name, species)
        self._attr_unique_id = f"pawsistant_{dog_id}_days_since_medicine"
        self._attr_name = "Days Since Medicine"

    @property
    def native_value(self) -> float | None:
        """Return decimal days since the last medicine event, or None."""
        return _days_since(self._dog_events(), "medicine")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the last medicine event note as an attribute."""
        attrs: dict[str, Any] = {**super().extra_state_attributes}
        event = _get_most_recent_event(self._dog_events(), "medicine")
        if event is None:
            return attrs
        if event.get("note"):
            attrs["medicine_name"] = event["note"]
        if event.get("id"):
            attrs["event_id"] = event["id"]
        return attrs


class PawsistantRecentTimelineSensor(_PawsistantSensorBase):
    """Sensor: count of events in the last 24 hours.

    The state is the count.  The ``events`` extra-state-attribute carries a
    list of dicts (newest-first) with keys: type, time, note, event_id.
    Dashboard markdown cards can iterate ``state_attr(...)['events']`` to
    render a chronological timeline.
    """

    _attr_icon = "mdi:timeline-clock"

    def __init__(
        self,
        coordinator: PawsistantCoordinator,
        dog_id: str,
        dog_name: str,
        species: str = DEFAULT_SPECIES,
    ) -> None:
        super().__init__(coordinator, dog_id, dog_name, species)
        self._attr_unique_id = f"pawsistant_{dog_id}_recent_timeline"
        self._attr_name = "Recent Timeline"

    def _recent_events(self) -> list[dict[str, Any]]:
        """Return events from the last 24 hours, sorted newest-first."""
        cutoff = dt_util.now() - timedelta(hours=24)
        result = []
        for event in self._dog_events():
            ts = _to_datetime(event.get("timestamp"))
            if ts >= cutoff:
                result.append(event)
        # Sort by timestamp descending (newest first)
        result.sort(key=lambda e: _to_datetime(e.get("timestamp")), reverse=True)
        return result

    @property
    def native_value(self) -> int:
        return len(self._recent_events())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        events = self._recent_events()
        timeline = []
        for e in events:
            ts = _to_datetime(e.get("timestamp"))
            local_ts = ts.astimezone(dt_util.DEFAULT_TIME_ZONE)
            timeline.append({
                "type": e.get("event_type", ""),
                "time": local_ts.strftime("%I:%M %p").lstrip("0"),
                "day": local_ts.strftime("%a"),
                "date": local_ts.strftime("%m/%d"),
                "iso": local_ts.isoformat(),
                "note": e.get("note", ""),
                "event_id": e.get("id", ""),
            })
        # Also expose the very last event ID for undo
        last_event_id = events[0].get("id", "") if events else ""
        return {
            **super().extra_state_attributes,
            "events": timeline,
            "last_event_id": last_event_id,
        }
