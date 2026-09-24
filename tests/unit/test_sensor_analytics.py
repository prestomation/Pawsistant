"""Unit tests for sensor_analytics.py — pure analytics functions.

No Home Assistant imports; these functions operate on plain event dicts.
"""

from __future__ import annotations

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
compute_routine_peaks = _mod.compute_routine_peaks


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


def _ts(days_ago: int = 0, hour: int = 12, ref: datetime | None = None) -> str:
    """ISO timestamp N days ago at a given hour (UTC).

    Args:
        days_ago: How many days in the past.
        hour:     Hour-of-day (0-23).
        ref:      Reference "now" for deterministic tests.
                  Falls back to ``datetime.now(tz=timezone.utc)``.
    """
    base = ref or datetime.now(tz=timezone.utc)
    dt = base - timedelta(days=days_ago)
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
        # sample_count reports the true number of readings even when there are
        # too few to judge, so the sensor can explain the "unknown" instead of
        # just showing a blank.
        assert result["sample_count"] == 1

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
        assert result["over_days"] == pytest.approx(30.0, abs=1.0)

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
# TestWeightTrendWindow
# ---------------------------------------------------------------------------


class TestWeightTrendWindow:
    """The trend is measured over a configurable recent window.

    Comparing oldest-to-newest across all history gets less useful the longer
    an integration runs: a dog that lost weight and regained it reads "stable",
    and the comparison span silently widens forever. The headline trend is
    therefore windowed, with the full-history figures kept as `lifetime_*`.

    The window is strict — readings outside it are excluded even when that
    leaves too few points to judge. Widening it automatically would override
    the interval the user deliberately chose.
    """

    def test_window_excludes_older_readings(self) -> None:
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        events = [
            # Old, heavier readings — outside a 30-day window.
            _ev("weight", _ts(200, ref=now), value=80.0),
            _ev("weight", _ts(150, ref=now), value=75.0),
            # Recent readings, gaining.
            _ev("weight", _ts(20, ref=now), value=50.0),
            _ev("weight", _ts(10, ref=now), value=53.0),
            _ev("weight", _ts(1, ref=now), value=56.0),
        ]
        result = compute_weight_trend(events, window_days=30, now=now)
        assert result["trend"] == "gaining", (
            "window should be measured over recent readings only"
        )
        assert result["sample_count"] == 3
        assert result["oldest_value"] == 50.0
        assert result["newest_value"] == 56.0

    def test_lifetime_figures_reported_alongside_window(self) -> None:
        """Full history stays available — nothing is lost by windowing."""
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        events = [
            _ev("weight", _ts(300, ref=now), value=50.0),
            _ev("weight", _ts(200, ref=now), value=50.0),
            _ev("weight", _ts(20, ref=now), value=50.0),
            _ev("weight", _ts(10, ref=now), value=53.0),
            _ev("weight", _ts(1, ref=now), value=56.0),
        ]
        result = compute_weight_trend(events, window_days=30, now=now)
        assert result["trend"] == "gaining"
        # Across all history the net change is +12%, but the shape differs and
        # the span is 299 days rather than 19.
        assert result["lifetime_sample_count"] == 5
        assert result["lifetime_oldest_value"] == 50.0
        assert result["lifetime_newest_value"] == 56.0
        assert result["lifetime_over_days"] == pytest.approx(299.0, abs=1.0)

    def test_recovered_weight_reads_stable_lifetime_but_gaining_recently(self) -> None:
        """The exact case that motivated windowing.

        A dog that dropped weight and recovered nets out flat across all
        history, hiding an active upward trend.
        """
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        events = [
            _ev("weight", _ts(300, ref=now), value=60.0),
            _ev("weight", _ts(200, ref=now), value=50.0),
            _ev("weight", _ts(20, ref=now), value=54.0),
            _ev("weight", _ts(10, ref=now), value=57.0),
            _ev("weight", _ts(1, ref=now), value=60.0),
        ]
        result = compute_weight_trend(events, window_days=30, now=now)
        assert result["trend"] == "gaining"
        assert result["lifetime_trend"] == "stable"

    def test_sparse_window_returns_unknown_without_widening(self) -> None:
        """A strict window must not silently expand to find enough points."""
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        events = [
            _ev("weight", _ts(200, ref=now), value=50.0),
            _ev("weight", _ts(150, ref=now), value=52.0),
            _ev("weight", _ts(100, ref=now), value=54.0),
            _ev("weight", _ts(5, ref=now), value=60.0),
        ]
        result = compute_weight_trend(events, window_days=30, now=now)
        assert result["trend"] == "unknown"
        assert result["change_pct"] is None
        # Attributes must explain WHY it is unknown, so a blank sensor is
        # legible as "not enough readings in your window" rather than broken.
        assert result["sample_count"] == 1
        assert result["window_days"] == 30
        # Lifetime figures still resolve — the history exists.
        assert result["lifetime_trend"] == "gaining"
        assert result["lifetime_sample_count"] == 4

    def test_reading_exactly_on_window_boundary_is_included(self) -> None:
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        events = [
            _ev("weight", _ts(30, ref=now), value=50.0),
            _ev("weight", _ts(15, ref=now), value=53.0),
            _ev("weight", _ts(1, ref=now), value=56.0),
        ]
        result = compute_weight_trend(events, window_days=30, now=now)
        assert result["sample_count"] == 3, "boundary reading should be inside"
        assert result["trend"] == "gaining"

    def test_window_days_none_means_all_history(self) -> None:
        """Opting out of windowing keeps the original behaviour."""
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        events = [
            _ev("weight", _ts(900, ref=now), value=50.0),
            _ev("weight", _ts(500, ref=now), value=52.0),
            _ev("weight", _ts(1, ref=now), value=54.0),
        ]
        result = compute_weight_trend(events, window_days=None, now=now)
        assert result["sample_count"] == 3
        assert result["trend"] == "gaining"
        assert result["window_days"] is None


