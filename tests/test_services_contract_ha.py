"""Contract tests: ``services.yaml`` must agree with the code.

hassfest checks only the format of ``services.yaml``. It does not check that the
fields agree with the voluptuous schemas, that the selector options are real
keys, or that the service accepts each field that the UI offers. These tests do.
They use real Home Assistant (the ``real_ha`` marker).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
from unittest.mock import AsyncMock, patch

import pytest
import voluptuous as vol
import yaml

pytestmark = pytest.mark.real_ha

from homeassistant.exceptions import ServiceValidationError  # noqa: E402
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

from custom_components.pawsistant.config_flow import VALID_BUTTON_METRICS  # noqa: E402
from custom_components.pawsistant.const import DEFAULT_EVENT_TYPES, DOMAIN  # noqa: E402

FRONTEND = "custom_components.pawsistant._ensure_frontend_registered"
SERVICES_YAML = (
    Path(__file__).parent.parent / "custom_components" / DOMAIN / "services.yaml"
)
SERVICES: dict[str, Any] = yaml.safe_load(SERVICES_YAML.read_text(encoding="utf-8"))

# Valid options for a select selector, by field name.
SELECT_OPTIONS = {
    "event_type": set(DEFAULT_EVENT_TYPES),
    "metric": set(VALID_BUTTON_METRICS),
}

# A valid sample value for each field of each service. A function takes the test
# context (made in ``_setup``) and returns the value. When you add a field to
# services.yaml, add a sample here: test_every_field_has_a_sample makes sure.
SAMPLES: dict[str, dict[str, Any]] = {
    "log_event": {
        "dog": "Buddy",
        "event_type": "walk",
        "note": "sample",
        "value": 1.5,
        "timestamp": "2026-01-05T08:00:00+00:00",
    },
    "delete_event": {"event_id": lambda ctx: ctx["event_id"]},
    "update_event": {
        "event_id": lambda ctx: ctx["event_id"],
        "timestamp": "2026-01-06T08:00:00+00:00",
        "note": "changed",
        "value": 2.0,
    },
    "add_dog": {
        "name": "Rex",
        "breed": "Beagle",
        "birth_date": "2021-02-03",
        "species": "Cat",
    },
    "remove_dog": {"dog": "Buddy"},
    "list_events": {"dog": "Buddy", "event_type": "walk", "days": 30},
    "import_events": {"events": []},
    "export_data": {"files_dir": lambda ctx: ctx["files_dir"]},
    "import_data": {
        "document": lambda ctx: ctx["export"],
        "dry_run": True,
        "files_dir": lambda ctx: ctx["files_dir"],
    },
    "update_event_type": {
        "event_type": "walk",
        "name": "Stroll",
        "icon": "mdi:walk",
        "color": "#123456",
        "metric": "days_since",
    },
    "add_event_type": {
        "event_type": "brush2",
        "name": "Brush 2",
        "icon": "mdi:brush",
        "color": "#336699",
        "metric": "daily_count",
    },
    "delete_event_type": {"event_type": "brush", "delete_events": True},
    "set_shown_types": {"dog": "Buddy", "shown_types": ["walk", "pee"]},
}


# Services that correctly refuse a call with only the required fields: there is
# nothing to change. The call with each optional field must still work.
NEEDS_AN_OPTIONAL_FIELD = {"update_event_type"}


def _fields(service: str) -> dict[str, Any]:
    return SERVICES[service].get("fields") or {}


def _required(service: str) -> set[str]:
    return {name for name, f in _fields(service).items() if f.get("required")}


def _optional(service: str) -> set[str]:
    return set(_fields(service)) - _required(service)


def _cases() -> list[tuple[str, str | None]]:
    """(service, optional field) pairs; None means "required fields only"."""
    cases: list[tuple[str, str | None]] = []
    for service in SERVICES:
        cases.append((service, None))
        cases.extend((service, field) for field in sorted(_optional(service)))
    return cases


@pytest.fixture(autouse=True)
def _no_frontend():
    with patch(FRONTEND, new=AsyncMock()):
        yield


async def _setup(hass) -> dict[str, Any]:
    entry = MockConfigEntry(domain=DOMAIN, data={"initial_dog": {"name": "Buddy"}})
    entry.add_to_hass(hass)
    hass.config.components.add("http")
    hass.config.components.add("frontend")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    store = entry.runtime_data.store
    dog_id = store.get_dog_by_name("Buddy")[0]
    event = await store.add_event(dog_id=dog_id, event_type="walk")
    await hass.services.async_call(
        DOMAIN,
        "add_event_type",
        {"event_type": "brush", "name": "Brush", "icon": "mdi:brush", "color": "#336699"},
        blocking=True,
    )
    export = await hass.services.async_call(
        DOMAIN, "export_data", {}, blocking=True, return_response=True
    )
    return {
        "event_id": event["id"],
        "files_dir": hass.config.path(".storage", "home_keeper_import_export", "t"),
        "export": export,
    }


def _value(sample: Any, ctx: dict[str, Any]) -> Any:
    return sample(ctx) if isinstance(sample, Callable) else sample


def _schema_keys(hass, service: str) -> dict[str, bool]:
    """{field: required} from the schema that the service is registered with."""
    schema = hass.services.async_services()[DOMAIN][service].schema
    assert isinstance(schema, vol.Schema), f"{service} has no voluptuous schema"
    return {str(key.schema): isinstance(key, vol.Required) for key in schema.schema}


@pytest.mark.asyncio
async def test_yaml_fields_match_schema(hass, enable_custom_integrations):
    """Each field in services.yaml is in the schema, and the reverse."""
    await _setup(hass)
    registered = set(hass.services.async_services()[DOMAIN])
    assert registered == set(SERVICES)

    for service in SERVICES:
        schema = _schema_keys(hass, service)
        assert set(_fields(service)) == set(schema), service
        required = {name for name, is_required in schema.items() if is_required}
        assert _required(service) == required, service


def test_select_options_are_known_values():
    """A select option in services.yaml must be a real key or value."""
    for service, spec in SERVICES.items():
        for name, field in (spec.get("fields") or {}).items():
            options = ((field.get("selector") or {}).get("select") or {}).get("options")
            if not options or name not in SELECT_OPTIONS:
                continue
            values = {o["value"] if isinstance(o, dict) else o for o in options}
            unknown = values - SELECT_OPTIONS[name]
            assert not unknown, f"{service}.{name}: unknown options {sorted(unknown)}"


def test_every_field_has_a_sample():
    for service in SERVICES:
        assert set(SAMPLES.get(service, {})) == set(_fields(service)), service


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("service", "optional"), _cases(), ids=lambda v: "required_only" if v is None else v
)
async def test_service_accepts_each_field(
    hass, enable_custom_integrations, service, optional
):
    """Required fields plus one optional field at a time must not fail.

    This is what a user does in the action editor: fill in one field and run it.
    """
    ctx = await _setup(hass)
    fields = _required(service) | ({optional} if optional else set())
    data = {name: _value(SAMPLES[service][name], ctx) for name in fields}
    call = hass.services.async_call(
        DOMAIN,
        service,
        data,
        blocking=True,
        return_response=hass.services.supports_response(DOMAIN, service) != "none",
    )
    if optional is None and service in NEEDS_AN_OPTIONAL_FIELD:
        with pytest.raises(ServiceValidationError):
            await call
        return
    with patch("custom_components.pawsistant.care_link.delete_task", new=AsyncMock()):
        await call
        await hass.async_block_till_done()
