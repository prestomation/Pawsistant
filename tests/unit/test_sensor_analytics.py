"""Unit tests for sensor_analytics.py — pure analytics functions.

No Home Assistant imports; these functions operate on plain event dicts.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import importlib.util

import pytest

# Load sensor_analytics.py directly to avoid importing the HA-dependent
# package __init__.py.  This mirrors the pattern used by other unit tests
# in this repo (see test_event_types_registry.py).
_analytics_path = (
    Path(__file__).resolve().parent.parent.parent
    / "custom_components"
    / "pawsistant"
    / "sensor_analytics.py"
)
_spec = importlib.util.spec_from_file_location("sensor_analytics", _analytics_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

compute_weight_trend = _mod.compute_weight_trend
compute_sick_frequency = _mod.compute_sick_frequency


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _ev(
    event_type: str,
    timestamp: str,
    value: float | None = None,
    dog_id: str = "dog1",
) -> dict:
    """Build a minimal event dict."""
    e: dict = {
        "event_type": event_type,
        "timestamp": timestamp,
        "dog_id": dog_id,
        "id": "x",
    }
    if value is not None:
        e["value"] = value
    return e


def _ts(days_ago: int = 0, hour: int = 12) -> str:
    """ISO timestamp N days ago at a given hour (UTC)."""
    dt = datetime.now(tz=timezone.utc) - timedelta(days=days_ago)
    dt = dt.replace(hour=hour, minute=0, second=0, microsecond=0)
    return dt.isoformat()


# ---------------------------------------------------------------------------
# TestComputeWeightTrend
# ---------------------------------------------------------------------------


class TestComputeWeightTrend:
    """Tests for compute_weight_trend()."""

    def test_not_enough_points_returns_unknown(self) -> None:
        events = [_ev("weight", _ts(1), value=50.0)]
        result = compute_weight_trend(events)
        assert result["trend"] == "unknown"
        assert result["change_pct"] is None
        assert result["sample_count"] is None

    def test_stable_weight(self) -> None:
        events = [_ev("weight", _ts(i * 7), value=50.0) for i in range(5)]
        result = compute_weight_trend(events)
        assert result["trend"] == "stable"
        assert result["change_pct"] == pytest.approx(0.0, abs=0.01)

    def test_gaining_weight(self) -> None:
        values = [50.0, 53.0, 56.0, 60.0]
        events = [
            _ev("weight", _ts(30 - i * 10), value=v)
            for i, v in enumerate(values)
        ]
        result = compute_weight_trend(events)
        assert result["trend"] == "gaining"
        assert result["change_pct"] > 5.0

    def test_losing_weight(self) -> None:
        values = [60.0, 57.0, 54.0, 50.0]
        events = [
            _ev("weight", _ts(30 - i * 10), value=v)
            for i, v in enumerate(values)
        ]
        result = compute_weight_trend(events)
        assert result["trend"] == "losing"
        assert result["change_pct"] < -5.0

    def test_ignores_non_weight_events(self) -> None:
        events = [_ev("food", _ts(i), value=1.0) for i in range(10)]
        events.append(_ev("weight", _ts(0), value=50.0))
        result = compute_weight_trend(events)
        assert result["trend"] == "unknown"

    def test_attributes_contain_last_n_values(self) -> None:
        events = [
            _ev("weight", _ts(20), value=50.0),
            _ev("weight", _ts(10), value=52.0),
            _ev("weight", _ts(0), value=54.0),
        ]
        result = compute_weight_trend(events)
        assert result["sample_count"] == 3
        assert result["oldest_value"] == 50.0
        assert result["newest_value"] == 54.0


# ---------------------------------------------------------------------------
# TestComputeSickFrequency
# ---------------------------------------------------------------------------


class TestComputeSickFrequency:
    """Tests for compute_sick_frequency()."""

    def test_no_sick_events_returns_zero(self) -> None:
        events = [_ev("food", _ts(5))]
        result = compute_sick_frequency(events)
        assert result["count_current"] == 0
        assert result["count_previous"] == 0

    def test_counts_recent_sick_events(self) -> None:
        events = [
            _ev("sick", _ts(5)),
            _ev("sick", _ts(10)),
            _ev("sick", _ts(20)),
            _ev("food", _ts(3)),
        ]
        result = compute_sick_frequency(events)
        assert result["count_current"] == 3

    def test_counts_previous_window(self) -> None:
        events = [
            _ev("sick", _ts(10)),   # current window (last 30d)
            _ev("sick", _ts(40)),   # previous window (30-60d)
            _ev("sick", _ts(50)),   # previous window (30-60d)
        ]
        result = compute_sick_frequency(events)
        assert result["count_current"] == 1
        assert result["count_previous"] == 2

    def test_old_events_outside_both_windows_ignored(self) -> None:
        events = [_ev("sick", _ts(100))]
        result = compute_sick_frequency(events)
        assert result["count_current"] == 0
        assert result["count_previous"] == 0

    def test_cluster_detection(self) -> None:
        # 3 sick events within 7 days of each other (a cluster)
        # plus 1 isolated event well outside the 7-day window
        events = [
            _ev("sick", _ts(3)),
            _ev("sick", _ts(5)),
            _ev("sick", _ts(7)),
            _ev("sick", _ts(25)),  # isolated -- gap > 7 days from nearest cluster member
        ]
        result = compute_sick_frequency(events)
        assert result["cluster_size"] >= 3
