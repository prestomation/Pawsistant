"""Export and import of all Pawsistant data.

This module is the Pawsistant side of Home Keeper's combined export and import (see
Home Keeper's ``docs/INTEGRATING.md``, section "Join the export and import"). Home
Keeper puts the ``data`` that :func:`build_export` makes in a section of its own
export file. Later, maybe on a different install, it gives that section back to
:func:`plan_import` as the ``document``.

The 2 functions here are pure. They import no Home Assistant code and do no I/O:

* :func:`build_export` turns a snapshot of the store into a portable document.
* :func:`plan_import` compares a document with a snapshot of the store and returns an
  :class:`ImportPlan`. The plan holds the full report (counts, records, problems) and
  every write. It does not write. The store applies a plan that has no error.

Rules of the import:

* It is an upsert. A dog matches by id, then by name (case-insensitive). A care
  schedule matches by id, then by its pair of dog and event type. An event matches by
  id. The import never deletes a record that is not in the document.
* A document with a ``format`` higher than :data:`FORMAT` is refused.
* A care schedule is exported without its Home Keeper ``task_id``, because that id is
  known only to 1 install. The reconcile in ``care_link`` makes the task again.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .const import (
    CARE_FREQS,
    CARE_UNITS,
    DEFAULT_EVENT_TYPES,
    EVENT_TYPE_KEY_RE,
    HEX_COLOR_RE,
    MAX_EVENT_TYPE_KEY_LEN,
    MDI_ICON_RE,
    VALID_BUTTON_METRICS,
)

# The format of the exported ``data``. Increase it only when the meaning of a key
# changes. An import refuses a document with a higher format.
FORMAT = 1

# The top-level keys of the exported ``data``.
DOCUMENT_KEYS = (
    "format",
    "dogs",
    "event_types",
    "button_metrics",
    "shown_types",
    "care_schedules",
    "events",
)

# The dog fields that are copied. ``name`` is required, the others are optional.
DOG_FIELDS = ("name", "breed", "birth_date", "species")
# The event fields that are compared to decide if an existing event changed.
EVENT_FIELDS = ("dog_id", "event_type", "timestamp", "note", "value")
# The schedule fields that set the cadence of the Home Keeper task.
CADENCE_FIELDS = ("recurrence_type", "interval", "unit", "freq", "anchor")

ERROR = "error"
WARNING = "warning"


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def _sort_key(timestamp: Any) -> datetime:
    """Return a sort key for an event timestamp. A bad value sorts as the oldest."""
    parsed = parse_aware_timestamp(timestamp)
    return parsed if parsed is not None else datetime.min.replace(tzinfo=timezone.utc)


def _export_timestamp(value: Any) -> Any:
    """Return *value* with UTC added when it has no timezone.

    The store reads a timestamp without a timezone as UTC (``store._parse_timestamp``). The
    export writes that zone, so that the import, which refuses such a timestamp,
    accepts every export. A value that does not parse stays as it is.
    """
    if not isinstance(value, str) or not value:
        return value
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value
    if parsed.tzinfo is not None:
        return value
    return parsed.replace(tzinfo=timezone.utc).isoformat()


def build_export(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return the portable ``data`` document for *snapshot*.

    *snapshot* has these keys:

    * ``dogs`` — ``{dog_id: {name, breed, birth_date, species}}``
    * ``event_types`` — the stored event type overrides (a ``None`` value is a
      tombstone for a built-in type)
    * ``button_metrics`` — the stored button metric overrides
    * ``care_schedules`` — ``{schedule_id: {...}}``
    * ``shown_types`` — ``{dog_id: [event_type, ...]}``
    * ``events`` — every event of every year file
    """
    dogs = [
        {"id": dog_id, **{k: dog[k] for k in DOG_FIELDS if k in dog}}
        for dog_id, dog in snapshot.get("dogs", {}).items()
    ]
    dogs.sort(key=lambda d: (str(d.get("name", "")).lower(), d["id"]))

    schedules = [
        {"id": schedule_id, **{k: v for k, v in schedule.items() if k != "task_id"}}
        for schedule_id, schedule in snapshot.get("care_schedules", {}).items()
    ]
    schedules.sort(key=lambda s: s["id"])

    events = [dict(event) for event in snapshot.get("events", [])]
    for event in events:
        if "timestamp" in event:
            event["timestamp"] = _export_timestamp(event["timestamp"])
    # Newest first, as in the year files. The id breaks a tie so that 2 exports of
    # the same data are equal.
    events.sort(key=lambda e: str(e.get("id", "")))
    events.sort(key=lambda e: _sort_key(e.get("timestamp")), reverse=True)

    return {
        "format": FORMAT,
        "dogs": dogs,
        "event_types": dict(snapshot.get("event_types", {})),
        "button_metrics": dict(snapshot.get("button_metrics", {})),
        "shown_types": {
            dog_id: list(types)
            for dog_id, types in snapshot.get("shown_types", {}).items()
        },
        "care_schedules": schedules,
        "events": events,
    }


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


