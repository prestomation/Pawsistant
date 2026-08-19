"""Unit tests for sensor_analytics.py — pure analytics functions.

No Home Assistant imports; these functions operate on plain event dicts.
"""

from __future__ import annotations

import random
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
parse_event_timestamp = _mod.parse_event_timestamp


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
# TestParseEventTimestamp
# ---------------------------------------------------------------------------


class TestParseEventTimestamp:
    """Tests for parse_event_timestamp().

    Every sensor in the integration routes its timestamps through this one
    function — sensor.py imports it as ``_to_datetime``. Only the ISO path was
    exercised, and then only indirectly, so the fallbacks below were carrying
    real installs' legacy data with nothing pinning them down.
    """

    _SENTINEL = datetime.min.replace(tzinfo=timezone.utc)

    def test_iso_string_with_offset_keeps_its_instant(self) -> None:
        result = parse_event_timestamp("2026-06-01T08:00:00-08:00")
        assert result == datetime(2026, 6, 1, 16, 0, tzinfo=timezone.utc)

    def test_naive_iso_string_is_assumed_utc(self) -> None:
        result = parse_event_timestamp("2026-06-01T08:00:00")
        assert result == datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc)

    def test_aware_datetime_passes_through(self) -> None:
        tz = timezone(timedelta(hours=5, minutes=30))
        original = datetime(2026, 6, 1, 8, 0, tzinfo=tz)
        assert parse_event_timestamp(original) == original

    def test_naive_datetime_is_assumed_utc(self) -> None:
        result = parse_event_timestamp(datetime(2026, 6, 1, 8, 0))
        assert result == datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc)

    def test_numeric_seconds_are_epoch_seconds(self) -> None:
        """Legacy Firebase rows stored epoch seconds."""
        assert parse_event_timestamp(1780000000) == datetime.fromtimestamp(
            1780000000, tz=timezone.utc
        )

    def test_numeric_above_1e12_is_treated_as_milliseconds(self) -> None:
        """The same instant, in the millisecond form Firebase also produced.

        The 1e12 cutoff is what separates the two; read as seconds, a
        millisecond value would land some 55,000 years in the future.
        """
        assert parse_event_timestamp(1780000000000) == parse_event_timestamp(
            1780000000
        )

    def test_numeric_string_is_parsed_too(self) -> None:
        assert parse_event_timestamp("1780000000") == parse_event_timestamp(
            1780000000
        )

    def test_none_returns_the_sort_first_sentinel(self) -> None:
        assert parse_event_timestamp(None) == self._SENTINEL

    def test_unparseable_value_returns_the_sort_first_sentinel(self) -> None:
        assert parse_event_timestamp("not a timestamp") == self._SENTINEL
        assert parse_event_timestamp({}) == self._SENTINEL

    def test_sentinel_sorts_before_every_real_event(self) -> None:
        """Callers sort on this without a None check, so ordering must hold."""
        assert self._SENTINEL < parse_event_timestamp("1970-01-02T00:00:00+00:00")


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

    def test_zero_oldest_reading_is_unknown_not_stable(self) -> None:
        """A bogus 0 lb reading must not be reported as a stable trend.

        Dividing by it would raise, so the percentage change is genuinely
        undefined — but answering "stable" for a 0 -> 50 lb series states
        something false rather than declining to answer.
        """
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        events = [
            _ev("weight", (now - timedelta(days=20)).isoformat(), value=0.0),
            _ev("weight", (now - timedelta(days=10)).isoformat(), value=50.0),
            _ev("weight", (now - timedelta(days=1)).isoformat(), value=50.5),
        ]
        result = compute_weight_trend(events, window_days=30, now=now)
        assert result["trend"] == "unknown"
        assert result["change_pct"] is None
        # The readings themselves still surface, so the sensor can show what it
        # saw and the user can spot the bad entry.
        assert result["sample_count"] == 3
        assert result["oldest_value"] == 0.0
        assert result["newest_value"] == 50.5

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
        """The window edge is inclusive, and exact to the second.

        Timestamps are built from exact offsets rather than via ``_ts()``, whose
        hour-snapping would put the "boundary" reading half a day *inside* the
        window — leaving the test unable to detect an edge off by hours.
        """
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        cutoff = now - timedelta(days=30)
        events = [
            # One second too old: must fall outside.
            _ev("weight", (cutoff - timedelta(seconds=1)).isoformat(), value=1.0),
            # Exactly on the cutoff: must fall inside.
            _ev("weight", cutoff.isoformat(), value=50.0),
            _ev("weight", (now - timedelta(days=15)).isoformat(), value=53.0),
            _ev("weight", (now - timedelta(days=1)).isoformat(), value=56.0),
        ]
        result = compute_weight_trend(events, window_days=30, now=now)
        assert result["sample_count"] == 3, "boundary in, one-second-older out"
        # Pins down *which* three: the 50.0 sitting on the cutoff, not the 1.0
        # just outside it.
        assert result["oldest_value"] == 50.0
        assert result["trend"] == "gaining"
        assert result["lifetime_sample_count"] == 4

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


