"""Tests for pure sensor utility functions (no HA runtime needed)."""

from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import pytest

# Adjust sys.path so we can import without installing HA
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# We need to mock homeassistant modules since HA is not installed
import types

# Create minimal HA mock so sensor.py can be imported
ha_mock = types.ModuleType('homeassistant')
ha_util = types.ModuleType('homeassistant.util')
ha_dt = types.ModuleType('homeassistant.util.dt')
ha_components = types.ModuleType('homeassistant.components')
ha_sensor = types.ModuleType('homeassistant.components.sensor')
ha_core = types.ModuleType('homeassistant.core')
ha_config_entries = types.ModuleType('homeassistant.config_entries')
ha_helpers = types.ModuleType('homeassistant.helpers')
ha_entity = types.ModuleType('homeassistant.helpers.entity')
ha_entity_platform = types.ModuleType('homeassistant.helpers.entity_platform')
ha_update_coordinator = types.ModuleType('homeassistant.helpers.update_coordinator')

# Provide stub classes/values
import zoneinfo

PACIFIC = zoneinfo.ZoneInfo('America/Los_Angeles')
ha_dt.DEFAULT_TIME_ZONE = PACIFIC
ha_dt.now = lambda: datetime.now(PACIFIC)

from enum import Enum
class SensorStateClass(str, Enum):
    MEASUREMENT = 'measurement'
    TOTAL = 'total'
    TOTAL_INCREASING = 'total_increasing'
class SensorDeviceClass(str, Enum):
    TIMESTAMP = 'timestamp'

ha_sensor.SensorStateClass = SensorStateClass
ha_sensor.SensorDeviceClass = SensorDeviceClass
ha_sensor.SensorEntity = object
ha_sensor.SensorEntityDescription = object

ha_core.HomeAssistant = object
ha_core.ServiceCall = object
ha_config_entries.ConfigEntry = object
ha_helpers.entity = ha_entity
ha_helpers.entity_platform = ha_entity_platform
ha_entity.EntityDescription = object
ha_entity_platform.AddEntitiesCallback = object
class _Subscriptable(type):
    def __getitem__(cls, item):
        return cls

class _CoordinatorEntity(metaclass=_Subscriptable):
    pass

class _DataUpdateCoordinator(metaclass=_Subscriptable):
    pass

ha_update_coordinator.CoordinatorEntity = _CoordinatorEntity
ha_update_coordinator.DataUpdateCoordinator = _DataUpdateCoordinator
ha_update_coordinator.UpdateFailed = type('UpdateFailed', (Exception,), {})

ha_exceptions = types.ModuleType('homeassistant.exceptions')
ha_exceptions.ConfigEntryAuthFailed = type('ConfigEntryAuthFailed', (Exception,), {})

ha_device_registry = types.ModuleType('homeassistant.helpers.device_registry')
ha_device_registry.DeviceInfo = dict

ha_cv = types.ModuleType('homeassistant.helpers.config_validation')
ha_cv.string = str
ha_cv.boolean = bool
ha_event = types.ModuleType('homeassistant.helpers.event')
ha_event.async_call_later = lambda *a, **k: None
ha_http = types.ModuleType('homeassistant.components.http')

sys.modules['homeassistant.helpers.config_validation'] = ha_cv
sys.modules['homeassistant.helpers.event'] = ha_event
sys.modules['homeassistant.components.http'] = ha_http

sys.modules['homeassistant'] = ha_mock
sys.modules['homeassistant.util'] = ha_util
sys.modules['homeassistant.util.dt'] = ha_dt
sys.modules['homeassistant.components'] = ha_components
sys.modules['homeassistant.components.sensor'] = ha_sensor
sys.modules['homeassistant.exceptions'] = ha_exceptions
sys.modules['homeassistant.helpers.device_registry'] = ha_device_registry
sys.modules['homeassistant.core'] = ha_core
sys.modules['homeassistant.config_entries'] = ha_config_entries
sys.modules['homeassistant.helpers'] = ha_helpers
sys.modules['homeassistant.helpers.entity'] = ha_entity
sys.modules['homeassistant.helpers.entity_platform'] = ha_entity_platform
sys.modules['homeassistant.helpers.update_coordinator'] = ha_update_coordinator

from pydoglog.models import DogEvent, EventType
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
