"""Sensor platform for DogLog integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from pydoglog.models import Dog, DogEvent, EventType

from homeassistant.config_entries import ConfigEntry

from .coordinator import DogLogCoordinator

DOMAIN = "doglog"

EVENT_TYPE_ICONS: dict[EventType, str] = {
    EventType.FOOD: "mdi:food-drumstick",
    EventType.TREAT: "mdi:cookie",
    EventType.WALK: "mdi:walk",
    EventType.PEE: "mdi:water",
    EventType.POOP: "mdi:emoticon-poop",
    EventType.TEETH_BRUSHING: "mdi:toothbrush",
    EventType.GROOMING: "mdi:content-cut",
    EventType.TRAINING: "mdi:school",
    EventType.MEDICINE: "mdi:pill",
    EventType.WEIGHT: "mdi:scale-bathroom",
    EventType.TEMPERATURE: "mdi:thermometer",
    EventType.WATER: "mdi:cup-water",
    EventType.SLEEP: "mdi:sleep",
    EventType.VACCINE: "mdi:needle",
    EventType.BLOOD_GLUCOSE: "mdi:blood-bag",
}

MOST_RECENT_EVENT_TYPES = [
    EventType.FOOD,
    EventType.TREAT,
    EventType.WALK,
    EventType.PEE,
    EventType.POOP,
    EventType.WATER,
    EventType.SLEEP,
    EventType.TEETH_BRUSHING,
    EventType.GROOMING,
    EventType.TRAINING,
    EventType.MEDICINE,
    EventType.VACCINE,
]

DAILY_COUNT_EVENT_TYPES = [
    EventType.FOOD,
    EventType.TREAT,
    EventType.WALK,
    EventType.PEE,
    EventType.POOP,
    EventType.WATER,
]


def _slug(name: str) -> str:
    """Convert a name to a slug-safe string."""
    return name.lower().replace(" ", "_")


@dataclass(frozen=True, kw_only=True)
class DogLogMostRecentSensorDescription(SensorEntityDescription):
    """Describe a DogLog most-recent sensor."""

    event_type: EventType


@dataclass(frozen=True, kw_only=True)
class DogLogDailyCountSensorDescription(SensorEntityDescription):
    """Describe a DogLog daily count sensor."""

    event_type: EventType


def _get_most_recent_event(
    events: list[DogEvent], event_type: EventType
) -> DogEvent | None:
    """Get the most recent event of a given type."""
    for event in events:
        if event.event_type == event_type:
            return event
    return None


def _count_today(events: list[DogEvent], event_type: EventType) -> int:
    """Count events of a given type from today."""
    today = datetime.now(timezone.utc).date()
    count = 0
    for event in events:
        if event.event_type != event_type:
            continue
        event_date = datetime.fromtimestamp(
            event.timestamp / 1000 if event.timestamp > 1e12 else event.timestamp,
            tz=timezone.utc,
        ).date()
        if event_date == today:
            count += 1
    return count


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up DogLog sensors."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = []

    for dog in coordinator.dogs:
        slug = _slug(dog.name)

        # Most-recent sensors
        for event_type in MOST_RECENT_EVENT_TYPES:
            type_name = event_type.name.lower()
            description = DogLogMostRecentSensorDescription(
                key=f"{slug}_most_recent_{type_name}",
                name=f"{dog.name} Most Recent {event_type.name.replace('_', ' ').title()}",
                icon=EVENT_TYPE_ICONS.get(event_type, "mdi:paw"),
                event_type=event_type,
            )
            entities.append(
                DogLogMostRecentSensor(coordinator, description, dog)
            )

        # Daily count sensors
        for event_type in DAILY_COUNT_EVENT_TYPES:
            type_name = event_type.name.lower()
            # Use plural for walk
            display = type_name + "s" if type_name == "walk" else type_name
            description = DogLogDailyCountSensorDescription(
                key=f"{slug}_daily_{display}_count",
                name=f"{dog.name} Daily {event_type.name.replace('_', ' ').title()} Count",
                icon=EVENT_TYPE_ICONS.get(event_type, "mdi:paw"),
                state_class=SensorStateClass.TOTAL,
                event_type=event_type,
            )
            entities.append(
                DogLogDailyCountSensor(coordinator, description, dog)
            )

        # Poop count today sensor (automation-friendly name)
        entities.append(
            DogLogPoopCountTodaySensor(coordinator, dog)
        )

        # Weight sensor
        entities.append(DogLogWeightSensor(coordinator, dog))

    async_add_entities(entities)


class DogLogMostRecentSensor(CoordinatorEntity[DogLogCoordinator], SensorEntity):
    """Sensor showing the timestamp of the most recent event of a type."""

    entity_description: DogLogMostRecentSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DogLogCoordinator,
        description: DogLogMostRecentSensorDescription,
        dog: Dog,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._dog = dog
        self._attr_unique_id = f"doglog_{dog.id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, dog.id)},
            "name": dog.name,
            "manufacturer": "DogLog",
            "model": "Pet",
        }

    @property
    def native_value(self) -> str | None:
        """Return the ISO timestamp of the most recent event."""
        events = self.coordinator.data.get(self._dog.name, [])
        event = _get_most_recent_event(events, self.entity_description.event_type)
        if event is None:
            return None
        ts = event.timestamp
        if ts > 1e12:
            ts = ts / 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        events = self.coordinator.data.get(self._dog.name, [])
        event = _get_most_recent_event(events, self.entity_description.event_type)
        if event is None:
            return {}
        attrs: dict[str, Any] = {"event_id": event.id}
        if event.note:
            attrs["note"] = event.note
        if event.extra:
            for k, v in event.extra.items():
                attrs[k] = v
        return attrs


class DogLogDailyCountSensor(CoordinatorEntity[DogLogCoordinator], SensorEntity):
    """Sensor showing the count of events of a type today."""

    entity_description: DogLogDailyCountSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DogLogCoordinator,
        description: DogLogDailyCountSensorDescription,
        dog: Dog,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._dog = dog
        self._attr_unique_id = f"doglog_{dog.id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, dog.id)},
            "name": dog.name,
            "manufacturer": "DogLog",
            "model": "Pet",
        }

    @property
    def native_value(self) -> int:
        """Return the count of events today."""
        events = self.coordinator.data.get(self._dog.name, [])
        return _count_today(events, self.entity_description.event_type)


class DogLogPoopCountTodaySensor(CoordinatorEntity[DogLogCoordinator], SensorEntity):
    """Sensor showing the count of poop events today (automation-friendly name)."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:emoticon-poop"

    def __init__(
        self,
        coordinator: DogLogCoordinator,
        dog: Dog,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._dog = dog
        slug = _slug(dog.name)
        self._attr_unique_id = f"doglog_{dog.id}_{slug}_poop_count_today"
        self._attr_name = f"{dog.name} Poop Count Today"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, dog.id)},
            "name": dog.name,
            "manufacturer": "DogLog",
            "model": "Pet",
        }

    @property
    def native_value(self) -> int:
        """Return the count of poop events today."""
        events = self.coordinator.data.get(self._dog.name, [])
        return _count_today(events, EventType.POOP)


class DogLogWeightSensor(CoordinatorEntity[DogLogCoordinator], SensorEntity):
    """Sensor showing the latest weight measurement."""

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "lbs"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:scale-bathroom"

    def __init__(
        self,
        coordinator: DogLogCoordinator,
        dog: Dog,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._dog = dog
        slug = _slug(dog.name)
        self._attr_unique_id = f"doglog_{dog.id}_{slug}_weight"
        self._attr_name = f"{dog.name} Weight"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, dog.id)},
            "name": dog.name,
            "manufacturer": "DogLog",
            "model": "Pet",
        }

    @property
    def native_value(self) -> float | None:
        """Return the latest weight value."""
        events = self.coordinator.data.get(self._dog.name, [])
        event = _get_most_recent_event(events, EventType.WEIGHT)
        if event is None:
            return None
        # Weight value is in extra dict
        if event.extra and "value" in event.extra:
            return float(event.extra["value"])
        return None