class TestSickClusterActive:
    """`cluster_active` answers "is an illness still going on right now?".

    It is advertised as an automation trigger, so its boolean has to be right
    in both directions — a stuck-on flag nags about a pet that recovered a
    month ago, and a stuck-off one misses the thing it exists to catch.
    """

    NOW = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)

    def _sick_days_ago(self, *days: float) -> list[dict]:
        return [
            _ev("sick", (self.NOW - timedelta(days=d)).isoformat()) for d in days
        ]

    def test_active_while_the_run_can_still_be_extended(self) -> None:
        result = compute_sick_frequency(self._sick_days_ago(1, 3), now=self.NOW)
        assert result["cluster_size"] == 2
        assert result["cluster_active"] is True

    def test_not_active_once_the_run_has_gone_cold(self) -> None:
        """Two sick days close together, but a fortnight ago: recovered."""
        result = compute_sick_frequency(self._sick_days_ago(14, 16), now=self.NOW)
        assert result["cluster_size"] == 2, "they still clustered with each other"
        assert result["cluster_active"] is False, "but it is over"

    def test_a_single_recent_sick_day_is_not_a_cluster(self) -> None:
        result = compute_sick_frequency(self._sick_days_ago(1), now=self.NOW)
        assert result["cluster_size"] == 1
        assert result["cluster_active"] is False

    def test_no_sick_events_is_not_active(self) -> None:
        result = compute_sick_frequency([], now=self.NOW)
        assert result["cluster_active"] is False
        assert result["days_since_last"] is None

    def test_cluster_gap_is_measured_exactly_not_truncated_to_whole_days(
        self,
    ) -> None:
        """Two events 7d20h apart are outside a 7-day gap, not inside it.

        Comparing `timedelta.days` truncates towards zero, so anything under a
        full 8 days used to satisfy a rule documented as 7 — making the cluster
        rule almost a day more permissive than every figure beside it.
        """
        result = compute_sick_frequency(
            self._sick_days_ago(1, 1 + 7 + 20 / 24), now=self.NOW
        )
        assert result["cluster_size"] == 1, "7d20h apart is not one illness"

        just_inside = compute_sick_frequency(
            self._sick_days_ago(1, 1 + 7 - 1 / 24), now=self.NOW
        )
        assert just_inside["cluster_size"] == 2, "6d23h apart still clusters"


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


def _daily_at(
    now: datetime,
    hour: int,
    days: range,
    event_type: str = "food",
    minute: int = 0,
    as_utc: bool = False,
) -> list[dict]:
    """Build one *event_type* per day in *days*, at *hour* in ``now``'s zone.

    ``as_utc`` re-expresses the same instants as UTC ``Z`` strings, mimicking
    events logged through the card's time chooser rather than by a button tap.
    """
    events = []
    for day in days:
        ts = (now - timedelta(days=day)).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        if as_utc:
            ts = ts.astimezone(timezone.utc)
        events.append(_ev(event_type, ts.isoformat()))
    return events


def _jittered_daily(
    now: datetime,
    hour: int,
    minute: int,
    jitter_min: int,
    days: range,
    event_type: str = "food",
    seed: int = 7,
) -> list[dict]:
    """One event a day at roughly the same time, with human-sized jitter.

    Nobody feeds a dog at exactly 08:00:00 every day, and the jitter is the
    whole point: it is what a fixed-hour histogram used to split in half.
    """
    rnd = random.Random(seed)
    events = []
    for day in days:
        base = (now - timedelta(days=day)).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        offset = timedelta(minutes=rnd.uniform(-jitter_min, jitter_min))
        events.append(_ev(event_type, (base + offset).isoformat()))
    return events


