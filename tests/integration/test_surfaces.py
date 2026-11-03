"""Touch every user-facing surface once, so the Home Assistant log can show problems.

The CI log gate (ci/check_ha_log.py) reads the container log after all tests
ran. It can only find a problem in code that ran. These tests call:

- the diagnostics download (REST endpoint)
- the options flow (REST endpoints)
- each service, one time with valid data

They check that each call works. The log gate checks what the calls wrote
to the log.

The tests use their own pet, "Surfacedog", and remove it at the end, so the
other tests do not see it.
"""

import pytest
from conftest import HA_URL

DOG = "Surfacedog"
FLOW_URL = f"{HA_URL}/api/config/config_entries/options/flow"
ENTRY_ID = "pawsistant_test_entry"


def _call(ha, service, data=None, response=False):
    """Call a Pawsistant service over REST. Return the JSON body."""
    url = f"{HA_URL}/api/services/pawsistant/{service}"
    if response:
        url += "?return_response"
    r = ha.post(url, json=data or {}, timeout=30)
    assert r.status_code == 200, f"{service}: HTTP {r.status_code}: {r.text}"
    return r.json()


def test_diagnostics_download(ha):
    """Download diagnostics the way the Home Assistant UI does."""
    r = ha.get(f"{HA_URL}/api/diagnostics/config_entry/{ENTRY_ID}", timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, dict), body
    # Home Assistant wraps the integration data under "data".
    assert "data" in body, f"no 'data' key; body keys: {sorted(body)}"
    data = body["data"]
    for key in ("integration_version", "num_dogs", "card_registration", "storage_files"):
        assert key in data, f"missing diagnostics key {key}; data keys: {sorted(data)}"
    version = data["integration_version"]
    assert isinstance(version, str) and version, f"bad version: {version!r}"


def _start_flow(ha):
    r = ha.post(FLOW_URL, json={"handler": ENTRY_ID}, timeout=15)
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["type"] == "form", result
    assert result["step_id"] == "init", result
    return result["flow_id"]


def _step(ha, flow_id, data, expect_step=None, expect_type="form"):
    r = ha.post(f"{FLOW_URL}/{flow_id}", json=data, timeout=15)
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["type"] == expect_type, result
    if expect_step:
        assert result["step_id"] == expect_step, result
    return result


def test_options_flow_open_and_abort(ha):
    """Open the options menu, then close it without a change."""
    flow_id = _start_flow(ha)
    r = ha.delete(f"{FLOW_URL}/{flow_id}", timeout=15)
    assert r.status_code == 200, r.text


def test_options_flow_done(ha):
    flow_id = _start_flow(ha)
    _step(ha, flow_id, {"action": "done"}, expect_type="create_entry")


@pytest.mark.parametrize(
    ("action", "step"),
    [
        ("add_dog", "add_dog"),
        ("remove_dog", "remove_dog"),
        ("edit_event_types", "manage_event_types"),
    ],
)
def test_options_flow_each_menu_entry_opens(ha, action, step):
    """Each entry of the options menu shows its form. Then the flow is closed."""
    flow_id = _start_flow(ha)
    _step(ha, flow_id, {"action": action}, expect_step=step)
    r = ha.delete(f"{FLOW_URL}/{flow_id}", timeout=15)
    assert r.status_code == 200, r.text


def test_options_flow_edit_event_type_form_opens(ha):
    """Open the edit form of one event type."""
    flow_id = _start_flow(ha)
    _step(ha, flow_id, {"action": "edit_event_types"}, expect_step="manage_event_types")
    _step(ha, flow_id, {"action": "edit_walk"}, expect_step="edit_event_type")
    r = ha.delete(f"{FLOW_URL}/{flow_id}", timeout=15)
    assert r.status_code == 200, r.text


def test_every_service_once(ha):
    """Call each Pawsistant service one time with valid data."""
    try:
        _call(ha, "add_dog", {"name": DOG, "breed": "Beagle", "birth_date": "2021-02-03"})
        logged = _call(
            ha,
            "log_event",
            {"dog": DOG, "event_type": "walk", "note": "surface", "value": 1.5},
            response=True,
        )
        event_id = logged["service_response"]["event_id"]
        _call(ha, "update_event", {"event_id": event_id, "note": "changed", "value": 2.0})
        listed = _call(
            ha, "list_events", {"dog": DOG, "event_type": "walk", "days": 30}, response=True
        )
        assert listed["service_response"]["events"], listed
        _call(ha, "set_shown_types", {"dog": DOG, "shown_types": ["walk", "pee"]})
        _call(
            ha,
            "add_event_type",
            {
                "event_type": "surfacebrush",
                "name": "Surface brush",
                "icon": "mdi:brush",
                "color": "#336699",
                "metric": "daily_count",
            },
        )
        _call(
            ha,
            "update_event_type",
            {"event_type": "surfacebrush", "name": "Surface brush 2", "color": "#123456"},
        )
        exported = _call(ha, "export_data", response=True)["service_response"]
        _call(ha, "import_data", {"document": exported, "dry_run": True}, response=True)
        _call(ha, "import_events", {"events": []})
        _call(ha, "delete_event", {"event_id": event_id})
        _call(ha, "delete_event_type", {"event_type": "surfacebrush", "delete_events": True})
    finally:
        # Best effort: remove the test pet, so other tests do not see it.
        ha.post(
            f"{HA_URL}/api/services/pawsistant/remove_dog", json={"dog": DOG}, timeout=30
        )
