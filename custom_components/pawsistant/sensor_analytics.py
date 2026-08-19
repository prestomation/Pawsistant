"""Pure analytics functions for Pawsistant sensors.

Each function takes a list of event dicts (same shape as coordinator data)
and returns a dict of computed values. No HA imports -- fully testable
without a running Home Assistant instance.

Time-of-day arithmetic is always done in the timezone of the ``now`` argument,
never in whatever offset a stored timestamp happens to carry. The store holds a
mix of conventions -- a button tap writes ``dt_util.now()`` (local offset) while
the card's time chooser sends ``toISOString()`` (UTC ``Z``) -- so bucketing on a
raw ``.hour`` would scatter a single routine across several hours. Callers in
the integration pass ``now=dt_util.now()`` so the buckets are the user's local
hours; the default of UTC only applies to direct callers that pass nothing.
"""

from __future__ import annotations

import math
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

# How far from a routine's usual time an event still counts as "that one".
ROUTINE_LATE_THRESHOLD_MINUTES = 120

# Events further apart than this belong to different routines. Splitting on a
# gap rather than into fixed hour buckets is what keeps one habit from being
# sawn in half by an arbitrary boundary: a meal at 07:58 one day and 08:02 the
# next is four minutes apart, and no amount of bucketing should disagree.
ROUTINE_CLUSTER_GAP_MINUTES = 90

# What makes a cluster a *routine* rather than a coincidence: it has to recur on
# at least this many separate days, and on at least this share of the days the
# activity was logged at all. Counting days rather than events matters -- three
# pees in one bad hour on one night is not a schedule.
ROUTINE_MIN_CLUSTER_DAYS = 3
ROUTINE_MIN_DAY_FRACTION = 0.5

# How long before midnight a still-uncovered routine is judged, when its normal
# grace period would run past the end of the day. Without this a 22:00 routine
# could never report "late": its deadline (22:00 + 2h) lands after the day has
# already rolled over and today's events have reset.
ROUTINE_END_OF_DAY_MARGIN = timedelta(minutes=30)

MINUTES_PER_DAY = 1440


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safe_float(v: Any) -> float | None:
    """Try to convert *v* to float; return None on failure."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_event_timestamp(ts: Any) -> datetime:
    """Parse a timestamp string, datetime, or numeric value to tz-aware datetime.

    The single parser for event timestamps across the integration; sensor.py
    imports it as ``_to_datetime``, the name it has always used there. It lives
    in this module because this module has no HA imports.

    Accepts:
      - ISO 8601 string
      - datetime object (made tz-aware if naive)
      - numeric: milliseconds if > 1e12, else seconds (legacy Firebase format)

    Anything naive is assumed UTC. Returns ``datetime.min`` with UTC tzinfo for
    None / unparseable values, so callers can sort and compare without a None
    check -- such a value sorts before every real event.
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


def _weight_series(events: list[dict[str, Any]]) -> list[tuple[datetime, float]]:
    """Extract usable weight readings as chronologically sorted (ts, value) pairs.

    Timestamps and values are parsed once, here, rather than re-derived by each
    consumer: the series is walked several times over (the lifetime summary, the
    windowed summary, and the endpoints of each) and parsing is not free.
    Readings whose value will not parse as a number are dropped.
    """
    series: list[tuple[datetime, float]] = []
    for event in events:
        if event.get("event_type") != "weight":
            continue
        value = _safe_float(event.get("value"))
        if value is None:
            continue
        series.append((parse_event_timestamp(event.get("timestamp")), value))
    series.sort(key=lambda pair: pair[0])
    return series


def _unknown_trend(sample_count: int, **extra: Any) -> dict[str, Any]:
    """Return an all-None trend summary carrying the true ``sample_count``.

    Callers can then explain *why* a trend is unknown ("2 readings in your
    90-day window") instead of rendering a bare blank.
    """
    return {
        "trend": "unknown",
        "change_pct": None,
        "sample_count": sample_count,
        "oldest_value": None,
        "newest_value": None,
        "over_days": None,
        **extra,
    }


