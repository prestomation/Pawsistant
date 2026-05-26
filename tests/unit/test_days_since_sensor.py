"""Unit tests for PawsistantDaysSinceSensor and PawsistantDaysSinceMedicineSensor.

Tests:
1. _days_since and _get_most_recent_event utility functions
2. PawsistantDaysSinceSensor creates with correct unique_id and name
3. PawsistantDaysSinceSensor returns correct native_value
4. PawsistantDaysSinceMedicineSensor still works (backward compat)
5. async_setup_entry creates days_since sensors for all types with metric=days_since

We avoid importing the full sensor module (which requires HA infrastructure)
by testing the pure utility functions directly and testing sensor class
attributes through a lightweight import approach.
"""

from __future__ import annotations

import sys
import types
import pathlib
import importlib.util
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

# ── Unified HA metaclass ───────────────────────────────────────────────────────
# Both SensorEntity and CoordinatorEntity need the same metaclass to
# avoid metaclass conflicts when sensor.py defines classes like
# _PawsistantSensorBase(CoordinatorEntity[PawsistantCoordinator], SensorEntity).

class _HAMeta(type):
    """Metaclass supporting __getitem__ for generic type syntax (Python 3.9+)."""
    def __getitem__(cls, item):
        return cls


def _inject_stubs() -> None:
    if "homeassistant" not in sys.modules:
        ha_mod = types.ModuleType("homeassistant")
        sys.modules["homeassistant"] = ha_mod

    if "homeassistant.core" not in sys.modules:
        core_mod = types.ModuleType("homeassistant.core")
        core_mod.Callback = lambda *a, **kw: (lambda f: f)
        sys.modules["homeassistant.core"] = core_mod

    if "homeassistant.components" not in sys.modules:
        comp_mod = types.ModuleType("homeassistant.components")
        sys.modules["homeassistant.components"] = comp_mod

    if "homeassistant.components.sensor" not in sys.modules:
        sensor_mod = types.ModuleType("homeassistant.components.sensor")
        sensor_mod.SensorDeviceClass = type("SensorDeviceClass", (), {
            "TIMESTAMP": "timestamp",
            "DURATION": "duration",
            "WEIGHT": "weight",
        })
        sensor_mod.SensorEntity = _HAMeta("SensorEntity", (), {"__init__": lambda self: None})
        sensor_mod.SensorEntityDescription = type("SensorEntityDescription", (), {
            "__init__": lambda self, **kw: None,
        })
        sensor_mod.SensorStateClass = type("SensorStateClass", (), {
            "TOTAL": "total",
            "MEASUREMENT": "measurement",
        })
        sys.modules["homeassistant.components.sensor"] = sensor_mod

    if "homeassistant.config_entries" not in sys.modules:
        ce_mod = types.ModuleType("homeassistant.config_entries")
        ce_mod.ConfigEntry = type("ConfigEntry", (), {})
        sys.modules["homeassistant.config_entries"] = ce_mod

    if "homeassistant.const" not in sys.modules:
        const_mod = types.ModuleType("homeassistant.const")
        const_mod.UnitOfMass = type("UnitOfMass", (), {"POUNDS": "lb"})
        const_mod.UnitOfTime = type("UnitOfTime", (), {"DAYS": "d"})
        sys.modules["homeassistant.const"] = const_mod

    if "homeassistant.helpers" not in sys.modules:
        helpers_mod = types.ModuleType("homeassistant.helpers")
        sys.modules["homeassistant.helpers"] = helpers_mod

    if "homeassistant.helpers.entity_platform" not in sys.modules:
        ep_mod = types.ModuleType("homeassistant.helpers.entity_platform")
        ep_mod.AddEntitiesCallback = type("AddEntitiesCallback", (), {})
        sys.modules["homeassistant.helpers.entity_platform"] = ep_mod

    if "homeassistant.helpers.update_coordinator" not in sys.modules:
        uc_mod = types.ModuleType("homeassistant.helpers.update_coordinator")
        uc_mod.CoordinatorEntity = _HAMeta("CoordinatorEntity", (), {
            "__init__": lambda self, coordinator: setattr(self, 'coordinator', coordinator),
        })
        uc_mod.UpdateFailed = type("UpdateFailed", (Exception,), {})
        uc_mod.DataUpdateCoordinator = type("DataUpdateCoordinator", (), {})
        sys.modules["homeassistant.helpers.update_coordinator"] = uc_mod

    if "homeassistant.helpers.device_registry" not in sys.modules:
        dr_mod = types.ModuleType("homeassistant.helpers.device_registry")
        dr_mod.DeviceInfo = type("DeviceInfo", (), {
            "__init__": lambda self, **kw: None,
        })
        sys.modules["homeassistant.helpers.device_registry"] = dr_mod

    if "homeassistant.util" not in sys.modules:
        util_mod = types.ModuleType("homeassistant.util")
        sys.modules["homeassistant.util"] = util_mod

    if "homeassistant.util.dt" not in sys.modules:
        dt_mod = types.ModuleType("homeassistant.util.dt")
        dt_mod.now = lambda tz=None: datetime.now(tz or timezone.utc)
        dt_mod.DEFAULT_TIME_ZONE = timezone.utc
        sys.modules["homeassistant.util.dt"] = dt_mod

