"""Tests for pure sensor utility functions."""
# These tests use real HA modules — skip the mock_homeassistant autouse fixture.
import pytest
pytestmark = pytest.mark.real_ha

from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import zoneinfo

from homeassistant.util import dt as dt_util

from custom_components.pawsistant.sensor import (
    _to_datetime,
    _count_today,
    _get_most_recent_event,
    _per_type_metric_maps,
)
from custom_components.pawsistant.store import _parse_timestamp

PACIFIC = zoneinfo.ZoneInfo("America/Los_Angeles")


def make_event(event_type: str, timestamp: datetime) -> dict:
    return {
        "id": "test-id",
        "event_type": event_type,
        "timestamp": timestamp.isoformat(),
        "dog_id": "dog-1",
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
        with patch("custom_components.pawsistant.sensor.dt_util.now", return_value=now_pacific), \
             patch("custom_components.pawsistant.sensor.dt_util.DEFAULT_TIME_ZONE", PACIFIC):
            assert _count_today(events, "poop") == 2
            assert _count_today(events, "pee") == 1

    def test_excludes_yesterday(self):
        now_pacific = datetime.now(PACIFIC)
        yesterday = now_pacific - timedelta(days=1)
        events = [make_event("poop", yesterday.astimezone(timezone.utc))]
        with patch("custom_components.pawsistant.sensor.dt_util.now", return_value=now_pacific), \
             patch("custom_components.pawsistant.sensor.dt_util.DEFAULT_TIME_ZONE", PACIFIC):
            assert _count_today(events, "poop") == 0

    def test_timezone_boundary(self):
        # 11pm Pacific = next day UTC — should count as today in Pacific
        pacific_11pm = datetime(2026, 3, 15, 23, 0, tzinfo=PACIFIC)
        events = [make_event("poop", pacific_11pm.astimezone(timezone.utc))]
        with patch("custom_components.pawsistant.sensor.dt_util.now", return_value=pacific_11pm), \
             patch("custom_components.pawsistant.sensor.dt_util.DEFAULT_TIME_ZONE", PACIFIC):
            assert _count_today(events, "poop") == 1


class TestPerTypeMetricMaps:
    """The timeline sensor exposes per-type maps so the card can render
    daily_count / days_since / hours_since for *every* event type (built-in
    and custom), not just pee/poop."""

    def test_covers_custom_and_builtin_types(self):
        now_pacific = datetime.now(PACIFIC)
        today_noon = now_pacific.replace(hour=12, minute=0, second=0, microsecond=0)
        events = [
            make_event("walk", today_noon.astimezone(timezone.utc)),
            make_event("walk", today_noon.astimezone(timezone.utc) - timedelta(hours=1)),
            make_event("playtime", today_noon.astimezone(timezone.utc)),  # custom type
        ]
        with patch("custom_components.pawsistant.sensor.dt_util.now", return_value=now_pacific), \
             patch("custom_components.pawsistant.sensor.dt_util.DEFAULT_TIME_ZONE", PACIFIC):
            daily_counts, days_since, last_event_ts = _per_type_metric_maps(events)
        assert daily_counts == {"walk": 2, "playtime": 1}
        # days_since ~0 (today) and present for both, including the custom type.
        # (Exact value depends on wall-clock vs. the noon timestamp, so allow a
        # sub-day window rather than asserting precisely 0.)
        assert set(days_since) == {"walk", "playtime"}
        assert abs(days_since["walk"]) < 1.0
        assert set(last_event_ts) == {"walk", "playtime"}

    def test_daily_count_zero_when_no_events_today(self):
        now_pacific = datetime.now(PACIFIC)
        yesterday = now_pacific - timedelta(days=1, hours=2)
        events = [make_event("vaccine", yesterday.astimezone(timezone.utc))]
        with patch("custom_components.pawsistant.sensor.dt_util.now", return_value=now_pacific), \
             patch("custom_components.pawsistant.sensor.dt_util.DEFAULT_TIME_ZONE", PACIFIC):
            daily_counts, days_since, last_event_ts = _per_type_metric_maps(events)
        # Surfaced as 0 (not absent) so a daily_count badge reads "0 today".
        assert daily_counts == {"vaccine": 0}
        assert days_since["vaccine"] >= 1.0
        assert "vaccine" in last_event_ts

    def test_empty_events(self):
        assert _per_type_metric_maps([]) == ({}, {}, {})

    def test_most_recent_timestamp_per_type(self):
        older = make_event("food", datetime(2026, 3, 15, 10, tzinfo=timezone.utc))
        newer = make_event("food", datetime(2026, 3, 16, 10, tzinfo=timezone.utc))
        with patch("custom_components.pawsistant.sensor.dt_util.now",
                   return_value=datetime(2026, 3, 17, 10, tzinfo=timezone.utc)), \
             patch("custom_components.pawsistant.sensor.dt_util.DEFAULT_TIME_ZONE", timezone.utc):
            _, days_since, last_event_ts = _per_type_metric_maps([older, newer])
        # Most recent (3/16) wins → ~1 day since, ts reflects the newer event.
        assert days_since["food"] == 1.0
        assert last_event_ts["food"].startswith("2026-03-16T10:00:00")


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

    def test_returns_newest_when_unsorted(self):
        """Bug: linear scan returned first match instead of newest.

        Reproduces the exact scenario from the bug report: list is NOT sorted
        newest-first, so the first pee (01:00) must NOT win over the later one (04:00).
        """
        e1 = {"id": "1", "event_type": "pee", "timestamp": "2026-04-13T01:00:00+00:00"}
        e2 = {"id": "2", "event_type": "food", "timestamp": "2026-04-13T02:00:00+00:00"}
        e3 = {"id": "3", "event_type": "pee", "timestamp": "2026-04-13T04:00:00+00:00"}
        result = _get_most_recent_event([e1, e2, e3], "pee")
        assert result is not None
        assert result["id"] == "3", (
            f"Expected id=3 (04:00 UTC) but got id={result['id']} — "
            "linear scan returned first match instead of newest"
        )

    def test_mixed_tz_offsets_picks_true_newest(self):
        """Mixed UTC offsets that compare incorrectly as strings must still yield correct result.

        '2026-04-13T01:00:00+00:00' > '2026-04-13T04:00:00-04:00' lexicographically,
        but the -04:00 event is actually 08:00 UTC — 7 hours later.
        """
        # 01:00 UTC
        utc_event = {"id": "utc", "event_type": "walk", "timestamp": "2026-04-13T01:00:00+00:00"}
        # 04:00 local (ET -04:00) = 08:00 UTC — this is actually NEWER
        et_event = {"id": "et", "event_type": "walk", "timestamp": "2026-04-13T04:00:00-04:00"}
        result = _get_most_recent_event([utc_event, et_event], "walk")
        assert result is not None
        assert result["id"] == "et", (
            f"Expected et event (08:00 UTC) but got {result['id']} — "
            "string comparison of mixed offsets produced wrong ordering"
        )


class TestParseTimestampSort:
    """Prove that string sort of mixed-offset timestamps gives wrong order,
    and that _parse_timestamp-based sort gives the correct order."""

    def test_string_sort_is_wrong_for_mixed_offsets(self):
        """`sorted(..., key=lambda e: e.get('timestamp'))` gives wrong order."""
        events = [
            {"id": "utc", "timestamp": "2026-04-13T01:00:00+00:00"},  # 01:00 UTC
            {"id": "et", "timestamp": "2026-04-13T04:00:00-04:00"},   # 08:00 UTC (newer)
        ]
        string_sorted = sorted(events, key=lambda e: e.get("timestamp", ""), reverse=True)
        # String comparison: "2026-04-13T04:00:00-04:00" > "2026-04-13T01:00:00+00:00"
        # (because '4' > '1' in the hour field), so utc paradoxically sorts first.
        # The utc event is at 01:00 but sorts first — demonstrating the bug.
        assert string_sorted[0]["id"] == "et"  # lexicographically first (but wrong: et is actually NEWER, so this happens to be coincidentally correct here...)
        # The real problem shows with a different pair:
        events2 = [
            {"id": "late_utc", "timestamp": "2026-04-13T05:00:00+00:00"},  # 05:00 UTC (newer)
            {"id": "early_et", "timestamp": "2026-04-13T09:00:00-04:00"},  # 13:00 UTC (even newer)
        ]
        # String comparison: "2026-04-13T09:00:00-04:00" > "2026-04-13T05:00:00+00:00" — correct accident
        # Tricky case: +00:00 event that is actually later than a -04:00 event
        events3 = [
            {"id": "newer_utc", "timestamp": "2026-04-13T10:00:00+00:00"},  # 10:00 UTC (newer)
            {"id": "older_et", "timestamp": "2026-04-13T08:00:00-04:00"},   # 12:00 UTC (even newer!)
        ]
        string_sorted3 = sorted(events3, key=lambda e: e.get("timestamp", ""), reverse=True)
        # String: "2026-04-13T10:00:00+00:00" vs "2026-04-13T08:00:00-04:00"
        # '10' > '08' so newer_utc sorts first, but older_et is 12:00 UTC (actually newest)
        assert string_sorted3[0]["id"] == "newer_utc"  # string sort picks this...
        # ...but it's wrong: older_et (08:00-04:00 = 12:00 UTC) is actually newer
        assert _parse_timestamp("2026-04-13T08:00:00-04:00") > _parse_timestamp("2026-04-13T10:00:00+00:00")

    def test_parse_timestamp_sort_correct_for_mixed_offsets(self):
        """_parse_timestamp-keyed sort produces correct newest-first order."""
        events = [
            {"id": "older", "timestamp": "2026-04-13T10:00:00+00:00"},  # 10:00 UTC
            {"id": "newer", "timestamp": "2026-04-13T08:00:00-04:00"},  # 12:00 UTC — actually newer
        ]
        dt_sorted = sorted(events, key=lambda e: _parse_timestamp(e.get("timestamp", "")), reverse=True)
        assert dt_sorted[0]["id"] == "newer"
