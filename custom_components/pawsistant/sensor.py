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

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
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

from .const import (
    CONF_WEIGHT_THRESHOLD_PCT,
    CONF_WEIGHT_WINDOW_DAYS,
    DEFAULT_SPECIES,
    DEFAULT_WEIGHT_WINDOW_DAYS,
    DOMAIN,
)
from .coordinator import PawsistantCoordinator
from .sensor_analytics import (
    ROUTINE_EVENT_TYPES,
    compute_routine_peaks,
    compute_sick_frequency,
    compute_weight_trend,
    # The canonical event-timestamp parser. It lives in sensor_analytics --
    # which has no HA imports, so it stays unit-testable standalone -- and is
    # aliased to the name this module has always used rather than kept as a
    # second copy: the two had already drifted apart on timezone handling once.
    parse_event_timestamp as _to_datetime,
)

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




def _get_most_recent_event(
    events: list[dict[str, Any]], event_type: str
) -> dict[str, Any] | None:
    """Return the event with the latest timestamp for *event_type*, or None.

    Uses _to_datetime() for comparison so mixed timezone offsets are handled
    correctly regardless of the order events appear in the list.
    """
    matching = [e for e in events if e.get("event_type") == event_type]
    if not matching:
        return None
    return max(matching, key=lambda e: _to_datetime(e.get("timestamp")))


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


def _per_type_metric_maps(
    events: list[dict[str, Any]],
) -> tuple[dict[str, int], dict[str, float], dict[str, str]]:
    """Compute per-event-type metric maps in a single pass over *events*.

    Returns three dicts keyed by event_type, covering every type present in
    the dog's events so the card can render daily_count / days_since /
    hours_since for *any* type (built-in or custom):

    * ``daily_counts``  — count of events that occurred today (local tz)
    * ``days_since``    — decimal days since the most recent event
    * ``last_event_ts`` — ISO timestamp (local tz) of the most recent event

    These power the button-card metric badges. Without them the card could
    only show counts for pee/poop and could never show hours_since, and any
    custom event type was unsupported.
    """
    now = dt_util.now()
    today = now.date()
    daily_counts: dict[str, int] = {}
    most_recent: dict[str, datetime] = {}

    for event in events:
        etype = event.get("event_type")
        if not etype:
            continue
        ts = _to_datetime(event.get("timestamp"))
        local_ts = ts.astimezone(dt_util.DEFAULT_TIME_ZONE)
        if local_ts.date() == today:
            daily_counts[etype] = daily_counts.get(etype, 0) + 1
        if etype not in most_recent or ts > most_recent[etype]:
            most_recent[etype] = ts

    days_since: dict[str, float] = {}
    last_event_ts: dict[str, str] = {}
    for etype, ts in most_recent.items():
        days_since[etype] = round((now - ts).total_seconds() / 86400, 1)
        last_event_ts[etype] = ts.astimezone(dt_util.DEFAULT_TIME_ZONE).isoformat()
        # Surface a 0 for types that have events historically but none today,
        # so a daily_count badge reads "0 today" rather than disappearing.
        daily_counts.setdefault(etype, 0)

    return daily_counts, days_since, last_event_ts


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
        # Days-since sensors for all event types with metric=days_since
        # ------------------------------------------------------------------
        button_metrics = coordinator.store.get_button_metrics()
        event_type_names = coordinator.store.get_event_types()
        for et, metric in button_metrics.items():
            if metric == "days_since":
                et_info = event_type_names.get(et, {})
                et_name = et_info.get("name", et.replace("_", " ").title())
                entities.append(
                    PawsistantDaysSinceSensor(coordinator, dog_id, dog_name, et, et_name, species)
                )

        # ------------------------------------------------------------------
        # Recent timeline sensor (last 24h events for dashboard)
        # ------------------------------------------------------------------
        entities.append(PawsistantRecentTimelineSensor(coordinator, dog_id, dog_name, species))

        # ------------------------------------------------------------------
        # Weight trend sensor
        # ------------------------------------------------------------------
        entities.append(PawsistantWeightTrendSensor(coordinator, dog_id, dog_name, species))

        # ------------------------------------------------------------------
        # Sickness frequency sensor
        # ------------------------------------------------------------------
        entities.append(PawsistantSicknessFrequencySensor(coordinator, dog_id, dog_name, species))

        # ------------------------------------------------------------------
        # Routine sensors (one per tracked event type)
        # ------------------------------------------------------------------
        for event_type in ROUTINE_EVENT_TYPES:
            entities.append(
                PawsistantRoutineSensor(coordinator, dog_id, dog_name, event_type, species)
            )

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
        # Fresh sentinel per entity, so the first _cached() call always misses.
        self._cache_key: Any = object()
        self._cache: dict[str, Any] = {}

    def _dog_events(self) -> list[dict[str, Any]]:
        """Shortcut to this dog's event list from coordinator data."""
        if self.coordinator.data is None:
            return []
        return self.coordinator.data.get(self._dog_id, [])

    def _cached(
        self, key: Any, compute: Callable[[], dict[str, Any]]
    ) -> dict[str, Any]:
        """Memoise *compute* for as long as *key* holds steady.

        HA asks each analytics sensor for its value at least twice per refresh --
        once for ``native_value``, once for ``extra_state_attributes`` -- and the
        analytics functions walk the dog's entire event list each time. *key*
        must capture everything the result depends on: the coordinator's refresh
        timestamp, plus any user setting that should take effect on the next
        refresh rather than waiting for a reload.
        """
        if key != self._cache_key:
            self._cache_key = key
            self._cache = compute()
        return self._cache

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the dog name, species, event type registry, button metrics,
        and shown_types on every sensor so the card can render dynamic metadata."""
        attrs = {
            "dog": self._dog_name,
            "dog_id": self._dog_id,
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


class PawsistantDaysSinceSensor(_PawsistantSensorBase):
    """Sensor: days since the last event of a given type was logged.

    Generic version — works for any event_type (medicine, teeth, vaccine, etc.).
    Used for reminder automations: if this value exceeds the expected
    interval the automation can fire a notification.
    """

    _attr_native_unit_of_measurement = UnitOfTime.DAYS
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: PawsistantCoordinator,
        dog_id: str,
        dog_name: str,
        event_type: str,
        event_type_name: str,
        species: str = DEFAULT_SPECIES,
    ) -> None:
        """Initialise the sensor.

        Args:
            event_type: The event_type key (e.g. 'medicine', 'teeth').
            event_type_name: Human-readable name (e.g. 'Medicine', 'Teeth').
        """
        super().__init__(coordinator, dog_id, dog_name, species)
        self._event_type = event_type
        self._event_type_name = event_type_name
        self._attr_unique_id = f"pawsistant_{dog_id}_days_since_{event_type}"
        self._attr_name = f"Days Since {event_type_name}"
        self._attr_icon = EVENT_TYPE_ICONS.get(event_type, "mdi:clock-outline")

    @property
    def native_value(self) -> float | None:
        """Return decimal days since the last event of this type, or None."""
        return _days_since(self._dog_events(), self._event_type)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the last event note as an attribute."""
        attrs: dict[str, Any] = {**super().extra_state_attributes}
        event = _get_most_recent_event(self._dog_events(), self._event_type)
        if event is None:
            return attrs
        if event.get("note"):
            attrs["note"] = event["note"]
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
        daily_counts, days_since, last_event_ts = _per_type_metric_maps(
            self._dog_events()
        )
        return {
            **super().extra_state_attributes,
            "events": timeline,
            "daily_counts": daily_counts,
            "days_since": days_since,
            "last_event_ts": last_event_ts,
        }


