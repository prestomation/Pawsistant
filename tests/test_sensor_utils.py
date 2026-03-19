"""Tests for pure sensor utility functions (no HA runtime needed)."""

from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import pytest

# Adjust sys.path so we can import without installing HA
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# We need to mock homeassistant modules since HA is not installed
# Use a universal mock that auto-creates submodules on demand
import types
import zoneinfo
from enum import Enum

class _HAModuleFinder:
    """Auto-create mock modules for any homeassistant.* import."""
    _cache = {}
    
    @classmethod
    def find_module(cls, name, path=None):
        if name == 'homeassistant' or name.startswith('homeassistant.'):
            return cls
        return None
    
    @classmethod
    def load_module(cls, name):
        if name in sys.modules:
            return sys.modules[name]
        mod = types.ModuleType(name)
        # Add commonly needed attributes
        mod.__path__ = []
        mod.__package__ = name
        sys.modules[name] = mod
        cls._cache[name] = mod
        return mod

sys.meta_path.insert(0, _HAModuleFinder)

# Pre-populate critical HA mock attributes
import homeassistant.util.dt as ha_dt
ha_dt.now = lambda: __import__('datetime').datetime.now(__import__('datetime').timezone.utc)
ha_dt.DEFAULT_TIME_ZONE = zoneinfo.ZoneInfo('America/Los_Angeles')

import homeassistant.components.sensor as ha_sensor
class SensorDeviceClass(Enum):
    TIMESTAMP = 'timestamp'
    BATTERY = 'battery'
    TEMPERATURE = 'temperature'
class SensorStateClass(Enum):
    MEASUREMENT = 'measurement'
    TOTAL = 'total'
ha_sensor.SensorDeviceClass = SensorDeviceClass
ha_sensor.SensorStateClass = SensorStateClass
ha_sensor.SensorEntity = type('SensorEntity', (), {})
ha_sensor.SensorEntityDescription = type('SensorEntityDescription', (), {'__init_subclass__': lambda **kw: None})

import homeassistant.helpers.update_coordinator as ha_uc
ha_uc.CoordinatorEntity = type('CoordinatorEntity', (), {'__class_getitem__': classmethod(lambda cls, x: cls)})

from custom_components.doglog.sensor import _to_datetime, _count_today, _get_most_recent_event


def make_event(event_type: EventType, timestamp: datetime) -> DogEvent:
    return DogEvent(
        id='test-id',
        event_type=event_type,
        timestamp=timestamp,
        pet_id='dog-1',
        pet_name='Sharky',
    )


class TestToDatetime:
    def test_passthrough_aware_datetime(self):
        dt = datetime(2026, 3, 16, 12, 0, tzinfo=timezone.utc)
        result = _to_datetime(dt)
        assert result == dt
        assert result.tzinfo is not None

    def test_numeric_seconds(self):
        ts = 1773609109  # ~March 2026
        result = _to_datetime(ts)
        assert result.tzinfo is not None
        assert result.year == 2026

    def test_numeric_milliseconds(self):
        ts = 1773609109 * 1000
        result = _to_datetime(ts)
        assert result.tzinfo is not None
        assert result.year == 2026


class TestCountToday:
    def test_counts_events_today(self):
        now_pacific = datetime.now(PACIFIC)
        today_noon = now_pacific.replace(hour=12, minute=0, second=0, microsecond=0)
        events = [
            make_event(EventType.POOP, today_noon.astimezone(timezone.utc)),
            make_event(EventType.POOP, today_noon.astimezone(timezone.utc) - timedelta(hours=2)),
            make_event(EventType.PEE, today_noon.astimezone(timezone.utc)),
        ]
        with patch('custom_components.doglog.sensor.dt_util.now', return_value=now_pacific):
            assert _count_today(events, EventType.POOP) == 2
            assert _count_today(events, EventType.PEE) == 1

    def test_excludes_yesterday(self):
        now_pacific = datetime.now(PACIFIC)
        yesterday = now_pacific - timedelta(days=1)
        events = [make_event(EventType.POOP, yesterday.astimezone(timezone.utc))]
        with patch('custom_components.doglog.sensor.dt_util.now', return_value=now_pacific):
            assert _count_today(events, EventType.POOP) == 0

    def test_timezone_boundary(self):
        # 11pm Pacific = next day UTC — should count as today in Pacific
        pacific_11pm = datetime(2026, 3, 15, 23, 0, tzinfo=PACIFIC)
        events = [make_event(EventType.POOP, pacific_11pm.astimezone(timezone.utc))]
        with patch('custom_components.doglog.sensor.dt_util.now', return_value=pacific_11pm):
            assert _count_today(events, EventType.POOP) == 1


class TestGetMostRecentEvent:
    def test_returns_most_recent(self):
        """Events are pre-sorted newest-first from the API."""
        older = make_event(EventType.FOOD, datetime(2026, 3, 15, 10, tzinfo=timezone.utc))
        newer = make_event(EventType.FOOD, datetime(2026, 3, 16, 10, tzinfo=timezone.utc))
        assert _get_most_recent_event([newer, older], EventType.FOOD) == newer

    def test_returns_none_when_empty(self):
        assert _get_most_recent_event([], EventType.FOOD) is None

    def test_filters_by_type(self):
        food = make_event(EventType.FOOD, datetime(2026, 3, 16, 10, tzinfo=timezone.utc))
        poop = make_event(EventType.POOP, datetime(2026, 3, 16, 11, tzinfo=timezone.utc))
        assert _get_most_recent_event([food, poop], EventType.FOOD) == food
