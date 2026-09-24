"""Regression tests for the analytics sensors' per-refresh compute cache.

The three analytics sensors cache `_compute()` keyed on the coordinator's
`last_update_success_time`, so that reading `native_value` and
`extra_state_attributes` in the same HA tick only runs the analytics once.

That attribute is defined by `TimestampDataUpdateCoordinator`, NOT by the plain
`DataUpdateCoordinator`. When `PawsistantCoordinator` extended the plain base,
the cache key was `None` on every read: after the first compute, the stored key
and the live value were both `None`, compared equal forever, and the sensor
state froze at whatever it computed first — it never reflected another event
again for the lifetime of the entity.

These tests pin both halves: the coordinator must expose a key that advances on
refresh, and the sensors must recompute when it does.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest


# ── HA stubs ───────────────────────────────────────────────────────────────────
# Mirrors the harness in test_days_since_sensor.py: sensor.py declares
# `_PawsistantSensorBase(CoordinatorEntity[PawsistantCoordinator], SensorEntity)`,
# so both bases need a metaclass supporting subscript.

class _HAMeta(type):
    """Metaclass supporting __getitem__ for generic type syntax."""

    def __getitem__(cls, item):
        return cls


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _inject_stubs() -> None:
    """Inject lightweight HA module stubs into sys.modules."""
    if "homeassistant" not in sys.modules:
        sys.modules["homeassistant"] = types.ModuleType("homeassistant")

    core_mod = sys.modules.get("homeassistant.core") or types.ModuleType("homeassistant.core")
    if not hasattr(core_mod, "HomeAssistant"):
        core_mod.HomeAssistant = type("HomeAssistant", (), {})
    if not hasattr(core_mod, "callback"):
        core_mod.callback = lambda f: f
    sys.modules["homeassistant.core"] = core_mod

    if "homeassistant.components" not in sys.modules:
        sys.modules["homeassistant.components"] = types.ModuleType("homeassistant.components")

    sensor_mod = types.ModuleType("homeassistant.components.sensor")
    sensor_mod.SensorDeviceClass = type("SensorDeviceClass", (), {
        "TIMESTAMP": "timestamp", "DURATION": "duration", "WEIGHT": "weight",
    })
    sensor_mod.SensorEntity = _HAMeta("SensorEntity", (), {"__init__": lambda self: None})
    sensor_mod.SensorEntityDescription = type("SensorEntityDescription", (), {
        "__init__": lambda self, **kw: None,
    })
    sensor_mod.SensorStateClass = type("SensorStateClass", (), {
        "TOTAL": "total", "MEASUREMENT": "measurement",
    })
    sys.modules["homeassistant.components.sensor"] = sensor_mod

    ce_mod = sys.modules.get("homeassistant.config_entries") or types.ModuleType(
        "homeassistant.config_entries"
    )
    if not hasattr(ce_mod, "ConfigEntry"):
        ce_mod.ConfigEntry = type("ConfigEntry", (), {})
    sys.modules["homeassistant.config_entries"] = ce_mod

    const_mod = sys.modules.get("homeassistant.const") or types.ModuleType("homeassistant.const")
    if not hasattr(const_mod, "UnitOfMass"):
        const_mod.UnitOfMass = type("UnitOfMass", (), {"POUNDS": "lb"})
    if not hasattr(const_mod, "UnitOfTime"):
        const_mod.UnitOfTime = type("UnitOfTime", (), {"DAYS": "d"})
    sys.modules["homeassistant.const"] = const_mod

    if "homeassistant.helpers" not in sys.modules:
        sys.modules["homeassistant.helpers"] = types.ModuleType("homeassistant.helpers")

    if "homeassistant.helpers.entity_platform" not in sys.modules:
        ep_mod = types.ModuleType("homeassistant.helpers.entity_platform")
        ep_mod.AddEntitiesCallback = type("AddEntitiesCallback", (), {})
        sys.modules["homeassistant.helpers.entity_platform"] = ep_mod

    # Faithful stand-ins for the two coordinator bases. The distinction between
    # them is the whole point of these tests, so the stubs must preserve it:
    # only the Timestamp variant carries last_update_success_time.
    uc_mod = types.ModuleType("homeassistant.helpers.update_coordinator")
    uc_mod.CoordinatorEntity = _HAMeta("CoordinatorEntity", (), {
        "__init__": lambda self, coordinator: setattr(self, "coordinator", coordinator),
    })
    uc_mod.UpdateFailed = type("UpdateFailed", (Exception,), {})

    class _DataUpdateCoordinator:
        """Plain base — deliberately has NO last_update_success_time."""

        def __init__(self, *args, **kwargs) -> None:
            self.data = None
            self.last_update_success = True

        def _async_refresh_finished(self) -> None:
            pass

    class _TimestampDataUpdateCoordinator(_DataUpdateCoordinator):
        """Mirrors HA's TimestampDataUpdateCoordinator."""

        last_update_success_time: datetime | None = None

        def _async_refresh_finished(self) -> None:
            if self.last_update_success:
                self.last_update_success_time = _utcnow()

    uc_mod.DataUpdateCoordinator = _HAMeta(
        "DataUpdateCoordinator", (_DataUpdateCoordinator,), {}
    )
    uc_mod.TimestampDataUpdateCoordinator = _HAMeta(
        "TimestampDataUpdateCoordinator", (_TimestampDataUpdateCoordinator,), {}
    )
    sys.modules["homeassistant.helpers.update_coordinator"] = uc_mod

    if "homeassistant.helpers.device_registry" not in sys.modules:
        dr_mod = types.ModuleType("homeassistant.helpers.device_registry")
        dr_mod.DeviceInfo = type("DeviceInfo", (), {"__init__": lambda self, **kw: None})
        sys.modules["homeassistant.helpers.device_registry"] = dr_mod

    if "homeassistant.util" not in sys.modules:
        sys.modules["homeassistant.util"] = types.ModuleType("homeassistant.util")

    if "homeassistant.util.dt" not in sys.modules:
        dt_mod = types.ModuleType("homeassistant.util.dt")
        dt_mod.now = lambda tz=None: datetime.now(tz or timezone.utc)
        dt_mod.utcnow = _utcnow
        dt_mod.DEFAULT_TIME_ZONE = timezone.utc
        sys.modules["homeassistant.util.dt"] = dt_mod


