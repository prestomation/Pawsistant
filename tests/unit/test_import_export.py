"""Unit tests for the pure export and import planner (import_export.py).

The module imports only ``const``, so the 2 files are loaded from disk into a small
stand-in package. No Home Assistant code runs here.
"""

from __future__ import annotations

import copy
import importlib.util
import itertools
import pathlib
import sys
import types

import pytest

_PKG_DIR = pathlib.Path(__file__).parent.parent.parent / "custom_components" / "pawsistant"


def _load(name: str):
    full = f"_pawsistant_ie.{name}"
    spec = importlib.util.spec_from_file_location(full, _PKG_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[full] = mod
    spec.loader.exec_module(mod)
    return mod


if "_pawsistant_ie" not in sys.modules:
    _pkg = types.ModuleType("_pawsistant_ie")
    _pkg.__path__ = [str(_PKG_DIR)]
    sys.modules["_pawsistant_ie"] = _pkg
    _load("const")
ie = sys.modules.get("_pawsistant_ie.import_export") or _load("import_export")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ids():
    counter = itertools.count(1)
    return lambda: f"new-{next(counter)}"


def _empty() -> dict:
    return {
        "dogs": {},
        "event_types": {},
        "button_metrics": {},
        "care_schedules": {},
        "shown_types": {},
        "events": {},
    }


def _sample_store() -> dict:
    """A snapshot in the shape of PawsistantStore.export_snapshot()."""
    return {
        "dogs": {
            "dog-a": {"name": "Buddy", "breed": "Lab", "birth_date": "2020-01-02", "species": "Dog"},
            "dog-b": {"name": "Mochi", "breed": "", "birth_date": "", "species": "Cat"},
        },
        "event_types": {
            "zoomies": {"name": "Zoomies", "icon": "mdi:run", "color": "#123456"},
            "sick": None,
        },
        "button_metrics": {"zoomies": "hours_since"},
        "care_schedules": {
            "s1": {
                "dog_id": "dog-a",
                "event_type": "medicine",
                "recurrence_type": "floating",
                "interval": 2,
                "unit": "weeks",
                "task_id": "hk-task-1",
            },
            "s2": {
                "dog_id": "dog-b",
                "event_type": "grooming",
                "recurrence_type": "fixed",
                "interval": 1,
                "freq": "MONTHLY",
                "anchor": "2026-03-01T09:00:00+00:00",
                "task_id": None,
            },
        },
        "shown_types": {"dog-a": ["walk", "zoomies"], "dog-b": ["food"]},
        "events": [
            {"id": "e1", "dog_id": "dog-a", "event_type": "walk",
             "timestamp": "2025-12-31T23:00:00+00:00", "note": ""},
            {"id": "e2", "dog_id": "dog-a", "event_type": "weight",
             "timestamp": "2026-02-01T08:00:00-08:00", "note": "vet", "value": 30.5},
            {"id": "e3", "dog_id": "dog-b", "event_type": "zoomies",
             "timestamp": "2026-04-01T10:00:00+00:00", "note": ""},
        ],
    }


def _as_current(snapshot: dict) -> dict:
    current = copy.deepcopy(snapshot)
    current["events"] = {e["id"]: e for e in current["events"]}
    return current


def _apply(plan, snapshot: dict) -> dict:
    """Apply a plan to a snapshot, as PawsistantStore.apply_import does."""
    out = copy.deepcopy(snapshot)
    out["dogs"].update(copy.deepcopy(plan.dogs))
    out["event_types"].update(plan.event_types)
    out["button_metrics"].update(plan.button_metrics)
    out["shown_types"].update(plan.shown_types)
    for sid, schedule in plan.care_schedules.items():
        task_id = (out["care_schedules"].get(sid) or {}).get("task_id")
        if sid in plan.replaced_tasks:
            task_id = None
        out["care_schedules"][sid] = {**schedule, "task_id": task_id}
    by_id = {e["id"]: e for e in out["events"]}
    for event in plan.events:
        by_id[event["id"]] = dict(event)
    out["events"] = list(by_id.values())
    return out


def _errors(plan) -> list[dict]:
    return [p for p in plan.problems if p["level"] == "error"]


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


class TestExport:
    def test_shape(self):
        data = ie.build_export(_sample_store())
        assert data["format"] == ie.FORMAT == 1
        assert set(data) == set(ie.DOCUMENT_KEYS)
        assert data["dogs"][0] == {
            "id": "dog-a", "name": "Buddy", "breed": "Lab",
            "birth_date": "2020-01-02", "species": "Dog",
        }
        assert data["event_types"]["sick"] is None
        assert data["shown_types"] == {"dog-a": ["walk", "zoomies"], "dog-b": ["food"]}

    def test_care_schedules_have_no_task_id(self):
        data = ie.build_export(_sample_store())
        assert [s["id"] for s in data["care_schedules"]] == ["s1", "s2"]
        assert all("task_id" not in s for s in data["care_schedules"])

    def test_events_newest_first(self):
        data = ie.build_export(_sample_store())
        assert [e["id"] for e in data["events"]] == ["e3", "e2", "e1"]
        assert data["events"][1]["value"] == 30.5

    def test_export_does_not_change_the_snapshot(self):
        snapshot = _sample_store()
        before = copy.deepcopy(snapshot)
        ie.build_export(snapshot)
        assert snapshot == before


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_export_import_into_empty_export_is_equal(self):
        source = _sample_store()
        exported = ie.build_export(source)

        plan = ie.plan_import(copy.deepcopy(exported), _empty(), new_id=_ids())
        assert plan.ok, plan.problems
        assert plan.counts["dogs"]["created"] == 2
        assert plan.counts["events"]["created"] == 3
        assert plan.counts["care_schedules"]["created"] == 2

        empty_snapshot = {**_empty(), "events": []}
        target = _apply(plan, empty_snapshot)
        assert ie.build_export(target) == exported
        # A new schedule has no Home Keeper task yet; reconcile makes it.
        assert all(s["task_id"] is None for s in target["care_schedules"].values())

    def test_import_into_the_same_store_changes_nothing(self):
        source = _sample_store()
        plan = ie.plan_import(ie.build_export(source), _as_current(source))
        assert plan.ok, plan.problems
        assert not plan.has_changes
        assert plan.records == []
        assert plan.counts["events"] == {"created": 0, "updated": 0, "unchanged": 3}
        # The task id of an unchanged schedule stays.
        assert plan.replaced_tasks == set()

    def test_the_full_export_response_is_accepted(self):
        source = _sample_store()
        envelope = {"format": 1, "version": "2.23.1", "data": ie.build_export(source), "skipped": {}}
        plan = ie.plan_import(envelope, _as_current(source))
        assert plan.ok, plan.problems
        assert not plan.has_changes

    def test_report_shape(self):
        plan = ie.plan_import(ie.build_export(_sample_store()), _empty(), new_id=_ids())
        report = plan.report(dry_run=True)
        assert set(report) == {"ok", "dry_run", "counts", "records", "problems"}
        assert report["dry_run"] is True
        record = next(r for r in report["records"] if r["section"] == "dogs")
        assert record == {
            "section": "dogs", "index": 0, "id": "dog-a", "name": "Buddy",
            "action": "create", "matched_by": None,
        }


class TestFormat:
    def test_higher_format_is_refused(self):
        doc = ie.build_export(_sample_store())
        doc["format"] = ie.FORMAT + 1
        plan = ie.plan_import(doc, _empty())
        assert not plan.ok
        assert _errors(plan)[0]["path"] == "format"
        assert not plan.has_changes

    def test_higher_format_in_the_envelope_is_refused(self):
        envelope = {"format": 2, "data": ie.build_export(_sample_store())}
        plan = ie.plan_import(envelope, _empty())
        assert [p["path"] for p in _errors(plan)] == ["format"]

    def test_missing_format_means_the_current_one(self):
        doc = ie.build_export(_sample_store())
        del doc["format"]
        assert ie.plan_import(doc, _empty()).ok

    def test_document_must_be_an_object(self):
        plan = ie.plan_import(["no"], _empty())
        assert not plan.ok

    def test_unknown_key_is_a_warning(self):
        doc = {"format": 1, "cats": []}
        plan = ie.plan_import(doc, _empty())
        assert plan.ok
        assert plan.problems == [
            {"level": "warning", "path": "cats",
             "message": "Pawsistant does not know the key 'cats'. It is ignored."}
        ]


class TestDogs:
    def test_name_fallback_maps_ids(self):
        """A dog with another id but the same name is the same dog."""
        current = _empty()
        current["dogs"] = {"local-id": {"name": "Buddy", "breed": "", "birth_date": "", "species": "Dog"}}
        doc = {
            "dogs": [{"id": "far-id", "name": "buddy", "breed": "Lab"}],
            "events": [{"id": "e9", "dog_id": "far-id", "event_type": "walk",
                        "timestamp": "2026-01-01T10:00:00+00:00"}],
            "care_schedules": [{"id": "s9", "dog_id": "far-id", "event_type": "walk",
                                "recurrence_type": "floating", "interval": 1, "unit": "days"}],
            "shown_types": {"far-id": ["walk"]},
        }
        plan = ie.plan_import(doc, current)
        assert plan.ok, plan.problems
        assert list(plan.dogs) == ["local-id"]
        assert plan.dogs["local-id"]["breed"] == "Lab"
        assert plan.records[0]["matched_by"] == "name"
        assert plan.events[0]["dog_id"] == "local-id"
        assert plan.care_schedules["s9"]["dog_id"] == "local-id"
        assert plan.shown_types == {"local-id": ["walk"]}

    def test_match_by_id_wins_over_name(self):
        current = _empty()
        current["dogs"] = {"d1": {"name": "Rex", "species": "Dog"}}
        plan = ie.plan_import({"dogs": [{"id": "d1", "name": "Max"}]}, current)
        assert plan.ok
        assert plan.dogs["d1"]["name"] == "Max"
        assert plan.records[0]["matched_by"] == "id"
        assert plan.records[0]["action"] == "update"

    def test_new_dog_keeps_its_id(self):
        plan = ie.plan_import({"dogs": [{"id": "keep-me", "name": "Rex"}]}, _empty())
        assert plan.dogs == {
            "keep-me": {"name": "Rex", "breed": "", "birth_date": "", "species": "Dog"}
        }

    def test_new_dog_without_id_gets_one(self):
        plan = ie.plan_import({"dogs": [{"name": "Rex"}]}, _empty(), new_id=_ids())
        assert list(plan.dogs) == ["new-1"]

    def test_dog_without_name_is_an_error(self):
        plan = ie.plan_import({"dogs": [{"id": "x"}]}, _empty())
        assert _errors(plan)[0]["path"] == "dogs[0].name"

    def test_rename_onto_another_dog_is_an_error(self):
        current = _empty()
        current["dogs"] = {"d1": {"name": "Rex"}, "d2": {"name": "Max"}}
        plan = ie.plan_import({"dogs": [{"id": "d1", "name": "max"}]}, current)
        assert [p["path"] for p in _errors(plan)] == ["dogs[0].name"]

    def test_two_document_dogs_for_one_dog_is_an_error(self):
        current = _empty()
        current["dogs"] = {"d1": {"name": "Rex"}}
        doc = {"dogs": [{"id": "d1", "name": "Rex"}, {"id": "other", "name": "rex"}]}
        plan = ie.plan_import(doc, current)
        assert [p["path"] for p in _errors(plan)] == ["dogs[1]"]

    def test_dog_not_in_document_is_not_deleted(self):
        current = _empty()
        current["dogs"] = {"d1": {"name": "Rex"}}
        plan = ie.plan_import({"dogs": [{"id": "d2", "name": "Max"}]}, current)
        assert plan.ok
        assert list(plan.dogs) == ["d2"]


class TestEvents:
    def _current(self):
        current = _empty()
        current["dogs"] = {"d1": {"name": "Rex"}}
        current["events"] = {
            "e1": {"id": "e1", "dog_id": "d1", "event_type": "walk",
                   "timestamp": "2026-01-01T10:00:00+00:00", "note": ""},
        }
        return current

    def test_unknown_dog_is_an_error_with_a_path(self):
        doc = {"events": [
            {"id": "ok", "dog_id": "d1", "event_type": "walk", "timestamp": "2026-01-01T10:00:00+00:00"},
            {"id": "bad", "dog_id": "ghost", "event_type": "walk", "timestamp": "2026-01-01T10:00:00+00:00"},
        ]}
        plan = ie.plan_import(doc, self._current())
        assert not plan.ok
        assert [p["path"] for p in _errors(plan)] == ["events[1].dog_id"]

    def test_unknown_dog_in_a_schedule_is_an_error(self):
        doc = {"care_schedules": [{"dog_id": "ghost", "event_type": "walk"}]}
        plan = ie.plan_import(doc, self._current())
        assert [p["path"] for p in _errors(plan)] == ["care_schedules[0].dog_id"]

    def test_dedupe_by_id(self):
        doc = {"events": [
            {"id": "e1", "dog_id": "d1", "event_type": "walk",
             "timestamp": "2026-01-01T10:00:00+00:00", "note": ""},
            {"id": "e2", "dog_id": "d1", "event_type": "pee",
             "timestamp": "2026-01-02T10:00:00+00:00"},
        ]}
        plan = ie.plan_import(doc, self._current())
        assert plan.ok
        assert [e["id"] for e in plan.events] == ["e2"]
        assert plan.counts["events"] == {"created": 1, "updated": 0, "unchanged": 1}

    def test_changed_event_is_an_update(self):
        doc = {"events": [{"id": "e1", "dog_id": "d1", "event_type": "walk",
                           "timestamp": "2026-01-01T10:00:00+00:00", "note": "long"}]}
        plan = ie.plan_import(doc, self._current())
        assert plan.counts["events"] == {"created": 0, "updated": 1, "unchanged": 0}
        assert plan.events[0]["note"] == "long"

    def test_duplicate_id_in_document_is_an_error(self):
        event = {"id": "x", "dog_id": "d1", "event_type": "walk",
                 "timestamp": "2026-01-01T10:00:00+00:00"}
        plan = ie.plan_import({"events": [event, dict(event)]}, self._current())
        assert [p["path"] for p in _errors(plan)] == ["events[1].id"]

    def test_event_without_id_gets_one(self):
        doc = {"events": [{"dog_id": "d1", "event_type": "walk",
                           "timestamp": "2026-01-03T10:00:00+00:00"}]}
        plan = ie.plan_import(doc, self._current(), new_id=_ids())
        assert plan.events == [{"id": "new-1", "dog_id": "d1", "event_type": "walk",
                                "timestamp": "2026-01-03T10:00:00+00:00", "note": ""}]

    @pytest.mark.parametrize("timestamp", ["2026-01-01T10:00:00", "yesterday", "", None, 5])
    def test_timestamp_must_be_aware_iso(self, timestamp):
        doc = {"events": [{"id": "x", "dog_id": "d1", "event_type": "walk", "timestamp": timestamp}]}
        plan = ie.plan_import(doc, self._current())
        assert [p["path"] for p in _errors(plan)] == ["events[0].timestamp"]

    def test_utc_z_suffix_is_accepted(self):
        doc = {"events": [{"id": "x", "dog_id": "d1", "event_type": "walk",
                           "timestamp": "2026-01-01T10:00:00.000Z"}]}
        assert ie.plan_import(doc, self._current()).ok

    def test_event_type_from_the_document_overrides_is_known(self):
        doc = {
            "event_types": {"zoomies": {"name": "Zoomies", "icon": "mdi:run", "color": "#123456"}},
            "events": [{"id": "x", "dog_id": "d1", "event_type": "zoomies",
                        "timestamp": "2026-01-01T10:00:00+00:00"}],
        }
        plan = ie.plan_import(doc, self._current())
        assert plan.ok and plan.problems == []

    def test_unknown_event_type_is_a_warning_and_the_event_is_kept(self):
        doc = {"events": [{"id": "x", "dog_id": "d1", "event_type": "nope",
                           "timestamp": "2026-01-01T10:00:00+00:00"}]}
        plan = ie.plan_import(doc, self._current())
        assert plan.ok
        assert [p["level"] for p in plan.problems] == ["warning"]
        assert plan.problems[0]["path"] == "events[0].event_type"
        assert len(plan.events) == 1

    def test_value_must_be_a_number(self):
        doc = {"events": [{"id": "x", "dog_id": "d1", "event_type": "weight",
                           "timestamp": "2026-01-01T10:00:00+00:00", "value": "heavy"}]}
        plan = ie.plan_import(doc, self._current())
        assert [p["path"] for p in _errors(plan)] == ["events[0].value"]


class TestCareSchedules:
    def _current(self):
        current = _empty()
        current["dogs"] = {"d1": {"name": "Rex"}}
        current["care_schedules"] = {
            "local-s": {"dog_id": "d1", "event_type": "medicine", "recurrence_type": "floating",
                        "interval": 2, "unit": "weeks", "task_id": "hk-1"},
        }
        return current

    def test_match_by_dog_and_event_type(self):
        doc = {"care_schedules": [{"id": "far-s", "dog_id": "d1", "event_type": "medicine",
                                   "recurrence_type": "floating", "interval": 2, "unit": "weeks"}]}
        plan = ie.plan_import(doc, self._current())
        assert plan.ok
        assert plan.counts["care_schedules"] == {"created": 0, "updated": 0, "unchanged": 1}
        assert not plan.care_schedules

    def test_cadence_change_replaces_the_task(self):
        doc = {"care_schedules": [{"id": "local-s", "dog_id": "d1", "event_type": "medicine",
                                   "recurrence_type": "floating", "interval": 3, "unit": "weeks"}]}
        plan = ie.plan_import(doc, self._current())
        assert plan.ok
        assert plan.care_schedules["local-s"]["interval"] == 3
        assert "task_id" not in plan.care_schedules["local-s"]
        assert plan.replaced_tasks == {"local-s"}

    def test_task_id_in_document_is_ignored(self):
        doc = {"care_schedules": [{"id": "local-s", "dog_id": "d1", "event_type": "medicine",
                                   "recurrence_type": "floating", "interval": 2, "unit": "weeks",
                                   "task_id": "other-install"}]}
        plan = ie.plan_import(doc, self._current())
        assert not plan.care_schedules

    def test_tombstoned_event_type_is_an_error(self):
        doc = {"event_types": {"walk": None},
               "care_schedules": [{"dog_id": "d1", "event_type": "walk"}]}
        plan = ie.plan_import(doc, self._current())
        assert [p["path"] for p in _errors(plan)] == ["care_schedules[0].event_type"]

    def test_fixed_schedule_needs_an_anchor(self):
        doc = {"care_schedules": [{"dog_id": "d1", "event_type": "walk",
                                   "recurrence_type": "fixed", "freq": "WEEKLY"}]}
        plan = ie.plan_import(doc, self._current())
        assert [p["path"] for p in _errors(plan)] == ["care_schedules[0].anchor"]

    def test_bad_unit_is_an_error(self):
        doc = {"care_schedules": [{"dog_id": "d1", "event_type": "walk", "unit": "years"}]}
        plan = ie.plan_import(doc, self._current())
        assert [p["path"] for p in _errors(plan)] == ["care_schedules[0].unit"]


class TestSettings:
    def test_event_type_validation(self):
        doc = {"event_types": {"Bad Key": {"name": "x", "icon": "mdi:x", "color": "#000000"},
                               "ok": {"name": "", "icon": "walk", "color": "red"}}}
        plan = ie.plan_import(doc, _empty())
        assert [p["path"] for p in _errors(plan)] == [
            "event_types.Bad Key", "event_types.ok.name", "event_types.ok.icon",
            "event_types.ok.color",
        ]

    def test_button_metric_validation(self):
        plan = ie.plan_import({"button_metrics": {"walk": "forever"}}, _empty())
        assert [p["path"] for p in _errors(plan)] == ["button_metrics.walk"]

    def test_overrides_are_merged_not_replaced(self):
        current = _empty()
        current["event_types"] = {"mine": {"name": "Mine", "icon": "mdi:star", "color": "#000000"}}
        doc = {"event_types": {"theirs": {"name": "Theirs", "icon": "mdi:star", "color": "#FFFFFF"}}}
        plan = ie.plan_import(doc, current)
        assert plan.event_types == {"theirs": doc["event_types"]["theirs"]}