def parse_aware_timestamp(value: Any) -> datetime | None:
    """Return *value* as a timezone-aware datetime, or None.

    A timestamp without a timezone gives None: its zone is not known, so the import
    does not guess it.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


@dataclass
class ImportPlan:
    """The result of :func:`plan_import`: the report and every write.

    The write fields use the ids of the target install. A dog that matched by name
    uses the id of the dog that is already in the store.
    """

    problems: list[dict[str, str]] = field(default_factory=list)
    records: list[dict[str, Any]] = field(default_factory=list)
    counts: dict[str, dict[str, int]] = field(default_factory=dict)
    # dog_id -> the full dog dict to write.
    dogs: dict[str, dict[str, Any]] = field(default_factory=dict)
    # event type key -> the override to write (a dict, or None for a tombstone).
    event_types: dict[str, Any] = field(default_factory=dict)
    # event type key -> the metric to write.
    button_metrics: dict[str, str] = field(default_factory=dict)
    # dog_id -> the shown types to write.
    shown_types: dict[str, list[str]] = field(default_factory=dict)
    # schedule_id -> the schedule fields to write, without ``task_id``.
    care_schedules: dict[str, dict[str, Any]] = field(default_factory=dict)
    # The ids of the existing schedules whose cadence changed. Their Home Keeper
    # task has the old cadence, so it is replaced.
    replaced_tasks: set[str] = field(default_factory=set)
    # The full events to write: new events, and changed events that replace the
    # event with the same id.
    events: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True if no problem has the level ``error``."""
        return not any(p["level"] == ERROR for p in self.problems)

    @property
    def has_changes(self) -> bool:
        """Return True if the plan writes at least 1 record."""
        return any(
            (
                self.dogs,
                self.event_types,
                self.button_metrics,
                self.shown_types,
                self.care_schedules,
                self.events,
            )
        )

    def report(self, *, dry_run: bool) -> dict[str, Any]:
        """Return the service response ``{ok, dry_run, counts, records, problems}``."""
        return {
            "ok": self.ok,
            "dry_run": dry_run,
            "counts": self.counts,
            "records": list(self.records),
            "problems": list(self.problems),
        }