_inject_stubs()

for _key in list(sys.modules):
    if _key == "custom_components.pawsistant" or _key.startswith("custom_components.pawsistant."):
        del sys.modules[_key]

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
_PKG = _REPO_ROOT / "custom_components" / "pawsistant"


def _load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_load_module("custom_components.pawsistant.const", _PKG / "const.py")

# sensor.py imports PawsistantCoordinator only for type annotations, so a stub
# suffices here; the real coordinator is checked separately below.
_mock_coord_mod = types.ModuleType("custom_components.pawsistant.coordinator")
_mock_coord_mod.PawsistantCoordinator = type(
    "PawsistantCoordinator", (), {"__init__": lambda self, *a, **kw: None}
)
sys.modules["custom_components.pawsistant.coordinator"] = _mock_coord_mod

_load_module("custom_components.pawsistant.sensor_analytics", _PKG / "sensor_analytics.py")
_sensor_mod = _load_module("custom_components.pawsistant.sensor", _PKG / "sensor.py")

PawsistantWeightTrendSensor = _sensor_mod.PawsistantWeightTrendSensor
PawsistantSicknessFrequencySensor = _sensor_mod.PawsistantSicknessFrequencySensor
PawsistantRoutineSensor = _sensor_mod.PawsistantRoutineSensor


# ── Fakes ──────────────────────────────────────────────────────────────────────