_inject_stubs()

# Remove stale modules so importlib loads fresh
for key in list(sys.modules):
    if key == "custom_components.pawsistant" or key.startswith("custom_components.pawsistant."):
        del sys.modules[key]

_repo_root = pathlib.Path(__file__).parent.parent.parent


def _load_module(name: str, path: pathlib.Path):
    """Load a module from file path and register it in sys.modules."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Load modules in dependency order
_const_mod = _load_module(
    "custom_components.pawsistant.const",
    _repo_root / "custom_components" / "pawsistant" / "const.py",
)

# Mock out the coordinator module — sensor.py imports from it
mock_coordinator_mod = types.ModuleType("custom_components.pawsistant.coordinator")
mock_coordinator_mod.PawsistantCoordinator = type("PawsistantCoordinator", (), {
    "__init__": lambda self, *a, **kw: None,
})
sys.modules["custom_components.pawsistant.coordinator"] = mock_coordinator_mod

# Load sensor module
_sensor_mod = _load_module(
    "custom_components.pawsistant.sensor",
    _repo_root / "custom_components" / "pawsistant" / "sensor.py",
)

# Grab classes and functions under test
PawsistantDaysSinceSensor = _sensor_mod.PawsistantDaysSinceSensor
PawsistantDaysSinceMedicineSensor = _sensor_mod.PawsistantDaysSinceMedicineSensor
_days_since = _sensor_mod._days_since
_get_most_recent_event = _sensor_mod._get_most_recent_event
_slug = _sensor_mod._slug


def _make_coordinator(dogs=None, events=None):
    """Create a mock coordinator that _PawsistantSensorBase._dog_events() can use."""
    coordinator = MagicMock()
    coordinator.data = events or {}

    store = MagicMock()
    store.get_dogs.return_value = dogs or {
        "dog1": {"name": "Fido", "breed": "Lab", "birth_date": "2020-01-01", "species": "Dog"}
    }
    store.get_button_metrics.return_value = {
        "medicine": "days_since",
        "weight": "last_value",
        "vaccine": "days_since",
        "walk": "daily_count",
        "teeth": "days_since",
    }
    store.get_event_types.return_value = {
        "medicine": {"name": "Medicine", "icon": "mdi:pill", "color": "#F44336"},
        "weight": {"name": "Weight", "icon": "mdi:scale-bathroom", "color": "#9C27B0"},
        "vaccine": {"name": "Vaccine", "icon": "mdi:needle", "color": "#E91E63"},
        "walk": {"name": "Walk", "icon": "mdi:walk", "color": "#8BC34A"},
        "teeth": {"name": "Teeth", "icon": "mdi:toothbrush", "color": "#009688"},
    }
    store.get_shown_types.return_value = None
    coordinator.store = store
    coordinator.event_types = store.get_event_types()
    coordinator.button_metrics = store.get_button_metrics()
    coordinator.get_device_info = MagicMock(return_value=MagicMock())

    return coordinator


class TestDaysSinceUtility:
    """Test the _days_since utility function directly."""

    def test_days_since_returns_correct_value(self):
        """_days_since should return decimal days since the most recent event."""
        now = datetime.now(timezone.utc)
        events = [
            {"event_type": "teeth", "timestamp": (now - timedelta(days=3, hours=12)).isoformat(), "id": "e1"},
            {"event_type": "medicine", "timestamp": (now - timedelta(days=1)).isoformat(), "id": "e2"},
        ]
        val = _days_since(events, "teeth")
        assert val is not None
        assert abs(val - 3.5) < 0.2

    def test_days_since_none_when_no_events(self):
        """_days_since should return None for event types with no events."""
        assert _days_since([], "teeth") is None

    def test_get_most_recent_event_returns_latest(self):
        """_get_most_recent_event should return the event with the latest timestamp."""
        now = datetime.now(timezone.utc)
        events = [
            {"event_type": "teeth", "timestamp": (now - timedelta(days=5)).isoformat(), "id": "old"},
            {"event_type": "teeth", "timestamp": (now - timedelta(days=1)).isoformat(), "id": "new"},
        ]
        result = _get_most_recent_event(events, "teeth")
        assert result is not None
        assert result["id"] == "new"


class TestPawsistantDaysSinceSensor:
    """Test the generic PawsistantDaysSinceSensor."""

    def test_correct_unique_id_and_name(self):
        """Sensor should have unique_id pawsistant_{dog_id}_days_since_{event_type}
        and name 'Days Since {event_type_name}'."""
        coordinator = _make_coordinator()
        sensor = PawsistantDaysSinceSensor(
            coordinator, "dog1", "Fido", "teeth", "Teeth", "Dog"
        )
        assert sensor._attr_unique_id == "pawsistant_dog1_days_since_teeth"
        assert sensor._attr_name == "Days Since Teeth"

    def test_native_value_returns_days(self):
        """Sensor should return decimal days since the most recent event of its type."""
        now = datetime.now(timezone.utc)
        coordinator = _make_coordinator(events={
            "dog1": [
                {"event_type": "teeth", "timestamp": (now - timedelta(days=3, hours=12)).isoformat(), "id": "e1"},
                {"event_type": "medicine", "timestamp": (now - timedelta(days=1)).isoformat(), "id": "e2"},
            ]
        })
        sensor = PawsistantDaysSinceSensor(
            coordinator, "dog1", "Fido", "teeth", "Teeth", "Dog"
        )
        val = sensor.native_value
        assert val is not None
        assert abs(val - 3.5) < 0.2

    def test_native_value_none_when_no_events(self):
        """Sensor should return None when there are no events of its type."""
        coordinator = _make_coordinator(events={"dog1": []})
        sensor = PawsistantDaysSinceSensor(
            coordinator, "dog1", "Fido", "teeth", "Teeth", "Dog"
        )
        assert sensor.native_value is None

    def test_extra_state_attributes_include_note(self):
        """Attributes should include note and event_id from the most recent event."""
        now = datetime.now(timezone.utc)
        coordinator = _make_coordinator(events={
            "dog1": [
                {"event_type": "teeth", "timestamp": now.isoformat(), "id": "e1", "note": "brushing"},
            ]
        })
        sensor = PawsistantDaysSinceSensor(
            coordinator, "dog1", "Fido", "teeth", "Teeth", "Dog"
        )
        attrs = sensor.extra_state_attributes
        assert attrs.get("note") == "brushing"
        assert attrs.get("event_id") == "e1"

    def test_icon_from_event_type_map(self):
        """Sensor should use the icon from EVENT_TYPE_ICONS if available."""
        coordinator = _make_coordinator()
        sensor = PawsistantDaysSinceSensor(
            coordinator, "dog1", "Fido", "teeth", "Teeth", "Dog"
        )
        assert sensor._attr_icon == "mdi:toothbrush"

    def test_icon_fallback_for_unknown_type(self):
        """Unknown event types should get the default clock icon."""
        coordinator = _make_coordinator()
        sensor = PawsistantDaysSinceSensor(
            coordinator, "dog1", "Fido", "nail_trim", "Nail Trim", "Dog"
        )
        assert sensor._attr_icon == "mdi:clock-outline"

    def test_vaccine_sensor_unique_id(self):
        """Vaccine days_since sensor should have the correct unique_id."""
        coordinator = _make_coordinator()
        sensor = PawsistantDaysSinceSensor(
            coordinator, "dog1", "Fido", "vaccine", "Vaccine", "Dog"
        )
        assert sensor._attr_unique_id == "pawsistant_dog1_days_since_vaccine"
        assert sensor._attr_name == "Days Since Vaccine"

    def test_generic_sensor_uses_generic_note_attribute(self):
        """Generic PawsistantDaysSinceSensor should use 'note' attribute, not 'medicine_name'."""
        now = datetime.now(timezone.utc)
        coordinator = _make_coordinator(events={
            "dog1": [
                {"event_type": "teeth", "timestamp": now.isoformat(), "id": "e1", "note": "toothpaste"},
            ]
        })
        sensor = PawsistantDaysSinceSensor(
            coordinator, "dog1", "Fido", "teeth", "Teeth", "Dog"
        )
        attrs = sensor.extra_state_attributes
        assert "note" in attrs
        assert attrs["note"] == "toothpaste"
        # Should NOT have medicine_name (that was the old hardcoded key)
        assert "medicine_name" not in attrs


class TestPawsistantDaysSinceMedicineSensor:
    """Backward compatibility: PawsistantDaysSinceMedicineSensor still works."""

    def test_backward_compat_unique_id(self):
        """Medicine sensor should keep the original unique_id pattern."""
        coordinator = _make_coordinator()
        sensor = PawsistantDaysSinceMedicineSensor(
            coordinator, "dog1", "Fido", "Dog"
        )
        assert sensor._attr_unique_id == "pawsistant_dog1_days_since_medicine"
        assert sensor._attr_name == "Days Since Medicine"
        assert sensor._attr_icon == "mdi:pill"

    def test_backward_compat_native_value(self):
        """Medicine sensor should return days since the last medicine event."""
        now = datetime.now(timezone.utc)
        coordinator = _make_coordinator(events={
            "dog1": [
                {"event_type": "medicine", "timestamp": (now - timedelta(days=2)).isoformat(), "id": "m1"},
            ]
        })
        sensor = PawsistantDaysSinceMedicineSensor(
            coordinator, "dog1", "Fido", "Dog"
        )
        val = sensor.native_value
        assert val is not None
        assert abs(val - 2.0) < 0.2

    def test_backward_compat_is_subclass(self):
        """Medicine sensor should be a subclass of PawsistantDaysSinceSensor."""
        assert issubclass(PawsistantDaysSinceMedicineSensor, PawsistantDaysSinceSensor)

    def test_backward_compat_medicine_note_attribute(self):
        """Medicine sensor should use the generic 'note' attribute from the parent class."""
        now = datetime.now(timezone.utc)
        coordinator = _make_coordinator(events={
            "dog1": [
                {"event_type": "medicine", "timestamp": now.isoformat(), "id": "m1", "note": "Apoquel"},
            ]
        })
        sensor = PawsistantDaysSinceMedicineSensor(
            coordinator, "dog1", "Fido", "Dog"
        )
        attrs = sensor.extra_state_attributes
        # The generic parent uses "note" as the attribute key
        assert attrs.get("note") == "Apoquel"


class TestSetupEntryLogic:
    """Test the sensor creation logic that async_setup_entry uses for days_since sensors."""

    def test_creates_days_since_sensors_for_non_medicine_types(self):
        """async_setup_entry should create a PawsistantDaysSinceSensor for each
        event type with metric=days_since (except medicine, which has its own class)."""
        coordinator = _make_coordinator()
        entities = []

        dogs = coordinator.store.get_dogs()
        for dog_id, dog_info in dogs.items():
            dog_name = dog_info["name"]
            species = dog_info.get("species", "Dog") or "Dog"

            # Medicine days_since sensor
            entities.append(PawsistantDaysSinceMedicineSensor(coordinator, dog_id, dog_name, species))

            # Generic days_since sensors
            button_metrics = coordinator.store.get_button_metrics()
            event_type_names = coordinator.store.get_event_types()
            for et, metric in button_metrics.items():
                if metric == "days_since" and et != "medicine":
                    et_info = event_type_names.get(et, {})
                    et_name = et_info.get("name", et.replace("_", " ").title())
                    entities.append(
                        PawsistantDaysSinceSensor(coordinator, dog_id, dog_name, et, et_name, species)
                    )

        # Check that we have: medicine (specific) + vaccine + teeth = 3 days_since sensors
        days_since_entities = [e for e in entities if isinstance(e, PawsistantDaysSinceSensor)]
        assert len(days_since_entities) == 3, f"Expected 3 days_since sensors, got {len(days_since_entities)}"

        # Verify types
        etypes = {e._event_type for e in days_since_entities}
        assert etypes == {"medicine", "vaccine", "teeth"}

    def test_no_duplicate_medicine_sensor(self):
        """Medicine should only appear once (as PawsistantDaysSinceMedicineSensor),
        not also as a generic PawsistantDaysSinceSensor."""
        coordinator = _make_coordinator()
        entities = []

        dogs = coordinator.store.get_dogs()
        for dog_id, dog_info in dogs.items():
            dog_name = dog_info["name"]
            species = dog_info.get("species", "Dog") or "Dog"

            entities.append(PawsistantDaysSinceMedicineSensor(coordinator, dog_id, dog_name, species))

            button_metrics = coordinator.store.get_button_metrics()
            event_type_names = coordinator.store.get_event_types()
            for et, metric in button_metrics.items():
                if metric == "days_since" and et != "medicine":
                    et_info = event_type_names.get(et, {})
                    et_name = et_info.get("name", et.replace("_", " ").title())
                    entities.append(
                        PawsistantDaysSinceSensor(coordinator, dog_id, dog_name, et, et_name, species)
                    )

        # Only one sensor should have event_type="medicine"
        medicine_sensors = [e for e in entities if e._event_type == "medicine"]
        assert len(medicine_sensors) == 1, "Medicine should only have one sensor"
        assert isinstance(medicine_sensors[0], PawsistantDaysSinceMedicineSensor)

    def test_unique_ids_are_unique(self):
        """All days_since sensor unique_ids should be unique."""
        coordinator = _make_coordinator()
        entities = []

        dogs = coordinator.store.get_dogs()
        for dog_id, dog_info in dogs.items():
            dog_name = dog_info["name"]
            species = dog_info.get("species", "Dog") or "Dog"

            entities.append(PawsistantDaysSinceMedicineSensor(coordinator, dog_id, dog_name, species))

            button_metrics = coordinator.store.get_button_metrics()
            event_type_names = coordinator.store.get_event_types()
            for et, metric in button_metrics.items():
                if metric == "days_since" and et != "medicine":
                    et_info = event_type_names.get(et, {})
                    et_name = et_info.get("name", et.replace("_", " ").title())
                    entities.append(
                        PawsistantDaysSinceSensor(coordinator, dog_id, dog_name, et, et_name, species)
                    )

        unique_ids = [e._attr_unique_id for e in entities]
        assert len(unique_ids) == len(set(unique_ids)), f"Duplicate unique_ids: {unique_ids}"

    def test_entity_id_pattern_matches_expectation(self):
        """Unique IDs should follow pawsistant_{dog_id}_days_since_{event_type} pattern."""
        coordinator = _make_coordinator()

        entities = []
        dogs = coordinator.store.get_dogs()
        for dog_id, dog_info in dogs.items():
            dog_name = dog_info["name"]
            species = dog_info.get("species", "Dog") or "Dog"

            entities.append(PawsistantDaysSinceMedicineSensor(coordinator, dog_id, dog_name, species))

            button_metrics = coordinator.store.get_button_metrics()
            event_type_names = coordinator.store.get_event_types()
            for et, metric in button_metrics.items():
                if metric == "days_since" and et != "medicine":
                    et_info = event_type_names.get(et, {})
                    et_name = et_info.get("name", et.replace("_", " ").title())
                    entities.append(
                        PawsistantDaysSinceSensor(coordinator, dog_id, dog_name, et, et_name, species)
                    )

        expected_unique_ids = {
            "pawsistant_dog1_days_since_medicine",
            "pawsistant_dog1_days_since_vaccine",
            "pawsistant_dog1_days_since_teeth",
        }
        actual_unique_ids = {e._attr_unique_id for e in entities}
        assert actual_unique_ids == expected_unique_ids, f"Expected {expected_unique_ids}, got {actual_unique_ids}"

    def test_friendly_name_pattern_for_frontend(self):
        """Friendly names should end with 'Days Since {type_name}' for frontend lookup."""
        coordinator = _make_coordinator()
        entities = []

        dogs = coordinator.store.get_dogs()
        for dog_id, dog_info in dogs.items():
            dog_name = dog_info["name"]
            species = dog_info.get("species", "Dog") or "Dog"

            entities.append(PawsistantDaysSinceMedicineSensor(coordinator, dog_id, dog_name, species))

            button_metrics = coordinator.store.get_button_metrics()
            event_type_names = coordinator.store.get_event_types()
            for et, metric in button_metrics.items():
                if metric == "days_since" and et != "medicine":
                    et_info = event_type_names.get(et, {})
                    et_name = et_info.get("name", et.replace("_", " ").title())
                    entities.append(
                        PawsistantDaysSinceSensor(coordinator, dog_id, dog_name, et, et_name, species)
                    )

        names = {e._attr_name for e in entities}
        assert names == {"Days Since Medicine", "Days Since Vaccine", "Days Since Teeth"}