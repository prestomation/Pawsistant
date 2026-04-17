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

# @todo: make configurable per-dog via options flow if needed
WEIGHT_TREND_MIN_POINTS = 3
WEIGHT_TREND_SIGNIFICANT_CHANGE_PCT = 5.0

SICK_FREQUENCY_LOOKBACK_DAYS = 30
SICK_FREQUENCY_PREVIOUS_WINDOW_DAYS = 30

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


def compute_weight_trend(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyse weight events and return a trend summary.

    Args:
        events: List of event dicts (any mix of event types).

    Returns:
        Dict with keys:
            trend        -- "gaining", "losing", "stable", or "unknown"
            change_pct   -- percentage change oldest->newest (or None)
            sample_count -- number of weight data points (or None)
            oldest_value -- first recorded weight (or None)
            newest_value -- last recorded weight (or None)
            over_days    -- span in days between oldest and newest (or None)
    """
    weight_events = [
        e
        for e in events
        if e.get("event_type") == "weight" and e.get("value") is not None
    ]

    weight_events.sort(key=lambda e: _parse_ts(e.get("timestamp")))

    if len(weight_events) < WEIGHT_TREND_MIN_POINTS:
        return {
            "trend": "unknown",
            "change_pct": None,
            "sample_count": None,
            "oldest_value": None,
            "newest_value": None,
            "over_days": None,
        }

    oldest_value = float(weight_events[0]["value"])
    newest_value = float(weight_events[-1]["value"])

    oldest_ts = _parse_ts(weight_events[0].get("timestamp"))
    newest_ts = _parse_ts(weight_events[-1].get("timestamp"))
    over_days = round((newest_ts - oldest_ts).total_seconds() / 86400, 1)

    if oldest_value == 0:
        change_pct = 0.0
    else:
        change_pct = round(((newest_value - oldest_value) / oldest_value) * 100, 2)

    if change_pct > WEIGHT_TREND_SIGNIFICANT_CHANGE_PCT:
        trend = "gaining"
    elif change_pct < -WEIGHT_TREND_SIGNIFICANT_CHANGE_PCT:
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

    # days_since_last
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
            if (current[i] - current[i - 1]).total_seconds() <= 7 * 86400:
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