class FakeCoordinator:
    """Coordinator double matching TimestampDataUpdateCoordinator's contract.

    `refresh()` swaps in new data and advances the cache key the way a real
    successful refresh does.
    """

    def __init__(self, events: dict | None = None) -> None:
        self.data = events or {}
        self.last_update_success_time = _utcnow()
        self.event_types = {}
        self.button_metrics = {}
        store = MagicMock()
        store.get_shown_types.return_value = None
        store.get_analytics_settings.return_value = {
            "weight_window_days": 90,
            "weight_threshold_pct": None,
        }
        self.store = store
        self.get_device_info = MagicMock(return_value=MagicMock())

    def refresh(self, events: dict) -> None:
        self.data = events
        # Strictly increasing, and distinct from the previous value even if the
        # clock resolution would otherwise collide.
        self.last_update_success_time = max(
            _utcnow(), self.last_update_success_time + timedelta(microseconds=1)
        )


_NOW = datetime.now(timezone.utc)


def _weight(value: float, days_ago: int) -> dict:
    return {
        "event_type": "weight",
        "value": value,
        "timestamp": (_NOW - timedelta(days=days_ago)).isoformat(),
        "id": f"w{value}-{days_ago}",
    }


def _sick(days_ago: int) -> dict:
    return {
        "event_type": "sick",
        "timestamp": (_NOW - timedelta(days=days_ago)).isoformat(),
        "id": f"s{days_ago}",
    }


