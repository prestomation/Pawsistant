"""Tests for pure sensor utility functions (no HA runtime needed)."""

from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import pytest

# Adjust sys.path so we can import without installing HA
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# homeassistant is installed in the test environment
from pydoglog.models import DogEvent, EventType
import zoneinfo
PACIFIC = zoneinfo.ZoneInfo('America/Los_Angeles')
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