class _Planner:
    """Build one :class:`ImportPlan`. Each ``_plan_*`` method does 1 section."""

    def __init__(
        self,
        document: dict[str, Any],
        current: dict[str, Any],
        new_id: Callable[[], str],
    ) -> None:
        self.doc = document
        self.cur = current
        self.new_id = new_id
        self.plan = ImportPlan()
        # Document dog id -> target dog id. A dog id that is only in the store maps
        # to itself (see _resolve_dog).
        self.dog_map: dict[str, str] = {}
        self.cur_dogs: dict[str, dict[str, Any]] = current.get("dogs", {})
        # The resolved event type registry after the import, and every key that the
        # store or the document knows (a tombstoned key too).
        self.active_types: set[str] = set()
        self.known_types: set[str] = set()

    # -- helpers ----------------------------------------------------------------

    def problem(self, level: str, path: str, message: str) -> None:
        self.plan.problems.append({"level": level, "path": path, "message": message})

    def count(self, section: str, outcome: str) -> None:
        bucket = self.plan.counts.setdefault(
            section, {"created": 0, "updated": 0, "unchanged": 0}
        )
        bucket[outcome] += 1

    def record(
        self,
        section: str,
        index: int | None,
        record_id: str,
        name: str,
        action: str,
        matched_by: str | None,
    ) -> None:
        self.count(section, action + "d" if action != "unchanged" else action)
        if action == "unchanged":
            return
        self.plan.records.append(
            {
                "section": section,
                "index": index,
                "id": record_id,
                "name": name,
                "action": action,
                "matched_by": matched_by,
            }
        )

    def section_list(self, key: str) -> list[Any]:
        value = self.doc.get(key, [])
        if not isinstance(value, list):
            self.problem(ERROR, key, f"'{key}' must be a list.")
            return []
        return value

    def section_dict(self, key: str) -> dict[str, Any]:
        value = self.doc.get(key, {})
        if not isinstance(value, dict):
            self.problem(ERROR, key, f"'{key}' must be an object.")
            return {}
        return value

    def _resolve_dog(self, dog_id: Any, path: str) -> str | None:
        """Return the target dog id for a dog id in the document, or None."""
        if not isinstance(dog_id, str) or not dog_id:
            self.problem(ERROR, path, "The dog id must be a text value.")
            return None
        if dog_id in self.dog_map:
            return self.dog_map[dog_id]
        if dog_id in self.cur_dogs:
            return dog_id
        self.problem(
            ERROR,
            path,
            f"The dog id '{dog_id}' is not in 'dogs' and not on this install.",
        )
        return None

    # -- sections ---------------------------------------------------------------

    def plan_format(self) -> bool:
        declared = self.doc.get("format", FORMAT)
        if isinstance(declared, bool) or not isinstance(declared, int):
            self.problem(ERROR, "format", "'format' must be an integer.")
            return False
        if declared > FORMAT:
            self.problem(
                ERROR,
                "format",
                f"This document has format {declared}. This version of Pawsistant "
                f"reads format {FORMAT} or lower. Update Pawsistant, then try again.",
            )
            return False
        for key in self.doc:
            if key not in DOCUMENT_KEYS:
                self.problem(
                    WARNING, key, f"Pawsistant does not know the key '{key}'. It is ignored."
                )
        return True

    def plan_dogs(self) -> None:
        names_by_target: dict[str, str] = {
            dog_id: str(dog.get("name", "")) for dog_id, dog in self.cur_dogs.items()
        }
        name_index = {name.lower(): dog_id for dog_id, name in names_by_target.items()}
        claimed: dict[str, str] = {}  # target id -> path of the document dog
        seen_ids: set[str] = set()
        pending: list[tuple[int, str, dict[str, Any], str, str | None]] = []

        for i, raw in enumerate(self.section_list("dogs")):
            path = f"dogs[{i}]"
            if not isinstance(raw, dict):
                self.problem(ERROR, path, "A dog must be an object.")
                continue
            name = raw.get("name")
            if not isinstance(name, str) or not name.strip():
                self.problem(ERROR, f"{path}.name", "A dog must have a name.")
                continue
            name = name.strip()
            bad_field = False
            for key in DOG_FIELDS[1:]:
                if key in raw and not isinstance(raw[key], str):
                    self.problem(ERROR, f"{path}.{key}", f"'{key}' must be a text value.")
                    bad_field = True
            if bad_field:
                continue
            doc_id = raw.get("id")
            if doc_id is not None and (not isinstance(doc_id, str) or not doc_id):
                self.problem(ERROR, f"{path}.id", "The id must be a text value.")
                continue
            if doc_id is not None:
                if doc_id in seen_ids:
                    self.problem(ERROR, f"{path}.id", f"The id '{doc_id}' is used 2 times.")
                    continue
                seen_ids.add(doc_id)

            if doc_id is not None and doc_id in self.cur_dogs:
                target, matched_by = doc_id, "id"
            elif name.lower() in name_index:
                target, matched_by = name_index[name.lower()], "name"
            else:
                target, matched_by = doc_id or self.new_id(), None
            if target in claimed:
                self.problem(
                    ERROR,
                    path,
                    f"This dog and {claimed[target]} are the same dog on this install.",
                )
                continue
            claimed[target] = path
            if doc_id is not None:
                self.dog_map[doc_id] = target
            names_by_target[target] = name
            pending.append((i, target, raw, name, matched_by))

        # The names must stay unique after the import, because services find a dog
        # by its name.
        owners: dict[str, list[str]] = {}
        for target, name in names_by_target.items():
            owners.setdefault(name.lower(), []).append(target)
        for i, target, raw, name, matched_by in pending:
            if len(owners[name.lower()]) > 1:
                self.problem(
                    ERROR,
                    f"dogs[{i}].name",
                    f"After the import, 2 dogs have the name '{name}'.",
                )
                continue
            existing = self.cur_dogs.get(target)
            new_dog = dict(existing or {})
            new_dog.update({k: raw[k] for k in DOG_FIELDS[1:] if k in raw})
            new_dog["name"] = name
            if existing is None:
                new_dog.setdefault("breed", "")
                new_dog.setdefault("birth_date", "")
                new_dog["species"] = new_dog.get("species") or "Dog"
                action = "create"
            elif new_dog != existing:
                action = "update"
            else:
                action = "unchanged"
            if action != "unchanged":
                self.plan.dogs[target] = new_dog
            self.record("dogs", i, target, name, action, matched_by)

    def plan_event_types(self) -> None:
        stored: dict[str, Any] = self.cur.get("event_types", {})
        merged = dict(stored)
        for key, value in self.section_dict("event_types").items():
            path = f"event_types.{key}"
            if (
                not isinstance(key, str)
                or len(key) > MAX_EVENT_TYPE_KEY_LEN
                or not EVENT_TYPE_KEY_RE.match(key)
            ):
                self.problem(
                    ERROR,
                    path,
                    "An event type key uses only a-z, 0-9 and _, and has at most "
                    f"{MAX_EVENT_TYPE_KEY_LEN} characters.",
                )
                continue
            if value is not None and not self._valid_event_type(value, path):
                continue
            if value is None and key not in DEFAULT_EVENT_TYPES and key not in stored:
                # A tombstone for a custom type that is not here removes nothing.
                continue
            merged[key] = value
            if key not in stored:
                action = "create"
            elif stored[key] != value:
                action = "update"
            else:
                action = "unchanged"
            if action != "unchanged":
                self.plan.event_types[key] = value
            name = value.get("name", key) if isinstance(value, dict) else key
            self.record("event_types", None, key, name, action, "id" if key in stored else None)

        self.active_types = set(DEFAULT_EVENT_TYPES)
        for key, value in merged.items():
            if value is None:
                self.active_types.discard(key)
            elif value:
                self.active_types.add(key)
        self.known_types = set(DEFAULT_EVENT_TYPES) | set(merged)

    def _valid_event_type(self, value: Any, path: str) -> bool:
        if not isinstance(value, dict):
            self.problem(ERROR, path, "An event type must be an object or null.")
            return False
        ok = True
        name = value.get("name")
        if not isinstance(name, str) or not name.strip():
            self.problem(ERROR, f"{path}.name", "An event type must have a name.")
            ok = False
        icon = value.get("icon")
        if not isinstance(icon, str) or not MDI_ICON_RE.match(icon):
            self.problem(ERROR, f"{path}.icon", "The icon must look like mdi:walk.")
            ok = False
        color = value.get("color")
        if not isinstance(color, str) or not HEX_COLOR_RE.match(color):
            self.problem(ERROR, f"{path}.color", "The color must look like #4CAF50.")
            ok = False
        return ok

    def plan_button_metrics(self) -> None:
        stored: dict[str, str] = self.cur.get("button_metrics", {})
        for key, value in self.section_dict("button_metrics").items():
            path = f"button_metrics.{key}"
            if value not in VALID_BUTTON_METRICS:
                self.problem(
                    ERROR,
                    path,
                    f"The metric must be 1 of: {', '.join(VALID_BUTTON_METRICS)}.",
                )
                continue
            if key not in stored:
                action = "create"
            elif stored[key] != value:
                action = "update"
            else:
                action = "unchanged"
            if action != "unchanged":
                self.plan.button_metrics[key] = value
            self.record("button_metrics", None, key, key, action, "id" if key in stored else None)

    def plan_shown_types(self) -> None:
        stored: dict[str, list[str]] = self.cur.get("shown_types", {})
        for doc_dog_id, value in self.section_dict("shown_types").items():
            path = f"shown_types.{doc_dog_id}"
            target = self._resolve_dog(doc_dog_id, path)
            if target is None:
                continue
            if not isinstance(value, list) or not all(isinstance(t, str) for t in value):
                self.problem(ERROR, path, "The shown types must be a list of text values.")
                continue
            unknown = [t for t in value if t not in self.known_types]
            if unknown:
                self.problem(
                    WARNING,
                    path,
                    f"These event types are not known: {', '.join(unknown)}.",
                )
            if target not in stored:
                action = "create"
            elif stored[target] != value:
                action = "update"
            else:
                action = "unchanged"
            if action != "unchanged":
                self.plan.shown_types[target] = list(value)
            self.record("shown_types", None, target, target, action, None)

    def plan_care_schedules(self) -> None:
        current: dict[str, dict[str, Any]] = self.cur.get("care_schedules", {})
        by_pair = {
            (s.get("dog_id"), s.get("event_type")): sid for sid, s in current.items()
        }
        seen_ids: set[str] = set()
        claimed: dict[str, str] = {}
        pairs: dict[tuple[str, str], str] = {}

        for i, raw in enumerate(self.section_list("care_schedules")):
            path = f"care_schedules[{i}]"
            if not isinstance(raw, dict):
                self.problem(ERROR, path, "A care schedule must be an object.")
                continue
            schedule = self._valid_schedule(raw, path)
            if schedule is None:
                continue
            pair = (schedule["dog_id"], schedule["event_type"])
            if pair in pairs:
                self.problem(
                    ERROR,
                    path,
                    f"This schedule and {pairs[pair]} are for the same dog and event type.",
                )
                continue
            pairs[pair] = path
            doc_id = raw.get("id")
            if doc_id is not None and (not isinstance(doc_id, str) or not doc_id):
                self.problem(ERROR, f"{path}.id", "The id must be a text value.")
                continue
            if doc_id is not None:
                if doc_id in seen_ids:
                    self.problem(ERROR, f"{path}.id", f"The id '{doc_id}' is used 2 times.")
                    continue
                seen_ids.add(doc_id)

            if doc_id is not None and doc_id in current:
                target, matched_by = doc_id, "id"
            elif pair in by_pair:
                target, matched_by = by_pair[pair], "dog_and_event_type"
            else:
                target, matched_by = doc_id or uuid.uuid4().hex, None  # same shape as the options flow
            if target in claimed:
                self.problem(
                    ERROR,
                    path,
                    f"This schedule and {claimed[target]} are the same schedule here.",
                )
                continue
            claimed[target] = path
            # A schedule matched by id can change its pair. Then the new pair must
            # not belong to another schedule on this install.
            other = by_pair.get(pair)
            if other is not None and other != target:
                self.problem(
                    ERROR,
                    path,
                    "Another care schedule on this install has this dog and event type.",
                )
                continue

            existing = current.get(target)
            old = {k: v for k, v in (existing or {}).items() if k != "task_id"}
            if existing is None:
                action = "create"
            elif old != schedule:
                action = "update"
                if any(old.get(k) != schedule.get(k) for k in CADENCE_FIELDS) or (
                    old.get("dog_id"),
                    old.get("event_type"),
                ) != pair:
                    self.plan.replaced_tasks.add(target)
            else:
                action = "unchanged"
            if action != "unchanged":
                self.plan.care_schedules[target] = schedule
            dog_name = self._dog_name(schedule["dog_id"])
            self.record(
                "care_schedules",
                i,
                target,
                f"{dog_name}: {schedule['event_type']}",
                action,
                matched_by,
            )

    def _dog_name(self, target: str) -> str:
        dog = self.plan.dogs.get(target) or self.cur_dogs.get(target) or {}
        return str(dog.get("name", target))

    def _valid_schedule(self, raw: dict[str, Any], path: str) -> dict[str, Any] | None:
        dog = self._resolve_dog(raw.get("dog_id"), f"{path}.dog_id")
        event_type = raw.get("event_type")
        ok = dog is not None
        if not isinstance(event_type, str) or event_type not in self.active_types:
            self.problem(
                ERROR,
                f"{path}.event_type",
                f"The event type '{event_type}' does not exist.",
            )
            ok = False
        interval = raw.get("interval", 1)
        if isinstance(interval, bool) or not isinstance(interval, int) or interval < 1:
            self.problem(ERROR, f"{path}.interval", "The interval must be 1 or more.")
            ok = False
        kind = raw.get("recurrence_type", "floating")
        schedule: dict[str, Any] = {
            "dog_id": dog,
            "event_type": event_type,
            "recurrence_type": kind,
            "interval": interval,
        }
        if kind == "floating":
            unit = raw.get("unit", "weeks")
            if unit not in CARE_UNITS:
                self.problem(
                    ERROR, f"{path}.unit", f"The unit must be 1 of: {', '.join(CARE_UNITS)}."
                )
                ok = False
            schedule["unit"] = unit
        elif kind == "fixed":
            freq = raw.get("freq", "MONTHLY")
            if freq not in CARE_FREQS:
                self.problem(
                    ERROR, f"{path}.freq", f"The freq must be 1 of: {', '.join(CARE_FREQS)}."
                )
                ok = False
            anchor = raw.get("anchor")
            if parse_aware_timestamp(anchor) is None and not _is_date(anchor):
                self.problem(
                    ERROR,
                    f"{path}.anchor",
                    "A fixed schedule must have an anchor date in ISO 8601 format.",
                )
                ok = False
            schedule["freq"] = freq
            schedule["anchor"] = anchor
        else:
            self.problem(
                ERROR,
                f"{path}.recurrence_type",
                "The recurrence type must be 'floating' or 'fixed'.",
            )
            ok = False
        return schedule if ok else None

    def plan_events(self) -> None:
        current: dict[str, dict[str, Any]] = self.cur.get("events", {})
        seen_ids: set[str] = set()
        for i, raw in enumerate(self.section_list("events")):
            path = f"events[{i}]"
            if not isinstance(raw, dict):
                self.problem(ERROR, path, "An event must be an object.")
                continue
            event = self._valid_event(raw, path)
            if event is None:
                continue
            event_id = raw.get("id")
            if event_id is not None and (not isinstance(event_id, str) or not event_id):
                self.problem(ERROR, f"{path}.id", "The id must be a text value.")
                continue
            if event_id is None:
                event_id = self.new_id()
            elif event_id in seen_ids:
                self.problem(ERROR, f"{path}.id", f"The id '{event_id}' is used 2 times.")
                continue
            seen_ids.add(event_id)
            event = {"id": event_id, **event}

            existing = current.get(event_id)
            if existing is None:
                action = "create"
            elif any(existing.get(k) != event.get(k) for k in EVENT_FIELDS):
                action = "update"
            else:
                action = "unchanged"
            if action != "unchanged":
                self.plan.events.append(event)
            # Only counted: a store can hold many thousands of events, which would
            # make the list of records too long to read.
            self.count("events", action + "d" if action != "unchanged" else action)

    def _valid_event(self, raw: dict[str, Any], path: str) -> dict[str, Any] | None:
        dog = self._resolve_dog(raw.get("dog_id"), f"{path}.dog_id")
        ok = dog is not None
        event_type = raw.get("event_type")
        if not isinstance(event_type, str) or not event_type:
            self.problem(ERROR, f"{path}.event_type", "An event must have an event type.")
            ok = False
        elif event_type not in self.known_types:
            # Deleting an event type can keep its events, so a store can hold events
            # of a type that it does not know. Keep them, as that store does.
            self.problem(
                WARNING,
                f"{path}.event_type",
                f"The event type '{event_type}' is not known. The event is kept.",
            )
        timestamp = raw.get("timestamp")
        if parse_aware_timestamp(timestamp) is None:
            self.problem(
                ERROR,
                f"{path}.timestamp",
                "The timestamp must be ISO 8601 with a timezone, for example "
                "2026-05-01T08:30:00+00:00.",
            )
            ok = False
        note = raw.get("note", "")
        if note is None:
            note = ""
        if not isinstance(note, str):
            self.problem(ERROR, f"{path}.note", "The note must be a text value.")
            ok = False
        value = raw.get("value")
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, (int, float))
        ):
            self.problem(ERROR, f"{path}.value", "The value must be a number.")
            ok = False
        if not ok:
            return None
        event: dict[str, Any] = {
            "dog_id": dog,
            "event_type": event_type,
            "timestamp": timestamp,
            "note": note,
        }
        if value is not None:
            event["value"] = value
        return event