class TestRoutineClustering:
    """Grouping events by time of day, rather than into fixed hour buckets.

    Fixed buckets made the answer depend on where an arbitrary boundary fell:
    the same daily meal read as one, two or three "peaks" purely from being
    served at 08:30 versus 08:00 versus 07:30, and a bedtime routine at 23:55
    split into two peaks that the coverage arithmetic then placed 23 hours
    apart, so it could never satisfy itself.
    """

    NOW = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)

    @pytest.mark.parametrize(
        "hour,minute", [(8, 0), (7, 45), (8, 30), (7, 58), (12, 15)]
    )
    def test_one_meal_is_one_routine_wherever_the_clock_falls(
        self, hour: int, minute: int
    ) -> None:
        events = _jittered_daily(self.NOW, hour, minute, 25, range(1, 30))
        result = compute_routine_peaks(events, "food", now=self.NOW)
        assert len(result["peak_minutes"]) == 1, (
            f"one daily meal at {hour:02d}:{minute:02d} reported as "
            f"{len(result['peak_minutes'])} routines"
        )

    def test_wide_jitter_still_reads_as_one_routine(self) -> None:
        """+/-45 min spans three hour buckets; it is still one habit."""
        events = _jittered_daily(self.NOW, 7, 30, 45, range(1, 30))
        result = compute_routine_peaks(events, "food", now=self.NOW)
        assert len(result["peak_minutes"]) == 1

    def test_routine_straddling_midnight_stays_one_routine(self) -> None:
        """A habit centred near midnight lands on both sides of the seam.

        Balanced deliberately so that failing to close the circle yields two
        routines rather than one, instead of quietly discarding whichever half
        is smaller — which is what happens for a lopsided split and would let
        this pass while still being wrong.
        """
        events = _jittered_daily(self.NOW, 0, 10, 40, range(1, 30))
        result = compute_routine_peaks(events, "food", now=self.NOW)
        centers = result["peak_minutes"]
        assert len(centers) == 1, f"one bedtime habit read as {len(centers)}"
        assert _mod._circular_distance(centers[0], 10) <= 30, (
            "the surviving routine should sit near 00:10, not be one half of it"
        )
        # The histogram still splits it across buckets 23 and 0 — which is fine,
        # it is for drawing a chart. What matters is that no decision is made
        # from it any more.
        assert result["histogram"][23] > 0
        assert result["histogram"][0] > 0

    def test_two_genuinely_separate_meals_stay_two_routines(self) -> None:
        """Clustering must not over-merge: breakfast and dinner are distinct."""
        events = _jittered_daily(self.NOW, 8, 0, 20, range(1, 30)) + _jittered_daily(
            self.NOW, 18, 0, 20, range(1, 30), seed=11
        )
        result = compute_routine_peaks(events, "food", now=self.NOW)
        centers = result["peak_minutes"]
        assert len(centers) == 2
        # Asserted as a distance from the intended time rather than an exact
        # hour: jitter can land the average either side of the boundary, and
        # pinning to the hour is the brittleness this whole change removes.
        assert abs(centers[0] - 8 * 60) <= 30
        assert abs(centers[1] - 18 * 60) <= 30

    def test_peak_minutes_reports_the_real_time_not_the_hour(self) -> None:
        events = _daily_at(self.NOW, 8, range(1, 30), minute=30)
        result = compute_routine_peaks(events, "food", now=self.NOW)
        assert result["peak_minutes"] == [510], "08:30 is minute 510"

    def test_many_events_on_a_single_day_is_not_a_routine(self) -> None:
        """Three pees in one bad hour on one night is not a schedule.

        The old rule counted events, so a single unusual night could manufacture
        a peak. Recurrence is measured in days.
        """
        base = (self.NOW - timedelta(days=2)).replace(
            hour=3, minute=0, second=0, microsecond=0
        )
        events = [
            _ev("pee", (base + timedelta(minutes=i * 10)).isoformat())
            for i in range(6)
        ]
        result = compute_routine_peaks(events, "pee", now=self.NOW)
        assert result["peak_minutes"] == []
        assert result["status"] == "unknown"

    def test_an_occasional_habit_is_not_a_routine(self) -> None:
        """Tightly clustered in time, but only on a handful of days.

        This is the shape that made pee sensors read `late` all day: an
        occasional late-night trip became a "peak" the dog then had to satisfy
        every single day.
        """
        events = _jittered_daily(self.NOW, 8, 0, 20, range(1, 30), event_type="pee")
        events += _daily_at(self.NOW, 3, range(1, 30, 7), event_type="pee")
        result = compute_routine_peaks(events, "pee", now=self.NOW)
        centers = result["peak_minutes"]
        assert len(centers) == 1, "the 03:00 outings are not a routine"
        assert abs(centers[0] - 8 * 60) <= 30, "the surviving one is the morning"

    def test_circular_distance_wraps_around_midnight(self) -> None:
        distance = _mod._circular_distance
        assert distance(23 * 60 + 55, 10) == 15, "23:55 to 00:10 is 15 minutes"
        assert distance(10, 23 * 60 + 55) == 15, "and it is symmetric"
        assert distance(8 * 60, 9 * 60) == 60

    def test_circular_mean_averages_across_midnight(self) -> None:
        """23:50 and 00:10 average to midnight, not midday."""
        mean = _mod._circular_mean([23 * 60 + 50, 10])
        assert round(mean) % 1440 == 0