class TestWeightTrendThreshold:
    """The gaining/losing band is configurable, and defaults by window length.

    A 5% shift over a year is unremarkable growth; the same 5% inside a week
    warrants a vet call. A single fixed threshold would under-report change on
    short windows, so the default scales with the window.
    """

    def test_explicit_threshold_is_honoured(self) -> None:
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        events = [
            _ev("weight", _ts(20, ref=now), value=50.0),
            _ev("weight", _ts(10, ref=now), value=50.5),
            _ev("weight", _ts(1, ref=now), value=51.0),
        ]
        # +2% — under the 5% default, over an explicit 1%.
        assert compute_weight_trend(
            events, window_days=30, now=now
        )["trend"] == "stable"
        assert compute_weight_trend(
            events, window_days=30, threshold_pct=1.0, now=now
        )["trend"] == "gaining"

    def test_threshold_is_reported(self) -> None:
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        events = [_ev("weight", _ts(i, ref=now), value=50.0) for i in (20, 10, 1)]
        result = compute_weight_trend(
            events, window_days=30, threshold_pct=2.5, now=now
        )
        assert result["threshold_pct"] == 2.5

    @pytest.mark.parametrize(
        ("window_days", "expected"),
        [
            (7, 2.0),
            (14, 2.0),
            (30, 3.0),
            (90, 3.0),
            (180, 5.0),
            (365, 5.0),
            (None, 5.0),
        ],
    )
    def test_default_threshold_scales_with_window(
        self, window_days: int | None, expected: float
    ) -> None:
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        events = [_ev("weight", _ts(i, ref=now), value=50.0) for i in (3, 2, 1)]
        result = compute_weight_trend(events, window_days=window_days, now=now)
        assert result["threshold_pct"] == expected

    def test_short_window_flags_change_a_fixed_5pct_band_would_miss(self) -> None:
        """Regression guard for the under-reporting the scaling prevents."""
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        events = [
            _ev("weight", _ts(6, ref=now), value=50.0),
            _ev("weight", _ts(3, ref=now), value=49.0),
            _ev("weight", _ts(1, ref=now), value=48.5),
        ]
        # -3% in under a week: inside a flat 5% band, outside the 2% default
        # that a 7-day window gets.
        result = compute_weight_trend(events, window_days=7, now=now)
        assert result["trend"] == "losing"
        assert result["change_pct"] == pytest.approx(-3.0, abs=0.01)


# ---------------------------------------------------------------------------
# TestComputeSickFrequency
# ---------------------------------------------------------------------------