def _trend_over(
    series: list[tuple[datetime, float]], threshold_pct: float
) -> dict[str, Any]:
    """Summarise an already-filtered, chronologically sorted weight series."""
    if len(series) < WEIGHT_TREND_MIN_POINTS:
        return _unknown_trend(len(series))

    oldest_ts, oldest_value = series[0]
    newest_ts, newest_value = series[-1]
    over_days = round((newest_ts - oldest_ts).total_seconds() / 86400, 1)

    if oldest_value == 0:
        # A zero starting reading makes a percentage change meaningless, and
        # dividing by it would raise. Report unknown rather than "stable" --
        # a 0 -> 50 lb series is many things, but stable is not one of them.
        return _unknown_trend(
            len(series),
            oldest_value=oldest_value,
            newest_value=newest_value,
            over_days=over_days,
        )

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
        "sample_count": len(series),
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

    series = _weight_series(events)

    lifetime = _trend_over(series, threshold_pct)

    if window_days is None:
        windowed = lifetime
    else:
        cutoff = now - timedelta(days=window_days)
        windowed = _trend_over(
            [pair for pair in series if pair[0] >= cutoff], threshold_pct
        )

    return {
        **windowed,
        "window_days": window_days,
        "threshold_pct": threshold_pct,
        # Echoed so a caller can say "you have 1 of the 3 readings needed"
        # without hardcoding the constant and silently desyncing from it.
        "min_samples": WEIGHT_TREND_MIN_POINTS,
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
        ts = parse_event_timestamp(ev.get("timestamp"))
        if ts >= current_cutoff:
            current.append(ts)
        elif ts >= previous_cutoff:
            previous_count += 1

    # days_since_last — unbounded: considers ALL sick events, not just windowed
    days_since_last: float | None = None
    if sick_events:
        most_recent = max(parse_event_timestamp(e.get("timestamp")) for e in sick_events)
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

    # An illness is "ongoing" when a cluster exists and the run is still live --
    # the last sick day is recent enough that another one would extend it rather
    # than start a new cluster. Derived here so an automation can trigger on it
    # without re-deriving the rule from cluster_size and days_since_last.
    cluster_active = (
        cluster_size >= 2
        and days_since_last is not None
        and days_since_last <= SICK_CLUSTER_GAP_DAYS
    )

    return {
        "count_current": len(current),
        "count_previous": previous_count,
        "cluster_size": cluster_size,
        "cluster_active": cluster_active,
        "days_since_last": days_since_last,
    }


# ---------------------------------------------------------------------------
# compute_routine_peaks
# ---------------------------------------------------------------------------


def _circular_distance(a: float, b: float) -> float:
    """Minutes between two times of day, going the short way round the clock.

    23:55 and 00:10 are fifteen minutes apart, not twenty-three hours. Plain
    subtraction gets that wrong, which is why a bedtime routine used to be
    unable to satisfy itself.
    """
    delta = abs(a - b) % MINUTES_PER_DAY
    return min(delta, MINUTES_PER_DAY - delta)


def _circular_mean(minutes: list[float]) -> float:
    """Average a set of times of day, respecting the midnight seam.

    Averaging 23:50 and 00:10 arithmetically gives midday; treating each time as
    a point on a circle and averaging the vectors gives midnight, which is what
    a human means.
    """
    angles = [2 * math.pi * m / MINUTES_PER_DAY for m in minutes]
    x = sum(math.cos(a) for a in angles)
    y = sum(math.sin(a) for a in angles)
    if abs(x) < 1e-12 and abs(y) < 1e-12:
        # Times spread perfectly evenly round the clock have no meaningful
        # centre; anything we return is arbitrary, so return the first.
        return minutes[0]
    mean_angle = math.atan2(y, x) % (2 * math.pi)
    return mean_angle * MINUTES_PER_DAY / (2 * math.pi)


def _cluster_times_of_day(
    stamped: list[tuple[float, Any]],
) -> list[list[tuple[float, Any]]]:
    """Group (minute-of-day, day) pairs into clusters, wrapping across midnight.

    Sorts by time of day and starts a new cluster wherever the gap to the
    previous event exceeds ``ROUTINE_CLUSTER_GAP_MINUTES``. The first and last
    clusters are merged if they are close across the midnight seam, so a routine
    that straddles it stays one routine.
    """
    if not stamped:
        return []

    ordered = sorted(stamped, key=lambda pair: pair[0])
    clusters: list[list[tuple[float, Any]]] = [[ordered[0]]]
    for entry in ordered[1:]:
        if entry[0] - clusters[-1][-1][0] <= ROUTINE_CLUSTER_GAP_MINUTES:
            clusters[-1].append(entry)
        else:
            clusters.append([entry])

    # Close the circle: the last cluster of the day may be the same routine as
    # the first cluster of the next.
    if len(clusters) > 1:
        wrap_gap = (MINUTES_PER_DAY - clusters[-1][-1][0]) + clusters[0][0][0]
        if wrap_gap <= ROUTINE_CLUSTER_GAP_MINUTES:
            clusters[0] = clusters.pop() + clusters[0]

    return clusters


def compute_routine_peaks(
    events: list[dict[str, Any]],
    event_type: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Detect recurring times of day for a given event type.

    Events are grouped by when in the day they happen -- splitting wherever a
    gap exceeds ``ROUTINE_CLUSTER_GAP_MINUTES``, and closing the circle across
    midnight -- and a group counts as a routine when it recurs on enough
    separate days. Fixed hour buckets were tried first and do not work: the same
    meal reads as one, two or three daily peaks depending only on where the hour
    boundary happens to fall relative to it, and a bedtime routine at 23:55
    splits into two peaks that the arithmetic then treats as 23 hours apart.

    Args:
        events:     List of event dicts (any mix of event types).
        event_type: The event type to analyse (e.g. "food", "walk").
        now:        Optional reference timestamp for "now". Defaults to
                    ``datetime.now(tz=timezone.utc)`` when *None*, but can be
                    overridden for deterministic testing. **Its timezone decides
                    the hours reported** -- see the module docstring.

    Returns:
        Dict with keys:
            peak_minutes      -- each routine's usual time, as minutes since
                                 local midnight. The precise form; callers that
                                 display a time should format this themselves,
                                 since 12- vs 24-hour is the reader's choice.
            histogram         -- 24-element list of counts per hour bucket.
                                 Fine for drawing a chart; deliberately not what
                                 any decision below is made from.
            status            -- "on_schedule", "late", or "unknown"
            last_event_ago_hours -- hours since the most recent matching event
                                 (or None)
            sample_count      -- number of matching events in the lookback window
            days_observed     -- distinct days the activity was logged at all,
                                 the denominator behind ROUTINE_MIN_DAY_FRACTION
            min_days_required -- days a cluster must recur on to count, so a
                                 caller can explain an "unknown" without
                                 hardcoding the constant
            overdue_peak_minute -- the routine that is late, as minutes since
                                 midnight (None unless status is "late")
            minutes_overdue   -- how long past its deadline that routine is
                                 (None unless status is "late")
    """
    if now is None:
        now = datetime.now(tz=timezone.utc)
    tz = now.tzinfo or timezone.utc
    cutoff = now - timedelta(days=ROUTINE_LOOKBACK_DAYS)

    # Normalise every timestamp into *now*'s zone up front, so that all the
    # hour-of-day arithmetic below is comparing like with like regardless of
    # which offset each event was stored with.
    matching: list[datetime] = []
    for ev in events:
        if ev.get("event_type") != event_type:
            continue
        ts = parse_event_timestamp(ev.get("timestamp"))
        if ts >= cutoff:
            matching.append(ts.astimezone(tz))

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

    # Group the events by time of day, then keep the groups that recur often
    # enough to call a routine.
    stamped = [(ts.hour * 60 + ts.minute + ts.second / 60, ts.date()) for ts in matching]
    days_observed = len({day for _, day in stamped})

    peak_minutes: list[int] = []
    for cluster in _cluster_times_of_day(stamped):
        cluster_days = len({day for _, day in cluster})
        if cluster_days < ROUTINE_MIN_CLUSTER_DAYS:
            continue
        if days_observed and cluster_days / days_observed < ROUTINE_MIN_DAY_FRACTION:
            continue
        # Rounded to the whole minute at the source: the trigonometry round-trip
        # lands a cluster of identical 08:00 events on 479.99999, which floors
        # to hour 7. A minute is also the finest resolution anything downstream
        # reports, so nothing is lost by settling it here.
        center = round(_circular_mean([minute for minute, _ in cluster]))
        peak_minutes.append(center % MINUTES_PER_DAY)
    peak_minutes.sort()

    # Schedule status
    overdue_peak_minute: float | None = None
    minutes_overdue: float | None = None

    if not peak_minutes:
        status = "unknown"
    else:
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = today_start + timedelta(days=1)
        today_minutes = [
            minute
            for minute, day in stamped
            if day == today_start.date()
        ]

        # A routine only becomes *due* once its grace period has elapsed: a walk
        # that usually happens at 22:30 is not late at 22:01. One whose grace
        # would run past midnight is judged shortly before the day rolls over
        # instead, so a late-evening routine can still report late while today's
        # events are still the ones being counted.
        overdue: list[tuple[float, float]] = []
        for minute in peak_minutes:
            occurrence = today_start + timedelta(minutes=minute)
            deadline = min(
                occurrence + timedelta(minutes=ROUTINE_LATE_THRESHOLD_MINUTES),
                day_end - ROUTINE_END_OF_DAY_MARGIN,
            )
            if deadline <= occurrence:
                # A routine this close to midnight cannot be judged inside the
                # day it belongs to. Saying nothing beats guessing.
                continue
            if now < deadline:
                continue
            covered = any(
                _circular_distance(minute, today_minute)
                <= ROUTINE_LATE_THRESHOLD_MINUTES
                for today_minute in today_minutes
            )
            if not covered:
                overdue.append(
                    (minute, (now - deadline).total_seconds() / 60)
                )

        if overdue:
            status = "late"
            # Report the one that has been waiting longest; it is the one a
            # person would want named.
            overdue_peak_minute, minutes_overdue = max(overdue, key=lambda o: o[1])
            minutes_overdue = round(minutes_overdue)
        else:
            status = "on_schedule"

    return {
        "peak_minutes": peak_minutes,
        "histogram": histogram,
        "status": status,
        "last_event_ago_hours": last_event_ago_hours,
        "sample_count": sample_count,
        "days_observed": days_observed,
        "min_days_required": ROUTINE_MIN_CLUSTER_DAYS,
        "overdue_peak_minute": (
            round(overdue_peak_minute) if overdue_peak_minute is not None else None
        ),
        "minutes_overdue": minutes_overdue,
    }
