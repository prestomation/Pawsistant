"""Home Assistant tests for pawsistant.export_data and pawsistant.import_data.

These use real Home Assistant (the ``real_ha`` marker), so they run in the first
pytest process, before the mock-based tier changes ``sys.modules``. The Home Keeper
side (reconcile and the task it makes) is in ``test_cross_integration.py``.
"""

from __future__ import annotations

import copy
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.real_ha

from homeassistant.core import Context  # noqa: E402
from homeassistant.exceptions import ServiceValidationError, Unauthorized  # noqa: E402
from homeassistant.helpers import entity_registry as er  # noqa: E402
from pytest_homeassistant_custom_component.common import (  # noqa: E402
    MockConfigEntry,
    async_capture_events,
)

from custom_components.pawsistant.const import DOMAIN  # noqa: E402


async def _setup(hass) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data={"initial_dog": {"name": "Buddy"}})
    entry.add_to_hass(hass)
    # The card needs the compiled frontend, which the test env does not have.
    hass.config.components.add("http")
    hass.config.components.add("frontend")
    with patch(
        "custom_components.pawsistant._ensure_frontend_registered", new=AsyncMock()
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def _export(hass, context=None) -> dict:
    return await hass.services.async_call(
        DOMAIN, "export_data", {}, blocking=True, return_response=True, context=context
    )


async def _import(hass, document, *, dry_run=False, context=None) -> dict:
    with patch(
        "custom_components.pawsistant._ensure_frontend_registered", new=AsyncMock()
    ):
        result = await hass.services.async_call(
            DOMAIN,
            "import_data",
            {"document": document, "dry_run": dry_run},
            blocking=True,
            return_response=True,
            context=context,
        )
        await hass.async_block_till_done()
    return result


def _new_dog_document(data: dict) -> dict:
    """Add a dog with 1 event to an exported document."""
    doc = copy.deepcopy(data)
    doc["dogs"].append({"id": "dog-luna", "name": "Luna", "breed": "Beagle"})
    doc["events"].append(
        {
            "id": "ev-luna-1",
            "dog_id": "dog-luna",
            "event_type": "walk",
            "timestamp": "2026-01-05T08:00:00+00:00",
            "note": "imported",
        }
    )
    doc["shown_types"]["dog-luna"] = ["walk", "food"]
    return doc


@pytest.mark.asyncio
async def test_non_admin_cannot_export(
    hass, enable_custom_integrations, hass_read_only_user
):
    await _setup(hass)
    with pytest.raises(Unauthorized):
        await _export(hass, Context(user_id=hass_read_only_user.id))


@pytest.mark.asyncio
async def test_non_admin_cannot_import(
    hass, enable_custom_integrations, hass_admin_user, hass_read_only_user
):
    entry = await _setup(hass)
    data = (await _export(hass, Context(user_id=hass_admin_user.id)))["data"]
    with pytest.raises(Unauthorized):
        await _import(
            hass, _new_dog_document(data), context=Context(user_id=hass_read_only_user.id)
        )
    store = entry.runtime_data.store
    assert [d["name"] for d in store.get_dogs().values()] == ["Buddy"]


@pytest.mark.asyncio
async def test_admin_export_shape(hass, enable_custom_integrations, hass_admin_user):
    entry = await _setup(hass)
    store = entry.runtime_data.store
    dog_id = next(iter(store.get_dogs()))
    await hass.services.async_call(
        DOMAIN,
        "log_event",
        {"dog": "Buddy", "event_type": "weight", "value": 31.0,
         "timestamp": "2026-01-02T09:00:00+00:00"},
        blocking=True,
    )
    await store.set_shown_types("Buddy", ["walk", "weight"])

    response = await _export(hass, Context(user_id=hass_admin_user.id))

    assert response["format"] == 1
    assert response["skipped"] == {}
    assert isinstance(response["version"], str) and response["version"]
    data = response["data"]
    assert data["dogs"] == [
        {"id": dog_id, "name": "Buddy", "breed": "", "birth_date": "", "species": "Dog"}
    ]
    assert data["shown_types"] == {dog_id: ["walk", "weight"]}
    assert [(e["event_type"], e["value"]) for e in data["events"]] == [("weight", 31.0)]


@pytest.mark.asyncio
async def test_call_without_a_user_is_trusted(hass, enable_custom_integrations):
    """An automation or another integration calls with no user, like Home Keeper."""
    await _setup(hass)
    response = await _export(hass)
    assert response["format"] == 1


@pytest.mark.asyncio
async def test_dry_run_writes_nothing(hass, enable_custom_integrations, hass_admin_user):
    entry = await _setup(hass)
    admin = Context(user_id=hass_admin_user.id)
    data = (await _export(hass, admin))["data"]
    fired = async_capture_events(hass, f"{DOMAIN}_data_imported")

    report = await _import(hass, _new_dog_document(data), dry_run=True, context=admin)

    assert report["ok"] is True and report["dry_run"] is True
    assert report["counts"]["dogs"]["created"] == 1
    assert report["counts"]["events"]["created"] == 1
    store = entry.runtime_data.store
    assert [d["name"] for d in store.get_dogs().values()] == ["Buddy"]
    assert await store.get_event("ev-luna-1") is None
    assert fired == []


@pytest.mark.asyncio
async def test_import_creates_the_dog_its_entities_and_events(
    hass, enable_custom_integrations, hass_admin_user
):
    entry = await _setup(hass)
    admin = Context(user_id=hass_admin_user.id)
    data = (await _export(hass, admin))["data"]
    fired = async_capture_events(hass, f"{DOMAIN}_data_imported")

    report = await _import(hass, _new_dog_document(data), context=admin)

    assert report["ok"] is True and report["dry_run"] is False
    # The import reloads the entry, so read the new store.
    store = entry.runtime_data.store
    found = store.get_dog_by_name("Luna")
    assert found is not None and found[0] == "dog-luna"
    assert found[1]["breed"] == "Beagle"
    event = await store.get_event("ev-luna-1")
    assert event is not None and event["note"] == "imported"
    assert 2026 in store.known_years()
    assert store.get_shown_types("Luna") == ["walk", "food"]
    # The new dog has sensor entities, as after add_dog.
    unique_ids = {
        e.unique_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    }
    assert any(uid.startswith("pawsistant_dog-luna_") for uid in unique_ids)
    assert len(fired) == 1
    assert fired[0].data["counts"]["dogs"]["created"] == 1

    # The same document again changes nothing and makes no duplicate.
    again = await _import(hass, _new_dog_document(data), context=admin)
    assert again["records"] == []
    assert again["counts"]["events"]["created"] == 0
    assert len(await entry.runtime_data.store.get_all_events("dog-luna")) == 1


@pytest.mark.asyncio
async def test_import_with_an_error_writes_nothing(
    hass, enable_custom_integrations, hass_admin_user
):
    entry = await _setup(hass)
    admin = Context(user_id=hass_admin_user.id)
    data = (await _export(hass, admin))["data"]
    doc = _new_dog_document(data)
    doc["events"].append(
        {"id": "bad", "dog_id": "ghost", "event_type": "walk",
         "timestamp": "2026-01-05T08:00:00+00:00"}
    )

    report = await _import(hass, doc, context=admin)

    assert report["ok"] is False
    assert [p["path"] for p in report["problems"] if p["level"] == "error"] == [
        f"events[{len(doc['events']) - 1}].dog_id"
    ]
    assert entry.runtime_data.store.get_dog_by_name("Luna") is None


@pytest.mark.asyncio
async def test_higher_format_is_refused(hass, enable_custom_integrations):
    entry = await _setup(hass)
    data = (await _export(hass))["data"]
    doc = _new_dog_document(data)
    doc["format"] = 99
    report = await _import(hass, doc)
    assert report["ok"] is False
    assert report["problems"][0]["path"] == "format"
    assert entry.runtime_data.store.get_dog_by_name("Luna") is None


@pytest.mark.asyncio
async def test_files_dir_outside_the_home_keeper_folder_is_refused(
    hass, enable_custom_integrations
):
    await _setup(hass)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "export_data",
            {"files_dir": hass.config.path(".storage", "home_keeper_import_export", "..", "x")},
            blocking=True,
            return_response=True,
        )
    ok_dir = hass.config.path(".storage", "home_keeper_import_export", "bundle-1")
    response = await hass.services.async_call(
        DOMAIN, "export_data", {"files_dir": ok_dir}, blocking=True, return_response=True
    )
    assert response["format"] == 1