class PawsistantWeightTrendSensor(_PawsistantSensorBase):
    """Sensor: weight trend analysis (gaining/losing/stable)."""

    _attr_icon = "mdi:trending-up"

    def __init__(
        self,
        coordinator: PawsistantCoordinator,
        dog_id: str,
        dog_name: str,
        species: str = DEFAULT_SPECIES,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, dog_id, dog_name, species)
        self._attr_unique_id = f"pawsistant_{dog_id}_weight_trend"
        self._attr_name = "Weight Trend"

    def _settings(self) -> tuple[int | None, float | None]:
        """Return this dog's (window_days, threshold_pct) from the store."""
        settings = self.coordinator.store.get_analytics_settings(self._dog_id)
        return (
            settings.get(CONF_WEIGHT_WINDOW_DAYS, DEFAULT_WEIGHT_WINDOW_DAYS),
            settings.get(CONF_WEIGHT_THRESHOLD_PCT),
        )

    def _compute(self) -> dict[str, Any]:
        """Run the weight-trend analytics function (cached per refresh).

        The window and threshold are part of the cache key rather than read once
        at construction, so a change made in the options flow takes effect on
        the next refresh instead of requiring a reload.
        """
        window_days, threshold_pct = self._settings()
        return self._cached(
            (self.coordinator.last_update_success_time, window_days, threshold_pct),
            lambda: compute_weight_trend(
                self._dog_events(),
                window_days=window_days,
                threshold_pct=threshold_pct,
                now=dt_util.now(),
            ),
        )

    @property
    def native_value(self) -> str | None:
        """Return the recent trend: gaining, losing, or stable.

        Returns ``None`` -- which HA renders as *Unknown* -- when there aren't
        enough readings in the window to call it, rather than the literal string
        "unknown", which would collide with HA's own unknown state.
        """
        trend = self._compute()["trend"]
        return None if trend == "unknown" else trend

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the windowed figures, the window itself, and lifetime totals.

        The state covers the configured recent window; ``lifetime_*`` keeps the
        full-history view available so nothing is lost by windowing.
        """
        attrs: dict[str, Any] = {**super().extra_state_attributes}
        result = self._compute()
        attrs["change_pct"] = result["change_pct"]
        attrs["sample_count"] = result["sample_count"]
        attrs["oldest_value"] = result["oldest_value"]
        attrs["newest_value"] = result["newest_value"]
        attrs["over_days"] = result["over_days"]
        attrs["window_days"] = result["window_days"]
        attrs["threshold_pct"] = result["threshold_pct"]
        attrs["min_samples"] = result["min_samples"]
        attrs["lifetime_trend"] = result["lifetime_trend"]
        attrs["lifetime_change_pct"] = result["lifetime_change_pct"]
        attrs["lifetime_sample_count"] = result["lifetime_sample_count"]
        attrs["lifetime_oldest_value"] = result["lifetime_oldest_value"]
        attrs["lifetime_newest_value"] = result["lifetime_newest_value"]
        attrs["lifetime_over_days"] = result["lifetime_over_days"]
        return attrs


class PawsistantSicknessFrequencySensor(_PawsistantSensorBase):
    """Sensor: count of sick events in the last 30 days."""

    _attr_icon = "mdi:emoticon-sick"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: PawsistantCoordinator,
        dog_id: str,
        dog_name: str,
        species: str = DEFAULT_SPECIES,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, dog_id, dog_name, species)
        self._attr_unique_id = f"pawsistant_{dog_id}_sickness_frequency"
        self._attr_name = "Sickness Frequency"

    def _compute(self) -> dict[str, Any]:
        """Run the sick-frequency analytics function (cached per refresh)."""
        return self._cached(
            self.coordinator.last_update_success_time,
            lambda: compute_sick_frequency(self._dog_events(), now=dt_util.now()),
        )

    @property
    def native_value(self) -> int:
        """Return the count of sick events in the current 30-day window."""
        return self._compute()["count_current"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose previous-window count, cluster size, and days since last."""
        attrs: dict[str, Any] = {**super().extra_state_attributes}
        result = self._compute()
        attrs["count_previous_30d"] = result["count_previous"]
        attrs["cluster_size"] = result["cluster_size"]
        attrs["cluster_active"] = result["cluster_active"]
        attrs["days_since_last"] = result["days_since_last"]
        return attrs