def _is_date(value: Any) -> bool:
    """Return True if *value* is an ISO 8601 date or datetime text value."""
    if not isinstance(value, str) or not value:
        return False
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


def unwrap_document(document: Any) -> Any:
    """Return the ``data`` of *document*.

    The contract gives the ``data`` that the export returned. For convenience, the
    full export response ``{format, version, data, skipped}`` is accepted too. Then
    its ``format`` is copied into the data, so the format check sees it.
    """
    if (
        isinstance(document, dict)
        and isinstance(document.get("data"), dict)
        and "dogs" not in document
    ):
        data = dict(document["data"])
        if "format" in document:
            data["format"] = document["format"]
        return data
    return document


def plan_import(
    document: Any,
    current: dict[str, Any],
    *,
    new_id: Callable[[], str] | None = None,
) -> ImportPlan:
    """Compare *document* with *current* and return the plan. Write nothing.

    *current* is a snapshot of the store. It has the same keys as the snapshot of
    :func:`build_export`, but ``events`` is ``{event_id: event}``.

    *new_id* makes the id of a new dog or event that has no id in the document.
    """
    make_id = new_id or (lambda: str(uuid.uuid4()))
    document = unwrap_document(document)
    if not isinstance(document, dict):
        plan = ImportPlan()
        plan.problems.append(
            {"level": ERROR, "path": "", "message": "The document must be an object."}
        )
        return plan
    planner = _Planner(document, current, make_id)
    if not planner.plan_format():
        return planner.plan
    # Dogs and event types come first: the other sections refer to them.
    planner.plan_dogs()
    planner.plan_event_types()
    planner.plan_button_metrics()
    planner.plan_shown_types()
    planner.plan_care_schedules()
    planner.plan_events()
    return planner.plan