class TestRoutineOverdueDetail:
    """When a routine is late, say which one and by how much.

    Exposed as numbers rather than a sentence: the card composes the wording in
    the user's language, and 12- vs 24-hour is the reader's preference to make.
    """

    NOW = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)

    def test_late_names_the_overdue_routine(self) -> None:
        events = _daily_at(self.NOW, 8, range(1, 30))  # nothing logged today
        result = compute_routine_peaks(events, "food", now=self.NOW)
        assert result["status"] == "late"
        assert result["overdue_peak_minute"] == 480, "08:00"
        # Deadline was 08:00 + 2h grace = 10:00; now is 12:00.
        assert result["minutes_overdue"] == 120

    def test_on_schedule_leaves_the_overdue_fields_empty(self) -> None:
        events = _daily_at(self.NOW, 8, range(0, 30))  # includes today
        result = compute_routine_peaks(events, "food", now=self.NOW)
        assert result["status"] == "on_schedule"
        assert result["overdue_peak_minute"] is None
        assert result["minutes_overdue"] is None

    def test_the_longest_waiting_routine_is_the_one_named(self) -> None:
        events = _daily_at(self.NOW, 7, range(1, 30)) + _daily_at(
            self.NOW, 9, range(1, 30)
        )
        result = compute_routine_peaks(events, "food", now=self.NOW)
        assert result["status"] == "late"
        assert result["overdue_peak_minute"] == 420, "07:00, the older miss"

    def test_routine_too_close_to_midnight_reports_unknown_not_on_schedule(
        self,
    ) -> None:
        """A routine that cannot be judged must not be reported as fine.

        Its grace period expires after the day has already rolled over and
        today's events reset, so there is no honest verdict to give. Answering
        "on_schedule" would be a claim we cannot support: a nightly walk that
        quietly stopped happening would read as fine forever and no automation
        could fire on it.
        """
        events = _daily_at(self.NOW, 23, range(1, 30), minute=50)
        result = compute_routine_peaks(
            events, "food", now=self.NOW.replace(hour=23, minute=59)
        )
        assert result["status"] == "unknown"
        assert result["overdue_peak_minute"] is None
        # The routine itself was still detected — "unknown" here means "cannot
        # judge", not "nothing learned", and peak_minutes is what distinguishes
        # the two for a caller.
        assert len(result["peak_minutes"]) == 1

    def test_a_judgeable_routine_still_decides_the_status(self) -> None:
        """One unjudgeable near-midnight routine must not mask the others.

        With a morning routine present and satisfied, the verdict comes from
        that one rather than collapsing to unknown.
        """
        events = _daily_at(self.NOW, 8, range(0, 30)) + _daily_at(
            self.NOW, 23, range(1, 30), minute=50
        )
        result = compute_routine_peaks(events, "food", now=self.NOW.replace(hour=14))
        assert len(result["peak_minutes"]) == 2
        assert result["status"] == "on_schedule"

    def test_unknown_explains_itself_without_hardcoded_constants(self) -> None:
        """A caller can say "logged on 2 days, needs 3" from attributes alone."""
        events = _daily_at(self.NOW, 8, range(1, 3))
        result = compute_routine_peaks(events, "food", now=self.NOW)
        assert result["status"] == "unknown"
        assert result["days_observed"] == 2
        assert result["min_days_required"] == _mod.ROUTINE_MIN_CLUSTER_DAYS


