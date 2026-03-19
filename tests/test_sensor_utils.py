"""Tests for pure sensor utility functions."""

from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import pytest
import zoneinfo

from homeassistant.util import dt as dt_util

from custom_components.doglog.sensor import _to_datetime, _count_today, _get_most_recent_event

PACIFIC = zoneinfo.ZoneInfo("America/Los_Angeles")


def make_event(event_type: str, timestamp: datetime) -> dict:
    return {
        "id": "test-id",
        "event_type": event_type,
        "timestamp": timestamp.isoformat(),
        "pet_id": "dog-1",
    }


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
            make_event("poop", today_noon.astimezone(timezone.utc)),
            make_event("poop", today_noon.astimezone(timezone.utc) - timedelta(hours=2)),
            make_event("pee", today_noon.astimezone(timezone.utc)),
        ]
        with patch("custom_components.doglog.sensor.dt_util.now", return_value=now_pacific):
            assert _count_today(events, "poop") == 2
            assert _count_today(events, "pee") == 1

    def test_excludes_yesterday(self):
        now_pacific = datetime.now(PACIFIC)
        yesterday = now_pacific - timedelta(days=1)
        events = [make_event("poop", yesterday.astimezone(timezone.utc))]
        with patch("custom_components.doglog.sensor.dt_util.now", return_value=now_pacific):
            assert _count_today(events, "poop") == 0

    def test_timezone_boundary(self):
        # 11pm Pacific = next day UTC — should count as today in Pacific
        pacific_11pm = datetime(2026, 3, 15, 23, 0, tzinfo=PACIFIC)
        events = [make_event("poop", pacific_11pm.astimezone(timezone.utc))]
        with patch("custom_components.doglog.sensor.dt_util.now", return_value=pacific_11pm):
            assert _count_today(events, "poop") == 1


class TestGetMostRecentEvent:
    def test_returns_most_recent(self):
        """Events are pre-sorted newest-first from the API."""
        older = make_event("food", datetime(2026, 3, 15, 10, tzinfo=timezone.utc))
        newer = make_event("food", datetime(2026, 3, 16, 10, tzinfo=timezone.utc))
        assert _get_most_recent_event([newer, older], "food") == newer

    def test_returns_none_when_empty(self):
        assert _get_most_recent_event([], "food") is None

    def test_filters_by_type(self):
        food = make_event("food", datetime(2026, 3, 16, 10, tzinfo=timezone.utc))
        poop = make_event("poop", datetime(2026, 3, 16, 11, tzinfo=timezone.utc))
        assert _get_most_recent_event([food, poop], "food") == food