class TestComputeSickFrequency:
    """Tests for compute_sick_frequency()."""

    def test_no_sick_events_returns_zero(self) -> None:
        frozen_now = datetime.now(tz=timezone.utc)
        events = [_ev("food", _ts(5, ref=frozen_now))]
        result = compute_sick_frequency(events, now=frozen_now)
        assert result["count_current"] == 0
        assert result["count_previous"] == 0

    def test_counts_recent_sick_events(self) -> None:
        frozen_now = datetime.now(tz=timezone.utc)
        events = [
            _ev("sick", _ts(5, ref=frozen_now)),
            _ev("sick", _ts(10, ref=frozen_now)),
            _ev("sick", _ts(20, ref=frozen_now)),
            _ev("food", _ts(3, ref=frozen_now)),
        ]
        result = compute_sick_frequency(events, now=frozen_now)
        assert result["count_current"] == 3
        assert result["days_since_last"] == pytest.approx(5.0, abs=1.0)

    def test_counts_previous_window(self) -> None:
        frozen_now = datetime.now(tz=timezone.utc)
        events = [
            _ev("sick", _ts(10, ref=frozen_now)),   # current window (last 30d)
            _ev("sick", _ts(40, ref=frozen_now)),   # previous window (30-60d)
            _ev("sick", _ts(50, ref=frozen_now)),   # previous window (30-60d)
        ]
        result = compute_sick_frequency(events, now=frozen_now)
        assert result["count_current"] == 1
        assert result["count_previous"] == 2

    def test_old_events_outside_both_windows_ignored(self) -> None:
        frozen_now = datetime.now(tz=timezone.utc)
        events = [_ev("sick", _ts(100, ref=frozen_now))]
        result = compute_sick_frequency(events, now=frozen_now)
        assert result["count_current"] == 0
        assert result["count_previous"] == 0

    def test_cluster_detection(self) -> None:
        frozen_now = datetime.now(tz=timezone.utc)
        # 3 sick events within 7 days of each other (a cluster)
        # plus 1 isolated event well outside the 7-day window
        events = [
            _ev("sick", _ts(3, ref=frozen_now)),
            _ev("sick", _ts(5, ref=frozen_now)),
            _ev("sick", _ts(7, ref=frozen_now)),
            _ev("sick", _ts(25, ref=frozen_now)),  # isolated -- gap > 7 days from nearest cluster member
        ]
        result = compute_sick_frequency(events, now=frozen_now)
        assert result["cluster_size"] == 3


# ---------------------------------------------------------------------------
# TestComputeRoutinePeaks
# ---------------------------------------------------------------------------


class TestComputeRoutinePeaks:
    """Tests for compute_routine_peaks()."""

    def test_no_events_returns_empty(self) -> None:
        frozen_now = datetime.now(tz=timezone.utc)
        result = compute_routine_peaks([], "food", now=frozen_now)
        assert result["peak_hours"] == []
        assert result["status"] == "unknown"

    def test_single_peak_detected(self) -> None:
        frozen_now = datetime.now(tz=timezone.utc)
        events = [_ev("food", _ts(i, hour=8, ref=frozen_now)) for i in range(30)]
        result = compute_routine_peaks(events, "food", now=frozen_now)
        assert 8 in result["peak_hours"]
        assert isinstance(result["last_event_ago_hours"], (int, float))

    def test_two_peaks_detected(self) -> None:
        frozen_now = datetime.now(tz=timezone.utc)
        events = (
            [_ev("food", _ts(i, hour=8, ref=frozen_now)) for i in range(30)]
            + [_ev("food", _ts(i, hour=18, ref=frozen_now)) for i in range(30)]
        )
        result = compute_routine_peaks(events, "food", now=frozen_now)
        assert 8 in result["peak_hours"]
        assert 18 in result["peak_hours"]

    def test_on_schedule_when_recent_event_near_peak(self) -> None:
        frozen_now = datetime.now(tz=timezone.utc)
        # 30 days of food at 8am, including today
        events = [_ev("food", _ts(i, hour=8, ref=frozen_now)) for i in range(30)]
        result = compute_routine_peaks(events, "food", now=frozen_now)
        assert result["status"] == "on_schedule"

    def test_late_when_no_recent_event_near_peak(self) -> None:
        # Freeze "now" to 14:00 UTC so the 8am peak is well in the past.
        # All events are 2+ days ago at 8am -- none today.
        frozen_now = datetime.now(tz=timezone.utc).replace(
            hour=14, minute=0, second=0, microsecond=0,
        )
        events = [
            _ev(
                "food",
                (frozen_now - timedelta(days=i)).replace(hour=8).isoformat(),
            )
            for i in range(2, 32)
        ]
        result = compute_routine_peaks(events, "food", now=frozen_now)
        assert result["status"] == "late"

    def test_ignores_other_event_types(self) -> None:
        frozen_now = datetime.now(tz=timezone.utc)
        events = [_ev("pee", _ts(i, hour=8, ref=frozen_now)) for i in range(30)]
        result = compute_routine_peaks(events, "food", now=frozen_now)
        assert result["peak_hours"] == []
        assert result["status"] == "unknown"

    def test_histogram_attribute_has_24_buckets(self) -> None:
        frozen_now = datetime.now(tz=timezone.utc)
        events = [_ev("food", _ts(i, hour=8, ref=frozen_now)) for i in range(30)]
        result = compute_routine_peaks(events, "food", now=frozen_now)
        assert len(result["histogram"]) == 24