class TestComputeRoutinePeaks:
    """Tests for compute_routine_peaks().

    Every test pins ``now`` to a literal datetime. These assertions branch on
    the hour of day, so a wall-clock "now" would silently test a different code
    path depending on when the suite happened to run.
    """

    NOW = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)

    def test_no_events_returns_empty(self) -> None:
        result = compute_routine_peaks([], "food", now=self.NOW)
        assert result["peak_minutes"] == []
        assert result["status"] == "unknown"

    def test_single_peak_detected(self) -> None:
        events = _daily_at(self.NOW, 8, range(30))
        result = compute_routine_peaks(events, "food", now=self.NOW)
        assert result["peak_minutes"] == [8 * 60]
        assert isinstance(result["last_event_ago_hours"], (int, float))

    def test_two_peaks_detected(self) -> None:
        events = _daily_at(self.NOW, 8, range(30)) + _daily_at(
            self.NOW, 18, range(30)
        )
        result = compute_routine_peaks(events, "food", now=self.NOW)
        assert result["peak_minutes"] == [8 * 60, 18 * 60]

    def test_on_schedule_when_recent_event_near_peak(self) -> None:
        """Today's meal covers the 8am peak.

        ``now`` is 14:00 — comfortably past the peak *and* its grace period — so
        the coverage check is actually reached. Frozen earlier in the day the
        function short-circuits on "nothing due yet" and the assertion holds no
        matter how badly coverage detection is broken.
        """
        now = self.NOW.replace(hour=14)
        events = _daily_at(now, 8, range(30))  # range starts at 0: includes today
        result = compute_routine_peaks(events, "food", now=now)
        assert result["peak_minutes"] == [8 * 60]
        assert result["status"] == "on_schedule"

    def test_late_when_no_recent_event_near_peak(self) -> None:
        now = self.NOW.replace(hour=14)
        events = _daily_at(now, 8, range(2, 32))  # nothing today
        result = compute_routine_peaks(events, "food", now=now)
        assert result["status"] == "late"

    def test_peak_is_not_due_until_its_grace_period_elapses(self) -> None:
        """A routine is not late the instant its usual hour begins.

        ROUTINE_LATE_THRESHOLD_HOURS is a real deadline, not just a tolerance
        used when matching events to peaks.
        """
        events = _daily_at(self.NOW, 8, range(1, 31))  # nothing logged today
        at_nine = compute_routine_peaks(
            events, "food", now=self.NOW.replace(hour=9)
        )
        assert at_nine["status"] == "on_schedule", "still inside the grace period"

        at_half_ten = compute_routine_peaks(
            events, "food", now=self.NOW.replace(hour=10, minute=30)
        )
        assert at_half_ten["status"] == "late", "grace elapsed, nothing logged"

    def test_late_evening_peak_still_reports_late_before_midnight(self) -> None:
        """A 22:00 routine must be able to go late on the same day.

        Its grace period would otherwise expire after midnight, by which point
        today's events have reset and the peak can never be judged at all.
        """
        events = _daily_at(self.NOW, 22, range(1, 31))  # nothing logged today
        result = compute_routine_peaks(
            events, "food", now=self.NOW.replace(hour=23, minute=45)
        )
        assert result["status"] == "late"

    def test_routine_times_are_reported_in_the_reference_timezone(self) -> None:
        """Hours are the user's local hours, not the stored offset's.

        A pet fed at 08:00 in a UTC-08:00 household has its meals stored as
        16:00 UTC. The peak must read 8, or every non-UTC user sees their
        routine sensors flip at the wrong time of day.
        """
        tz = timezone(timedelta(hours=-8))
        now = datetime(2026, 6, 30, 12, 0, tzinfo=tz)
        events = _daily_at(now, 8, range(1, 31), as_utc=True)
        result = compute_routine_peaks(events, "food", now=now)
        assert result["peak_minutes"] == [8 * 60]
        assert result["histogram"][16] == 0, "16:00 UTC must not be its own peak"

    def test_mixed_offset_timestamps_collapse_into_one_peak(self) -> None:
        """One routine stays one peak when the store mixes timestamp formats.

        A button tap writes a local-offset timestamp; the card's time chooser
        writes UTC ``Z``. Both reach the store, so the same 08:00 meal arrives
        in two notations — which must not read as two separate daily peaks.
        """
        tz = timezone(timedelta(hours=-8))
        now = datetime(2026, 6, 30, 12, 0, tzinfo=tz)
        # Days 1-29 only: a day-30 event at 08:00 sits just outside the 30-day
        # lookback measured from midday, which would skew the count.
        events = _daily_at(now, 8, range(1, 30, 2)) + _daily_at(
            now, 8, range(2, 30, 2), as_utc=True
        )
        result = compute_routine_peaks(events, "food", now=now)
        assert result["peak_minutes"] == [8 * 60]
        assert result["histogram"][8] == len(events)
        assert result["histogram"][16] == 0

    def test_ignores_other_event_types(self) -> None:
        events = _daily_at(self.NOW, 8, range(30), event_type="pee")
        result = compute_routine_peaks(events, "food", now=self.NOW)
        assert result["peak_minutes"] == []
        assert result["status"] == "unknown"

    def test_histogram_attribute_has_24_buckets(self) -> None:
        events = _daily_at(self.NOW, 8, range(30))
        result = compute_routine_peaks(events, "food", now=self.NOW)
        assert len(result["histogram"]) == 24
