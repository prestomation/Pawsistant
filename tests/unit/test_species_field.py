"""Unit tests for the optional species field in config/options flow.

Tests that:
- species defaults to "Dog" when not provided
- species value is stored in config entry data
- options flow add_dog passes species to store
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
from enum import Enum
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# HA stubs — must be injected before importing config_flow
# ---------------------------------------------------------------------------


class CoreState(str, Enum):
    not_running = "NOT_RUNNING"
    running = "RUNNING"


def _inject_stubs() -> None:
    if "homeassistant" not in sys.modules:
        ha_mod = types.ModuleType("homeassistant")
        sys.modules["homeassistant"] = ha_mod

    if "homeassistant.core" not in sys.modules:
        core_mod = types.ModuleType("homeassistant.core")
        core_mod.CoreState = CoreState
        core_mod.HomeAssistant = object
        core_mod.ServiceCall = object
        core_mod.SupportsResponse = MagicMock()
        core_mod.callback = lambda f: f
        sys.modules["homeassistant.core"] = core_mod

    if "homeassistant.const" not in sys.modules:
        const_mod = types.ModuleType("homeassistant.const")
        const_mod.EVENT_HOMEASSISTANT_STARTED = "homeassistant_started"
        sys.modules["homeassistant.const"] = const_mod

    ce_mod = types.ModuleType("homeassistant.config_entries")

    class ConfigFlowResult(dict):
        pass

    class ConfigFlowMeta(type):
        def __new__(mcs, name, bases, namespace, domain=None, **kw):
            return super().__new__(mcs, name, bases, namespace)

        def __init__(cls, name, bases, namespace, domain=None, **kw):
            super().__init__(name, bases, namespace)

    class ConfigFlow(metaclass=ConfigFlowMeta):
        pass

    class OptionsFlow:
        def __init__(self):
            self.config_entry = None
            self.hass = None

        def async_show_form(self, *, step_id, data_schema=None, errors=None,
                            description_placeholders=None):
            return {
                "type": "form",
                "step_id": step_id,
                "data_schema": data_schema,
                "errors": errors or {},
                "description_placeholders": description_placeholders or {},
            }

        def async_create_entry(self, *, title, data):
            return {"type": "create_entry", "title": title, "data": data}

    ce_mod.ConfigFlow = ConfigFlow
    ce_mod.OptionsFlow = OptionsFlow
    ce_mod.ConfigEntry = object
    ce_mod.ConfigFlowResult = ConfigFlowResult
    sys.modules["homeassistant.config_entries"] = ce_mod

    if "homeassistant.helpers" not in sys.modules:
        helpers_mod = types.ModuleType("homeassistant.helpers")
        sys.modules["homeassistant.helpers"] = helpers_mod
    if "homeassistant.helpers.config_validation" not in sys.modules:
        cv_mod = types.ModuleType("homeassistant.helpers.config_validation")
        cv_mod.string = str
        sys.modules["homeassistant.helpers.config_validation"] = cv_mod

    vol_mod = types.ModuleType("voluptuous")
    vol_mod.Schema = lambda s, **kw: s
    vol_mod.Required = lambda k, **kw: k
    vol_mod.Optional = lambda k, **kw: k
    vol_mod.In = lambda v: v
    vol_mod.All = lambda *a: a[0]
    vol_mod.Range = lambda **kw: None
    vol_mod.Coerce = lambda t: t
    sys.modules["voluptuous"] = vol_mod

    _const = types.ModuleType("custom_components.pawsistant.const")
    _const.DOMAIN = "pawsistant"
    _const.CONF_SPECIES = "species"
    _const.DEFAULT_SPECIES = "Dog"
    sys.modules["custom_components.pawsistant.const"] = _const

    _pkg = types.ModuleType("custom_components.pawsistant")
    _pkg.__path__ = []
    _pkg.__package__ = "custom_components.pawsistant"
    sys.modules["custom_components.pawsistant"] = _pkg

    _cc = types.ModuleType("custom_components")
    _cc.pawsistant = _pkg
    sys.modules["custom_components"] = _cc


_inject_stubs()


def _load_config_flow():
    cached = sys.modules.get("custom_components.pawsistant.config_flow")
    if cached is not None:
        return cached

    _repo_root = pathlib.Path(__file__).parent.parent.parent
    cf_path = _repo_root / "custom_components" / "pawsistant" / "config_flow.py"
    spec = importlib.util.spec_from_file_location(
        "custom_components.pawsistant.config_flow", cf_path
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["custom_components.pawsistant.config_flow"] = mod
    spec.loader.exec_module(mod)
    return mod


_cf_mod = _load_config_flow()
PawsistantConfigFlow = _cf_mod.PawsistantConfigFlow
PawsistantOptionsFlow = _cf_mod.PawsistantOptionsFlow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_DOGS = {
    "dog-1": {"name": "Buddy", "breed": "Labrador", "birth_date": "2020-01-15", "species": "Dog"},
}


def _make_options_flow(dogs: dict | None = None):
    """Create a PawsistantOptionsFlow with a mocked config_entry and hass."""
    flow = PawsistantOptionsFlow()
    dogs_data = dogs if dogs is not None else {}

    store = MagicMock()
    store.get_dogs.return_value = dict(dogs_data)
    store.add_dog = AsyncMock(return_value="new-dog-id")
    store.remove_dog = AsyncMock()
    store.get_dog_by_name = MagicMock(
        side_effect=lambda name: next(
            (
                (dog_id, dog)
                for dog_id, dog in dogs_data.items()
                if dog.get("name", "").lower() == name.lower()
            ),
            None,
        )
    )

    coord = MagicMock()
    coord.store = store
    coord.async_refresh = AsyncMock()

    config_entry = MagicMock()
    config_entry.runtime_data = coord
    config_entry.entry_id = "test-entry-id"
    flow.config_entry = config_entry

    hass = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_reload = AsyncMock()
    hass.async_create_task = MagicMock()
    flow.hass = hass

    return flow, store, coord, hass


def _make_config_flow():
    """Create a PawsistantConfigFlow with minimal mocking."""
    flow = PawsistantConfigFlow()
    flow._async_set_unique_id = MagicMock()
    flow._abort_if_unique_id_configured = MagicMock()

    # Stub the required HA helpers on the flow
    created_entries = []

    def _async_create_entry(**kwargs):
        created_entries.append(kwargs)
        return {"type": "create_entry", **kwargs}

    def _async_set_unique_id(uid):
        pass

    def _abort_if_unique_id_configured():
        pass

    def _async_show_form(**kwargs):
        return {"type": "form", **kwargs}

    flow.async_create_entry = _async_create_entry
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = _abort_if_unique_id_configured
    flow.async_show_form = _async_show_form
    flow._created_entries = created_entries
    return flow, created_entries


# ---------------------------------------------------------------------------
# Tests: species defaults
# ---------------------------------------------------------------------------


class TestSpeciesDefault:
    """Verify species defaults to 'Dog' when not provided."""

    @pytest.mark.asyncio
    async def test_config_flow_species_defaults_to_dog_when_omitted(self):
        """Config flow should use 'Dog' as species when field not provided."""
        flow, created_entries = _make_config_flow()
        # Simulate user providing name but no species field
        result = await flow.async_step_user(
            user_input={"dog_name": "Fido", "breed": "", "birth_date": ""}
        )
        assert result["type"] == "create_entry"
        initial_dog = result["data"]["initial_dog"]
        assert initial_dog["species"] == "Dog"

    @pytest.mark.asyncio
    async def test_config_flow_species_defaults_to_dog_when_empty(self):
        """Config flow should fall back to 'Dog' when species is empty string."""
        flow, created_entries = _make_config_flow()
        result = await flow.async_step_user(
            user_input={"dog_name": "Fido", "breed": "", "birth_date": "", "species": ""}
        )
        assert result["type"] == "create_entry"
        initial_dog = result["data"]["initial_dog"]
        assert initial_dog["species"] == "Dog"

    @pytest.mark.asyncio
    async def test_options_flow_add_dog_species_defaults_to_dog(self):
        """Options flow add_dog should call store.add_dog with species='Dog' when omitted."""
        flow, store, coord, hass = _make_options_flow(SAMPLE_DOGS)
        result = await flow.async_step_add_dog(
            user_input={"dog_name": "Whiskers", "breed": "", "birth_date": ""}
        )
        assert result["type"] == "create_entry"
        store.add_dog.assert_awaited_once()
        call_kwargs = store.add_dog.call_args.kwargs
        assert call_kwargs["species"] == "Dog"


# ---------------------------------------------------------------------------
# Tests: species stored in config entry
# ---------------------------------------------------------------------------


class TestSpeciesStored:
    """Verify species value is stored correctly in config entry data."""

    @pytest.mark.asyncio
    async def test_config_flow_stores_species_value(self):
        """Config flow should store the provided species in config entry data."""
        flow, created_entries = _make_config_flow()
        result = await flow.async_step_user(
            user_input={
                "dog_name": "Mittens",
                "breed": "Tabby",
                "birth_date": "",
                "species": "Cat",
            }
        )
        assert result["type"] == "create_entry"
        initial_dog = result["data"]["initial_dog"]
        assert initial_dog["species"] == "Cat"

    @pytest.mark.asyncio
    async def test_config_flow_stores_custom_species(self):
        """Config flow should store arbitrary species values (e.g. Rabbit)."""
        flow, created_entries = _make_config_flow()
        result = await flow.async_step_user(
            user_input={
                "dog_name": "Thumper",
                "breed": "",
                "birth_date": "",
                "species": "Rabbit",
            }
        )
        assert result["type"] == "create_entry"
        assert result["data"]["initial_dog"]["species"] == "Rabbit"

    @pytest.mark.asyncio
    async def test_options_flow_add_dog_passes_species_to_store(self):
        """Options flow add_dog should pass species to store.add_dog."""
        flow, store, coord, hass = _make_options_flow(SAMPLE_DOGS)
        result = await flow.async_step_add_dog(
            user_input={
                "dog_name": "Luna",
                "breed": "Persian",
                "birth_date": "",
                "species": "Cat",
            }
        )
        assert result["type"] == "create_entry"
        store.add_dog.assert_awaited_once()
        call_kwargs = store.add_dog.call_args.kwargs
        assert call_kwargs["name"] == "Luna"
        assert call_kwargs["species"] == "Cat"

    @pytest.mark.asyncio
    async def test_options_flow_add_dog_empty_species_falls_back_to_dog(self):
        """Options flow should fall back to 'Dog' when species is empty."""
        flow, store, coord, hass = _make_options_flow(SAMPLE_DOGS)
        result = await flow.async_step_add_dog(
            user_input={
                "dog_name": "Fluffy",
                "breed": "",
                "birth_date": "",
                "species": "",
            }
        )
        assert result["type"] == "create_entry"
        call_kwargs = store.add_dog.call_args.kwargs
        assert call_kwargs["species"] == "Dog"
