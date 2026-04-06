"""Unit tests for PawsistantOptionsFlow multi-step flow.

Tests the add/remove/validation paths with mocked store and coordinator.
No live HA instance required — all HA internals are stubbed.
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
# HA stubs — injected before importing config_flow
# ---------------------------------------------------------------------------


class CoreState(str, Enum):
    not_running = "NOT_RUNNING"
    running = "RUNNING"


def _inject_stubs() -> None:
    """Inject lightweight HA stubs so config_flow can be imported standalone.

    We load config_flow.py directly via importlib so __init__.py is never
    executed — that file has heavy HA deps (StaticPathConfig etc.) that we
    don't need here.

    IMPORTANT: we deliberately do NOT replace sys.modules["homeassistant"].
    Python's import system resolves sub-module imports (e.g.
    ``from homeassistant.config_entries import ...``) by looking up the
    dotted key directly in sys.modules — it does NOT traverse the parent
    module's attributes.  This means we can safely stub out only the
    sub-modules that config_flow.py actually imports from, leaving the real
    homeassistant root module (and homeassistant.util etc.) untouched.

    Preserving the real root module is critical: other test files
    (e.g. test_sensor_utils.py) monkeypatch ``homeassistant.util.dt.*``
    which relies on the real module object being in sys.modules.
    """

    # homeassistant root — inject a minimal placeholder only if real HA isn't
    # installed.  We intentionally do NOT replace an existing real module.
    if "homeassistant" not in sys.modules:
        ha_mod = types.ModuleType("homeassistant")
        sys.modules["homeassistant"] = ha_mod

    # homeassistant.core — stub only if real HA hasn't already loaded it.
    # Replacing it could break autouse fixtures that monkeypatch HA internals.
    if "homeassistant.core" not in sys.modules:
        core_mod = types.ModuleType("homeassistant.core")
        core_mod.CoreState = CoreState
        core_mod.HomeAssistant = object
        core_mod.ServiceCall = object
        core_mod.SupportsResponse = MagicMock()
        core_mod.callback = lambda f: f
        sys.modules["homeassistant.core"] = core_mod

    # homeassistant.const — same guard
    if "homeassistant.const" not in sys.modules:
        const_mod = types.ModuleType("homeassistant.const")
        const_mod.EVENT_HOMEASSISTANT_STARTED = "homeassistant_started"
        sys.modules["homeassistant.const"] = const_mod

    # homeassistant.config_entries — always stub.
    # The option-flow tests rely on the stub's OptionsFlow.async_show_form
    # returning a plain dict.  The real OptionsFlow requires a fully
    # initialised hass context that we don't set up here.
    # config_entries is only reached via sys.modules direct lookup — never
    # traversed through the homeassistant root attribute — so replacing it
    # is safe for all other autouse fixtures.
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
        """Minimal OptionsFlow stub with config_entry + hass attributes."""

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

    # homeassistant.helpers / homeassistant.helpers.config_validation
    # Guard: skip if real HA loaded these (they may be traversed by autouse
    # fixtures via attribute paths on the real homeassistant module).
    if "homeassistant.helpers" not in sys.modules:
        helpers_mod = types.ModuleType("homeassistant.helpers")
        sys.modules["homeassistant.helpers"] = helpers_mod
    if "homeassistant.helpers.config_validation" not in sys.modules:
        cv_mod = types.ModuleType("homeassistant.helpers.config_validation")
        cv_mod.string = str
        sys.modules["homeassistant.helpers.config_validation"] = cv_mod

    # re module (needed by config_flow.py)
    import re
    sys.modules["re"] = re

    # voluptuous — always stub.  config_flow.py uses vol.Required/Optional with
    # default= kwargs and vol.Schema/In.  The stub provides minimal behaviour
    # the option-flow tests rely on.  No other test in the suite imports
    # voluptuous directly, so always replacing it here is safe.
    vol_mod = types.ModuleType("voluptuous")
    vol_mod.Schema = lambda s, **kw: s
    vol_mod.Required = lambda k, **kw: k
    vol_mod.Optional = lambda k, **kw: k
    vol_mod.In = lambda v: v
    vol_mod.All = lambda *a: a[0]
    vol_mod.Range = lambda **kw: None
    vol_mod.Coerce = lambda t: t
    sys.modules["voluptuous"] = vol_mod

    # custom_components.pawsistant.const — always stub (only config_flow uses it)
    _const = types.ModuleType("custom_components.pawsistant.const")
    _const.DOMAIN = "pawsistant"
    _const.CONF_SPECIES = "species"
    _const.DEFAULT_SPECIES = "Dog"
    _const.CONF_EVENT_TYPES = "event_types"
    _const.CONF_BUTTON_METRICS = "button_metrics"
    _const.DEFAULT_EVENT_TYPES = {
        "food":     {"name": "Food",     "icon": "mdi:bowl",           "color": "#4CAF50"},
        "treat":    {"name": "Treat",    "icon": "mdi:cookie",         "color": "#FF9800"},
        "water":    {"name": "Water",   "icon": "mdi:cup-water",       "color": "#2196F3"},
        "walk":     {"name": "Walk",    "icon": "mdi:walk",            "color": "#8BC34A"},
        "pee":      {"name": "Pee",     "icon": "mdi:water",           "color": "#FFEB3B"},
        "poop":     {"name": "Poop",    "icon": "mdi:emoticon-poop",   "color": "#795548"},
        "medicine": {"name": "Medicine","icon": "mdi:pill",             "color": "#F44336"},
        "weight":   {"name": "Weight",  "icon": "mdi:scale-bathroom",  "color": "#9C27B0"},
        "vaccine":  {"name": "Vaccine", "icon": "mdi:needle",          "color": "#E91E63"},
        "sleep":    {"name": "Sleep",   "icon": "mdi:sleep",           "color": "#3F51B5"},
        "grooming": {"name": "Grooming","icon": "mdi:content-cut",     "color": "#00BCD4"},
        "training": {"name": "Training","icon": "mdi:hand-pointing-up", "color": "#FF5722"},
        "teeth":    {"name": "Teeth",   "icon": "mdi:toothbrush",      "color": "#009688"},
        "sick":     {"name": "Sick",    "icon": "mdi:emoticon-sick",   "color": "#F44336"},
    }
    _const.DEFAULT_BUTTON_METRICS = {
        "medicine": "days_since",
        "weight":   "last_value",
        "vaccine":  "days_since",
    }
    sys.modules["custom_components.pawsistant.const"] = _const

    # custom_components.pawsistant — always stub to prevent __init__.py from
    # being executed when config_flow.py is loaded via importlib.
    # Replacing an already-loaded real package is safe here because other tests
    # that imported from the real package hold direct object references (not
    # sys.modules lookups) to their imported names.  The monkeypatch targets in
    # test_sensor_utils.py traverse sensor.dt_util (a direct reference to the
    # real homeassistant.util.dt module), so those patches still work correctly.
    _pkg = types.ModuleType("custom_components.pawsistant")
    _pkg.__path__ = []
    _pkg.__package__ = "custom_components.pawsistant"
    sys.modules["custom_components.pawsistant"] = _pkg

    _cc = types.ModuleType("custom_components")
    _cc.pawsistant = _pkg
    sys.modules["custom_components"] = _cc


_inject_stubs()


def _load_config_flow():
    """Load config_flow.py directly from disk, bypassing __init__.py.

    If it's already in sys.modules (e.g. loaded by the real HA test harness),
    return the cached module rather than re-loading it.
    """
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
PawsistantOptionsFlow = _cf_mod.PawsistantOptionsFlow
ACTION_ADD_DOG = _cf_mod.ACTION_ADD_DOG
ACTION_REMOVE_DOG = _cf_mod.ACTION_REMOVE_DOG
ACTION_DONE = _cf_mod.ACTION_DONE


# ---------------------------------------------------------------------------
# Test fixtures / helpers
# ---------------------------------------------------------------------------

SAMPLE_DOGS = {
    "dog-1": {"name": "Buddy", "breed": "Labrador", "birth_date": "2020-01-15"},
    "dog-2": {"name": "Max", "breed": "", "birth_date": ""},
}


def _make_flow(dogs: dict | None = None):
    """Create a PawsistantOptionsFlow with a mocked config_entry and hass."""
    flow = PawsistantOptionsFlow()

    dogs_data = dogs if dogs is not None else {}

    # Mock store
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

    # Mock coordinator
    coord = MagicMock()
    coord.store = store
    coord.async_refresh = AsyncMock()

    # Mock config_entry
    config_entry = MagicMock()
    config_entry.runtime_data = coord
    config_entry.entry_id = "test-entry-id"
    flow.config_entry = config_entry

    # Mock hass
    hass = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_reload = AsyncMock()
    hass.async_create_task = MagicMock()
    flow.hass = hass

    return flow, store, coord, hass


# ---------------------------------------------------------------------------
# Tests: async_step_init
# ---------------------------------------------------------------------------


class TestInitStep:
    @pytest.mark.asyncio
    async def test_shows_form_with_dogs(self):
        flow, store, coord, hass = _make_flow(SAMPLE_DOGS)
        result = await flow.async_step_init()
        assert result["type"] == "form"
        assert result["step_id"] == "init"
        assert "Buddy" in result["description_placeholders"]["current_dogs"]
        assert "Max" in result["description_placeholders"]["current_dogs"]

    @pytest.mark.asyncio
    async def test_shows_dog_details_in_summary(self):
        flow, store, coord, hass = _make_flow(SAMPLE_DOGS)
        result = await flow.async_step_init()
        placeholders = result["description_placeholders"]["current_dogs"]
        assert "Labrador" in placeholders
        assert "2020-01-15" in placeholders

    @pytest.mark.asyncio
    async def test_redirects_to_add_dog_when_no_dogs(self):
        flow, store, coord, hass = _make_flow({})
        result = await flow.async_step_init()
        # Should show the add_dog form (no dogs → skip selector)
        assert result["type"] == "form"
        assert result["step_id"] == "add_dog"

    @pytest.mark.asyncio
    async def test_routes_to_add_dog_on_action(self):
        flow, store, coord, hass = _make_flow(SAMPLE_DOGS)
        result = await flow.async_step_init(user_input={"action": ACTION_ADD_DOG})
        assert result["type"] == "form"
        assert result["step_id"] == "add_dog"

    @pytest.mark.asyncio
    async def test_routes_to_remove_dog_on_action(self):
        flow, store, coord, hass = _make_flow(SAMPLE_DOGS)
        result = await flow.async_step_init(user_input={"action": ACTION_REMOVE_DOG})
        assert result["type"] == "form"
        assert result["step_id"] == "remove_dog"

    @pytest.mark.asyncio
    async def test_done_creates_entry(self):
        flow, store, coord, hass = _make_flow(SAMPLE_DOGS)
        result = await flow.async_step_init(user_input={"action": ACTION_DONE})
        assert result["type"] == "create_entry"


# ---------------------------------------------------------------------------
# Tests: async_step_add_dog
# ---------------------------------------------------------------------------


class TestAddDogStep:
    @pytest.mark.asyncio
    async def test_shows_add_dog_form(self):
        flow, store, coord, hass = _make_flow(SAMPLE_DOGS)
        result = await flow.async_step_add_dog()
        assert result["type"] == "form"
        assert result["step_id"] == "add_dog"

    @pytest.mark.asyncio
    async def test_error_on_empty_name(self):
        flow, store, coord, hass = _make_flow(SAMPLE_DOGS)
        result = await flow.async_step_add_dog(
            user_input={"dog_name": "", "breed": "", "birth_date": ""}
        )
        assert result["type"] == "form"
        assert result["errors"]["dog_name"] == "name_required"
        store.add_dog.assert_not_called()

    @pytest.mark.asyncio
    async def test_error_on_whitespace_name(self):
        flow, store, coord, hass = _make_flow(SAMPLE_DOGS)
        result = await flow.async_step_add_dog(
            user_input={"dog_name": "   ", "breed": "", "birth_date": ""}
        )
        assert result["type"] == "form"
        assert result["errors"]["dog_name"] == "name_required"

    @pytest.mark.asyncio
    async def test_error_on_duplicate_name_case_insensitive(self):
        flow, store, coord, hass = _make_flow(SAMPLE_DOGS)
        result = await flow.async_step_add_dog(
            user_input={"dog_name": "buddy", "breed": "", "birth_date": ""}
        )
        assert result["type"] == "form"
        assert result["errors"]["dog_name"] == "name_already_exists"
        store.add_dog.assert_not_called()

    @pytest.mark.asyncio
    async def test_error_on_exact_duplicate_name(self):
        flow, store, coord, hass = _make_flow(SAMPLE_DOGS)
        result = await flow.async_step_add_dog(
            user_input={"dog_name": "Buddy", "breed": "", "birth_date": ""}
        )
        assert result["type"] == "form"
        assert result["errors"]["dog_name"] == "name_already_exists"

    @pytest.mark.asyncio
    async def test_successful_add_creates_entry(self):
        flow, store, coord, hass = _make_flow(SAMPLE_DOGS)
        result = await flow.async_step_add_dog(
            user_input={
                "dog_name": "Bella",
                "breed": "Poodle",
                "birth_date": "2022-06-01",
            }
        )
        assert result["type"] == "create_entry"
        store.add_dog.assert_awaited_once_with(
            name="Bella", breed="Poodle", birth_date="2022-06-01", species="Dog"
        )

    @pytest.mark.asyncio
    async def test_successful_add_triggers_reload(self):
        flow, store, coord, hass = _make_flow(SAMPLE_DOGS)
        await flow.async_step_add_dog(
            user_input={"dog_name": "Bella", "breed": "", "birth_date": ""}
        )
        # Should schedule a reload task
        hass.async_create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_value_error_shows_form(self):
        flow, store, coord, hass = _make_flow(SAMPLE_DOGS)
        store.add_dog.side_effect = ValueError("Dog already exists")
        result = await flow.async_step_add_dog(
            user_input={"dog_name": "NewDog", "breed": "", "birth_date": ""}
        )
        assert result["type"] == "form"
        assert result["errors"]["dog_name"] == "name_already_exists"

    @pytest.mark.asyncio
    async def test_add_with_optional_fields_omitted(self):
        flow, store, coord, hass = _make_flow(SAMPLE_DOGS)
        result = await flow.async_step_add_dog(
            user_input={"dog_name": "Charlie", "breed": "", "birth_date": ""}
        )
        assert result["type"] == "create_entry"
        store.add_dog.assert_awaited_once_with(
            name="Charlie", breed="", birth_date="", species="Dog"
        )


# ---------------------------------------------------------------------------
# Tests: async_step_remove_dog
# ---------------------------------------------------------------------------


class TestRemoveDogStep:
    @pytest.mark.asyncio
    async def test_shows_remove_dog_form(self):
        flow, store, coord, hass = _make_flow(SAMPLE_DOGS)
        result = await flow.async_step_remove_dog()
        assert result["type"] == "form"
        assert result["step_id"] == "remove_dog"

    @pytest.mark.asyncio
    async def test_redirects_to_add_dog_when_no_dogs(self):
        flow, store, coord, hass = _make_flow({})
        result = await flow.async_step_remove_dog()
        # No dogs → init → add_dog
        assert result["type"] == "form"
        assert result["step_id"] == "add_dog"

    @pytest.mark.asyncio
    async def test_successful_remove_creates_entry(self):
        flow, store, coord, hass = _make_flow(SAMPLE_DOGS)
        result = await flow.async_step_remove_dog(
            user_input={"dog_name": "Buddy"}
        )
        assert result["type"] == "create_entry"
        store.remove_dog.assert_awaited_once_with("dog-1")

    @pytest.mark.asyncio
    async def test_successful_remove_triggers_coordinator_refresh(self):
        flow, store, coord, hass = _make_flow(SAMPLE_DOGS)
        await flow.async_step_remove_dog(user_input={"dog_name": "Buddy"})
        coord.async_refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_remove_case_insensitive_lookup(self):
        flow, store, coord, hass = _make_flow(SAMPLE_DOGS)
        result = await flow.async_step_remove_dog(
            user_input={"dog_name": "max"}
        )
        assert result["type"] == "create_entry"
        store.remove_dog.assert_awaited_once_with("dog-2")

    @pytest.mark.asyncio
    async def test_error_when_dog_not_found(self):
        flow, store, coord, hass = _make_flow(SAMPLE_DOGS)
        store.get_dog_by_name.return_value = None
        result = await flow.async_step_remove_dog(
            user_input={"dog_name": "Ghost"}
        )
        assert result["type"] == "form"
        assert result["errors"]["dog_name"] == "dog_not_found"
        store.remove_dog.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_reload_triggered_on_remove(self):
        """Remove should refresh coordinator, not reload the entry."""
        flow, store, coord, hass = _make_flow(SAMPLE_DOGS)
        await flow.async_step_remove_dog(user_input={"dog_name": "Buddy"})
        hass.config_entries.async_reload.assert_not_called()
        coord.async_refresh.assert_awaited_once()


# ---------------------------------------------------------------------------
# Tests: missing/broken runtime_data
# ---------------------------------------------------------------------------


class TestMissingRuntimeData:
    @pytest.mark.asyncio
    async def test_init_handles_missing_runtime_data(self):
        flow, store, coord, hass = _make_flow(SAMPLE_DOGS)
        flow.config_entry.runtime_data = None
        # store returns {}, so no dogs → redirects to add_dog
        result = await flow.async_step_init()
        assert result["type"] == "form"

    @pytest.mark.asyncio
    async def test_add_dog_handles_missing_store(self):
        flow, store, coord, hass = _make_flow(SAMPLE_DOGS)
        flow.config_entry.runtime_data = None
        # With no store available, the flow should show an error rather than
        # silently succeeding without persisting the new dog.
        result = await flow.async_step_add_dog(
            user_input={"dog_name": "NewDog", "breed": "", "birth_date": ""}
        )
        assert result["type"] == "form"
        assert result["errors"].get("dog_name") == "store_unavailable"
