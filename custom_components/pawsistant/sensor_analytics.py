"""Pure analytics functions for Pawsistant sensors.

Each function takes a list of event dicts (same shape as coordinator data)
and returns a dict of computed values. No HA imports -- fully testable
without a running Home Assistant instance.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Tuning constants
# ---------------------------------------------------------------------------

WEIGHT_TREND_MIN_POINTS = 3
WEIGHT_TREND_SIGNIFICANT_CHANGE_PCT = 5.0

# Default recent window, in days, when a dog has no per-dog override.
# 90 days suits the common case of a weigh-in at each vet visit (every 2-3
# months) while still excluding readings old enough to be a different chapter
# of the pet's life.
WEIGHT_TREND_DEFAULT_WINDOW_DAYS = 90

# Default gaining/losing band, chosen by window length.
#
# A fixed band cannot serve every window: 5% over a year is unremarkable
# growth, whereas the same 5% inside a week warrants a vet call. Each entry is
# (max_window_days, threshold_pct), consulted in order; a window longer than
# every entry (or no window at all) falls back to
# WEIGHT_TREND_SIGNIFICANT_CHANGE_PCT.
#
# Users can override the threshold per dog; these are the defaults that make
# that unnecessary for most people.
WEIGHT_TREND_THRESHOLD_BY_WINDOW: list[tuple[int, float]] = [
    (14, 2.0),
    (90, 3.0),
]

SICK_FREQUENCY_LOOKBACK_DAYS = 30
SICK_FREQUENCY_PREVIOUS_WINDOW_DAYS = 30
SICK_CLUSTER_GAP_DAYS = 7

# Event types tracked for routine detection.
# @todo: allow user to add/remove types from this list via options flow
ROUTINE_EVENT_TYPES: list[str] = [
    "food",
    "pee",
    "poop",
    "walk",
    "water",
    "treat",
]
ROUTINE_LOOKBACK_DAYS = 30
ROUTINE_LATE_THRESHOLD_HOURS = 2


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safe_float(v: Any) -> float | None:
    """Try to convert *v* to float; return None on failure."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_ts(ts: Any) -> datetime:
    """Parse a timestamp string, datetime, or numeric value to tz-aware datetime.

    Same logic as ``_to_datetime`` in sensor.py:
      - ISO 8601 string
      - datetime object (made tz-aware if naive)
      - numeric: milliseconds if > 1e12, else seconds (legacy Firebase format)

    Returns ``datetime.min`` with UTC tzinfo for None / unparseable values.
    """
    if ts is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if isinstance(ts, datetime):
        return ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)
    if isinstance(ts, str):
        try:
            dt = datetime.fromisoformat(ts)
            return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            pass
    # Numeric fallback
    try:
        numeric = float(ts)
        if numeric > 1e12:
            numeric /= 1000
        return datetime.fromtimestamp(numeric, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return datetime.min.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# compute_weight_trend
# ---------------------------------------------------------------------------


def default_weight_threshold_pct(window_days: int | None) -> float:
    """Return the default gaining/losing band for a window of *window_days*.

    Shorter windows get tighter bands — see
    ``WEIGHT_TREND_THRESHOLD_BY_WINDOW`` for the reasoning.
    """
    if window_days is not None:
        for max_days, threshold in WEIGHT_TREND_THRESHOLD_BY_WINDOW:
            if window_days <= max_days:
                return threshold
    return WEIGHT_TREND_SIGNIFICANT_CHANGE_PCT


def _trend_over(
    weight_events: list[dict[str, Any]], threshold_pct: float
) -> dict[str, Any]:
    """Summarise an already-filtered, chronologically sorted weight series.

    Returns the trend plus the supporting figures, or an all-None summary when
    there are fewer than ``WEIGHT_TREND_MIN_POINTS`` readings. ``sample_count``
    is always the true number of readings so callers can explain an "unknown"
    result rather than just reporting a blank.
    """
    if len(weight_events) < WEIGHT_TREND_MIN_POINTS:
        return {
            "trend": "unknown",
            "change_pct": None,
            "sample_count": len(weight_events),
            "oldest_value": None,
            "newest_value": None,
            "over_days": None,
        }

    # _safe_float is guaranteed non-None here thanks to the caller's filter.
    oldest_value: float = _safe_float(weight_events[0]["value"])  # type: ignore[assignment]
    newest_value: float = _safe_float(weight_events[-1]["value"])  # type: ignore[assignment]

    oldest_ts = _parse_ts(weight_events[0].get("timestamp"))
    newest_ts = _parse_ts(weight_events[-1].get("timestamp"))
    over_days = round((newest_ts - oldest_ts).total_seconds() / 86400, 1)

    if oldest_value == 0:
        change_pct = 0.0
    else:
        change_pct = round(((newest_value - oldest_value) / oldest_value) * 100, 2)

    if change_pct > threshold_pct:
        trend = "gaining"
    elif change_pct < -threshold_pct:
        trend = "losing"
    else:
        trend = "stable"

    return {
        "trend": trend,
        "change_pct": change_pct,
        "sample_count": len(weight_events),
        "oldest_value": oldest_value,
        "newest_value": newest_value,
        "over_days": over_days,
    }


def compute_weight_trend(
    events: list[dict[str, Any]],
    *,
    window_days: int | None = WEIGHT_TREND_DEFAULT_WINDOW_DAYS,
    threshold_pct: float | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Analyse weight events and return a trend summary.

    The headline trend covers a recent window rather than all recorded history.
    Comparing the oldest reading to the newest gets steadily less informative
    as history accumulates: a dog that lost weight and then regained it nets
    out "stable", and the comparison span widens forever. Full-history figures
    remain available under the ``lifetime_*`` keys.

    The window is applied strictly. When it holds fewer than
    ``WEIGHT_TREND_MIN_POINTS`` readings the trend is "unknown" — the window is
    never widened to find more, because that would override the interval the
    user deliberately configured. ``sample_count`` and ``window_days`` are
    always populated so an "unknown" reads as "not enough readings in your
    window" rather than as a malfunction.

    Args:
        events:        List of event dicts (any mix of event types).
        window_days:   Recent window in days, or None to use all history for
                       the headline trend too.
        threshold_pct: Percentage change that counts as gaining/losing. When
                       None, defaults by window length via
                       :func:`default_weight_threshold_pct`.
        now:           Optional reference timestamp for "now". Defaults to
                       ``datetime.now(tz=timezone.utc)``; overridable for
                       deterministic testing.

    Returns:
        Dict with keys:
            trend         -- "gaining", "losing", "stable", or "unknown"
            change_pct    -- percentage change oldest->newest in window (or None)
            sample_count  -- weight readings inside the window
            oldest_value  -- first reading in the window (or None)
            newest_value  -- last reading in the window (or None)
            over_days     -- span in days covered by the window's readings
            window_days   -- the window applied (echoed back; None = all history)
            threshold_pct -- the gaining/losing band applied
            lifetime_*    -- the same trend figures computed over all history
                             (trend, change_pct, sample_count, oldest_value,
                             newest_value, over_days)
    """
    if now is None:
        now = datetime.now(tz=timezone.utc)
    if threshold_pct is None:
        threshold_pct = default_weight_threshold_pct(window_days)

    weight_events = [
        e
        for e in events
        if e.get("event_type") == "weight"
        and _safe_float(e.get("value")) is not None
    ]
    weight_events.sort(key=lambda e: _parse_ts(e.get("timestamp")))

    lifetime = _trend_over(weight_events, threshold_pct)

    if window_days is None:
        windowed = lifetime
    else:
        cutoff = now - timedelta(days=window_days)
        windowed = _trend_over(
            [e for e in weight_events if _parse_ts(e.get("timestamp")) >= cutoff],
            threshold_pct,
        )

    return {
        **windowed,
        "window_days": window_days,
        "threshold_pct": threshold_pct,
        "lifetime_trend": lifetime["trend"],
        "lifetime_change_pct": lifetime["change_pct"],
        "lifetime_sample_count": lifetime["sample_count"],
        "lifetime_oldest_value": lifetime["oldest_value"],
        "lifetime_newest_value": lifetime["newest_value"],
        "lifetime_over_days": lifetime["over_days"],
    }


# ---------------------------------------------------------------------------
# compute_sick_frequency
# ---------------------------------------------------------------------------


def compute_sick_frequency(
    events: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Analyse sick-event frequency over two 30-day windows.

    Args:
        events: List of event dicts (any mix of event types).
        now:    Optional reference timestamp for "now". Defaults to
                ``datetime.now(tz=timezone.utc)`` when *None*, but can be
                overridden for deterministic testing.

    Returns:
        Dict with keys:
            count_current  -- sick events in the last 30 days
            count_previous -- sick events in the 30-60 days-ago window
            cluster_size   -- longest run of consecutive sick events where
                              each pair is within 7 days of each other
                              (current window only)
            days_since_last -- days since most recent sick event (or None)
    """
    if now is None:
        now = datetime.now(tz=timezone.utc)
    current_cutoff = now - timedelta(days=SICK_FREQUENCY_LOOKBACK_DAYS)
    previous_cutoff = now - timedelta(
        days=SICK_FREQUENCY_LOOKBACK_DAYS + SICK_FREQUENCY_PREVIOUS_WINDOW_DAYS
    )

    sick_events = [e for e in events if e.get("event_type") == "sick"]

    current: list[datetime] = []
    previous_count = 0

    for ev in sick_events:
        ts = _parse_ts(ev.get("timestamp"))
        if ts >= current_cutoff:
            current.append(ts)
        elif ts >= previous_cutoff:
            previous_count += 1

    # days_since_last — unbounded: considers ALL sick events, not just windowed
    days_since_last: float | None = None
    if sick_events:
        most_recent = max(_parse_ts(e.get("timestamp")) for e in sick_events)
        if most_recent > datetime.min.replace(tzinfo=timezone.utc):
            days_since_last = round(
                (now - most_recent).total_seconds() / 86400, 1
            )

    # cluster detection: longest run of sick events within 7d of each other
    current.sort()
    cluster_size = 0
    if current:
        run = 1
        max_run = 1
        for i in range(1, len(current)):
            if (current[i] - current[i - 1]).days <= SICK_CLUSTER_GAP_DAYS:
                run += 1
            else:
                run = 1
            max_run = max(max_run, run)
        cluster_size = max_run

    return {
        "count_current": len(current),
        "count_previous": previous_count,
        "cluster_size": cluster_size,
        "days_since_last": days_since_last,
    }


# ---------------------------------------------------------------------------
# compute_routine_peaks
# ---------------------------------------------------------------------------


def compute_routine_peaks(
    events: list[dict[str, Any]],
    event_type: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Detect time-of-day peaks for a given event type.

    Args:
        events:     List of event dicts (any mix of event types).
        event_type: The event type to analyse (e.g. "food", "walk").
        now:        Optional reference timestamp for "now". Defaults to
                    ``datetime.now(tz=timezone.utc)`` when *None*, but can be
                    overridden for deterministic testing.

    Returns:
        Dict with keys:
            peak_hours        -- list of hour-of-day ints (0-23) that are peaks
            histogram         -- 24-element list of counts per hour bucket
            status            -- "on_schedule", "late", or "unknown"
            last_event_ago_hours -- hours since the most recent matching event
                                   (or None)
            sample_count      -- number of matching events in the lookback window
    """
    if now is None:
        now = datetime.now(tz=timezone.utc)
    cutoff = now - timedelta(days=ROUTINE_LOOKBACK_DAYS)

    matching: list[datetime] = []
    for ev in events:
        if ev.get("event_type") != event_type:
            continue
        ts = _parse_ts(ev.get("timestamp"))
        if ts >= cutoff:
            matching.append(ts)

    histogram = [0] * 24
    for ts in matching:
        histogram[ts.hour] += 1

    sample_count = len(matching)

    # last_event_ago_hours
    last_event_ago_hours: float | None = None
    if matching:
        most_recent = max(matching)
        last_event_ago_hours = round(
            (now - most_recent).total_seconds() / 3600, 1
        )

    # Peak detection: hours with count >= 2x average AND >= 3
    peak_hours: list[int] = []
    if sample_count > 0:
        avg = sample_count / 24
        peak_hours = [
            h for h in range(24) if histogram[h] >= 2 * avg and histogram[h] >= 3
        ]

    # Schedule status
    if not peak_hours:
        status = "unknown"
    else:
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_events = [ts for ts in matching if ts >= today_start]
        today_hours = {ts.hour for ts in today_events}

        # Determine which peak hours have already passed today
        past_peaks = [h for h in peak_hours if h <= now.hour]

        if not past_peaks:
            # No peak hour has arrived yet today
            status = "on_schedule"
        else:
            # Check if each past peak is covered by a today-event within
            # ROUTINE_LATE_THRESHOLD_HOURS
            all_covered = True
            for peak_h in past_peaks:
                covered = any(
                    abs(th - peak_h) <= ROUTINE_LATE_THRESHOLD_HOURS
                    for th in today_hours
                )
                if not covered:
                    all_covered = False
                    break
            status = "on_schedule" if all_covered else "late"

    return {
        "peak_hours": peak_hours,
        "histogram": histogram,
        "status": status,
        "last_event_ago_hours": last_event_ago_hours,
        "sample_count": sample_count,
    }