def _food(days_ago: int, hour: int) -> dict:
    ts = (_NOW - timedelta(days=days_ago)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return {"event_type": "food", "timestamp": ts.isoformat(), "id": f"f{days_ago}-{hour}"}


# ── Tests ──────────────────────────────────────────────────────────────────────


class TestCacheInvalidatesOnRefresh:
    """Each analytics sensor must reflect new data after a coordinator refresh."""

    def test_weight_trend_updates_after_refresh(self):
        coord = FakeCoordinator({"dog1": [_weight(50, 20), _weight(50, 10), _weight(50, 1)]})
        sensor = PawsistantWeightTrendSensor(coord, "dog1", "Fido", "Dog")
        assert sensor.native_value == "stable"

        coord.refresh({"dog1": [_weight(50, 20), _weight(60, 10), _weight(80, 1)]})
        assert sensor.native_value == "gaining", (
            "Weight trend froze at its first computed value — the compute cache "
            "is never invalidated."
        )
        assert sensor.extra_state_attributes["change_pct"] == pytest.approx(60.0)

    def test_sickness_frequency_updates_after_refresh(self):
        coord = FakeCoordinator({"dog1": [_sick(3)]})
        sensor = PawsistantSicknessFrequencySensor(coord, "dog1", "Fido", "Dog")
        assert sensor.native_value == 1

        coord.refresh({"dog1": [_sick(3), _sick(2), _sick(1)]})
        assert sensor.native_value == 3, (
            "Sickness count froze at its first computed value."
        )

    def test_routine_sensor_updates_after_refresh(self):
        coord = FakeCoordinator({"dog1": []})
        sensor = PawsistantRoutineSensor(coord, "dog1", "Fido", "food", "Dog")
        assert sensor.extra_state_attributes["sample_count"] == 0

        coord.refresh({"dog1": [_food(d, 8) for d in range(1, 6)]})
        assert sensor.extra_state_attributes["sample_count"] == 5, (
            "Routine sensor froze at its first computed value."
        )
        assert 8 in sensor.extra_state_attributes["peak_hours"]


class TestWeightTrendUsesPerDogSettings:
    """The sensor must read its window/threshold from the store, per dog.

    The analytics function is already covered directly in
    test_sensor_analytics.py; what matters here is that the sensor actually
    passes the stored settings through instead of silently using the defaults.
    """

    def test_stored_window_is_passed_through(self):
        coord = FakeCoordinator(
            {"dog1": [_weight(50, 200), _weight(50, 150), _weight(50, 100)]}
        )
        coord.store.get_analytics_settings.return_value = {
            "weight_window_days": 30,
            "weight_threshold_pct": None,
        }
        sensor = PawsistantWeightTrendSensor(coord, "dog1", "Fido", "Dog")
        # Every reading is older than 30 days, so a respected window leaves too
        # few points to judge. Falling back to the 90-day default would too;
        # the lifetime figures below are what distinguish the two.
        assert sensor.native_value == "unknown"
        attrs = sensor.extra_state_attributes
        assert attrs["window_days"] == 30
        assert attrs["sample_count"] == 0
        assert attrs["lifetime_sample_count"] == 3, (
            "lifetime figures should still resolve from full history"
        )

    def test_settings_are_looked_up_for_this_dog(self):
        coord = FakeCoordinator({"dog1": [_weight(50, 20)]})
        sensor = PawsistantWeightTrendSensor(coord, "dog1", "Fido", "Dog")
        sensor.native_value
        coord.store.get_analytics_settings.assert_called_with("dog1")

    def test_stored_threshold_is_passed_through(self):
        # +2%: stable under the default band for a 30-day window (3%), gaining
        # under an explicit 1%.
        events = {"dog1": [_weight(50.0, 20), _weight(50.5, 10), _weight(51.0, 1)]}
        coord = FakeCoordinator(events)
        coord.store.get_analytics_settings.return_value = {
            "weight_window_days": 30,
            "weight_threshold_pct": None,
        }
        assert PawsistantWeightTrendSensor(
            coord, "dog1", "Fido", "Dog"
        ).native_value == "stable"

        coord2 = FakeCoordinator(events)
        coord2.store.get_analytics_settings.return_value = {
            "weight_window_days": 30,
            "weight_threshold_pct": 1.0,
        }
        sensor2 = PawsistantWeightTrendSensor(coord2, "dog1", "Fido", "Dog")
        assert sensor2.native_value == "gaining"
        assert sensor2.extra_state_attributes["threshold_pct"] == 1.0

    def test_window_of_none_uses_all_history(self):
        coord = FakeCoordinator(
            {"dog1": [_weight(50, 900), _weight(52, 500), _weight(60, 400)]}
        )
        coord.store.get_analytics_settings.return_value = {
            "weight_window_days": None,
            "weight_threshold_pct": None,
        }
        sensor = PawsistantWeightTrendSensor(coord, "dog1", "Fido", "Dog")
        assert sensor.native_value == "gaining"
        assert sensor.extra_state_attributes["window_days"] is None

    def test_missing_store_method_falls_back_to_defaults(self):
        """A store predating this feature must not break the sensor."""
        coord = FakeCoordinator(
            {"dog1": [_weight(50, 20), _weight(55, 10), _weight(60, 1)]}
        )
        del coord.store.get_analytics_settings
        sensor = PawsistantWeightTrendSensor(coord, "dog1", "Fido", "Dog")
        assert sensor.native_value == "gaining"
        assert sensor.extra_state_attributes["window_days"] == 90

    def test_lifetime_attributes_are_exposed(self):
        coord = FakeCoordinator(
            {"dog1": [_weight(60, 300), _weight(50, 200), _weight(60, 1)]}
        )
        coord.store.get_analytics_settings.return_value = {
            "weight_window_days": 30,
            "weight_threshold_pct": None,
        }
        attrs = PawsistantWeightTrendSensor(
            coord, "dog1", "Fido", "Dog"
        ).extra_state_attributes
        # Dropped then recovered: flat across all history.
        assert attrs["lifetime_trend"] == "stable"
        assert attrs["lifetime_change_pct"] == pytest.approx(0.0)
        assert attrs["lifetime_oldest_value"] == 60
        assert attrs["lifetime_newest_value"] == 60
        assert attrs["lifetime_over_days"] == pytest.approx(299.0, abs=1.0)


class TestCacheStillCachesWithinATick:
    """The cache must still do its job: one compute per refresh, not per read."""

    def test_repeated_reads_compute_once(self, monkeypatch):
        calls = []
        real = _sensor_mod.compute_weight_trend

        def counting(events, *args, **kwargs):
            calls.append(1)
            return real(events, *args, **kwargs)

        monkeypatch.setattr(_sensor_mod, "compute_weight_trend", counting)

        coord = FakeCoordinator({"dog1": [_weight(50, 20), _weight(55, 10), _weight(60, 1)]})
        sensor = PawsistantWeightTrendSensor(coord, "dog1", "Fido", "Dog")

        sensor.native_value
        sensor.extra_state_attributes
        sensor.native_value
        assert len(calls) == 1, f"expected a single compute per refresh, got {len(calls)}"

        coord.refresh({"dog1": [_weight(50, 20), _weight(55, 10), _weight(70, 1)]})
        sensor.native_value
        sensor.extra_state_attributes
        assert len(calls) == 2, f"expected one more compute after refresh, got {len(calls)}"


class TestCoordinatorProvidesCacheKey:
    """The sensors' cache key only exists on TimestampDataUpdateCoordinator.

    Loaded separately from the sensor tests above (which stub the coordinator
    for its type annotation) so this asserts against the real class.

    Other unit-test modules force-override `homeassistant.helpers.*` in
    sys.modules at import time, so these tests install their own stubs inside
    the test body and restore what was there — never reading module-level state
    that a sibling module may have replaced.
    """

    def test_real_coordinator_exposes_last_update_success_time(self):
        """The real PawsistantCoordinator must inherit the timestamped base.

        Asserts on the resolved MRO rather than `hasattr`, so a stub that
        happens to define the attribute can't make this pass vacuously.
        """
        saved_uc = sys.modules.get("homeassistant.helpers.update_coordinator")
        saved_store = sys.modules.get("custom_components.pawsistant.store")
        for key in list(sys.modules):
            if key.startswith("custom_components.pawsistant.coordinator"):
                del sys.modules[key]

        uc_mod = types.ModuleType("homeassistant.helpers.update_coordinator")
        uc_mod.UpdateFailed = type("UpdateFailed", (Exception,), {})

        class _Plain(metaclass=_HAMeta):
            pass

        class _Timestamped(_Plain):
            last_update_success_time = None

        uc_mod.DataUpdateCoordinator = _Plain
        uc_mod.TimestampDataUpdateCoordinator = _Timestamped
        sys.modules["homeassistant.helpers.update_coordinator"] = uc_mod

        store_stub = types.ModuleType("custom_components.pawsistant.store")
        store_stub.PawsistantStore = type("PawsistantStore", (), {})
        sys.modules["custom_components.pawsistant.store"] = store_stub
        try:
            mod = _load_module(
                "custom_components.pawsistant.coordinator_under_test",
                _PKG / "coordinator.py",
            )
            assert _Timestamped in mod.PawsistantCoordinator.__mro__, (
                "PawsistantCoordinator does not extend "
                "TimestampDataUpdateCoordinator, so it has no "
                "last_update_success_time. The analytics sensors key their "
                "compute cache on that attribute; without it the key is None "
                "forever and their state freezes permanently at the first "
                "computed value."
            )
        finally:
            sys.modules.pop("custom_components.pawsistant.coordinator_under_test", None)
            if saved_uc is not None:
                sys.modules["homeassistant.helpers.update_coordinator"] = saved_uc
            if saved_store is not None:
                sys.modules["custom_components.pawsistant.store"] = saved_store
            else:
                sys.modules.pop("custom_components.pawsistant.store", None)

    def test_timestamped_base_advances_the_key_on_success(self):
        """Documents the semantics the sensors rely on.

        Mirrors HA's `TimestampDataUpdateCoordinator._async_refresh_finished`:
        the key is None until the first successful refresh, then advances. A
        key that never advances is exactly the frozen-state bug.
        """

        class Timestamped:
            last_update_success_time = None

            def __init__(self) -> None:
                self.last_update_success = True

            def _async_refresh_finished(self) -> None:
                if self.last_update_success:
                    self.last_update_success_time = _utcnow()

        coord = Timestamped()
        assert coord.last_update_success_time is None

        coord._async_refresh_finished()
        first = coord.last_update_success_time
        assert first is not None

        # A failed refresh must NOT advance the key — stale data keeps its
        # matching cache entry rather than being recomputed from nothing.
        coord.last_update_success = False
        coord._async_refresh_finished()
        assert coord.last_update_success_time == first