class PawsistantRoutineSensor(_PawsistantSensorBase):
    """Sensor: routine detection for a specific event type."""

    def __init__(
        self,
        coordinator: PawsistantCoordinator,
        dog_id: str,
        dog_name: str,
        event_type: str,
        species: str = DEFAULT_SPECIES,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, dog_id, dog_name, species)
        self._event_type = event_type
        display = event_type.replace("_", " ").title()
        self._attr_unique_id = f"pawsistant_{dog_id}_{event_type}_routine"
        self._attr_name = f"{display} Routine"
        self._attr_icon = EVENT_TYPE_ICONS.get(event_type, "mdi:clock-outline")

    def _compute(self) -> dict[str, Any]:
        """Run the routine-peaks analytics function (cached per refresh).

        ``now`` is passed as local time so the detected peak hours, and the
        judgement of what is due today, are in the user's timezone rather than
        UTC. See the module docstring in sensor_analytics.
        """
        return self._cached(
            self.coordinator.last_update_success_time,
            lambda: compute_routine_peaks(
                self._dog_events(), self._event_type, now=dt_util.now()
            ),
        )

    @property
    def native_value(self) -> str | None:
        """Return schedule status: on_schedule or late.

        Returns ``None`` -- rendered by HA as *Unknown* -- when there isn't
        enough history to establish a routine at all.
        """
        status = self._compute()["status"]
        return None if status == "unknown" else status

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose event_type, routine times, histogram, recency, and sample count."""
        attrs: dict[str, Any] = {**super().extra_state_attributes}
        result = self._compute()
        attrs["event_type"] = self._event_type
        attrs["peak_minutes"] = result["peak_minutes"]
        attrs["histogram"] = result["histogram"]
        attrs["last_event_ago_hours"] = result["last_event_ago_hours"]
        attrs["sample_count"] = result["sample_count"]
        attrs["days_observed"] = result["days_observed"]
        attrs["min_days_required"] = result["min_days_required"]
        attrs["overdue_peak_minute"] = result["overdue_peak_minute"]
        attrs["minutes_overdue"] = result["minutes_overdue"]
        return attrs
