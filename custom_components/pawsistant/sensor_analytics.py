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
