"""Unit tests for PawsistantCardRegistration immediate registration logic.

These tests mock out HA internals so they run without a live HA instance.
The key behaviour under test is the fix introduced for issue #15:
  - Registration always happens immediately regardless of HA state.
  - Static path is registered via async_register_static_paths (with RuntimeError
    guard against double-registration).
  - In storage mode the Lovelace resource is registered immediately.
  - In YAML mode an INFO message is logged instead of trying to register resources.
"""

from __future__ import annotations

import importlib
import pathlib
import re
import sys
import types
from enum import Enum
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Force-inject lightweight HA stubs before importing the component.
# We use direct assignment (not setdefault) so we override any already-loaded
# real HA modules in the test process.
# ---------------------------------------------------------------------------

class CoreState(str, Enum):
    not_running = "NOT_RUNNING"
    starting = "STARTING"
    running = "RUNNING"
    stopping = "STOPPING"


def _inject_stubs() -> None:
    """Replace HA modules with lightweight stubs for unit testing."""

    # homeassistant root
    ha_mod = types.ModuleType("homeassistant")
    sys.modules["homeassistant"] = ha_mod

    # homeassistant.core
    core_mod = types.ModuleType("homeassistant.core")
    core_mod.CoreState = CoreState
    core_mod.HomeAssistant = object
    core_mod.ServiceCall = object
    core_mod.SupportsResponse = MagicMock()
    core_mod.callback = lambda f: f
    sys.modules["homeassistant.core"] = core_mod
    ha_mod.core = core_mod

    # homeassistant.const
    const_mod = types.ModuleType("homeassistant.const")
    const_mod.EVENT_HOMEASSISTANT_STARTED = "homeassistant_started"
    sys.modules["homeassistant.const"] = const_mod
    ha_mod.const = const_mod

    # homeassistant.config_entries
    ce_mod = types.ModuleType("homeassistant.config_entries")
    ce_mod.ConfigEntry = object
    sys.modules["homeassistant.config_entries"] = ce_mod

    # homeassistant.components + sub-modules (network.util patched by pytest plugin)
    comp_mod = types.ModuleType("homeassistant.components")
    ha_mod.components = comp_mod
    sys.modules["homeassistant.components"] = comp_mod

    http_mod = types.ModuleType("homeassistant.components.http")
    http_mod.StaticPathConfig = MagicMock
    comp_mod.http = http_mod
    sys.modules["homeassistant.components.http"] = http_mod

    network_mod = types.ModuleType("homeassistant.components.network")
    comp_mod.network = network_mod
    sys.modules["homeassistant.components.network"] = network_mod

    network_util_mod = types.ModuleType("homeassistant.components.network.util")
    network_util_mod.async_get_source_ip = MagicMock(return_value="10.10.10.10")
    network_mod.util = network_util_mod
    sys.modules["homeassistant.components.network.util"] = network_util_mod

    # homeassistant.components.network.network — also patched by pytest plugin
    network_network_mod = types.ModuleType("homeassistant.components.network.network")
    network_network_mod.async_load_adapters = AsyncMock(return_value=[])
    network_mod.network = network_network_mod
    sys.modules["homeassistant.components.network.network"] = network_network_mod

    # homeassistant.helpers + homeassistant.helpers.config_validation
    helpers_mod = types.ModuleType("homeassistant.helpers")
    cv_mod = types.ModuleType("homeassistant.helpers.config_validation")
    cv_mod.string = str
    sys.modules["homeassistant.helpers"] = helpers_mod
    sys.modules["homeassistant.helpers.config_validation"] = cv_mod
    helpers_mod.config_validation = cv_mod

    # homeassistant.util.logging (needed by pytest-homeassistant-custom-component fixture)
    util_mod = types.ModuleType("homeassistant.util")
    util_logging_mod = types.ModuleType("homeassistant.util.logging")
    util_logging_mod.log_exception = MagicMock()
    sys.modules["homeassistant.util"] = util_mod
    sys.modules["homeassistant.util.logging"] = util_logging_mod
    ha_mod.util = util_mod
    util_mod.logging = util_logging_mod

    # voluptuous
    vol_mod = types.ModuleType("voluptuous")
    vol_mod.Schema = lambda s, **kw: s
    vol_mod.Required = lambda k, **kw: k
    vol_mod.Optional = lambda k, **kw: k
    vol_mod.In = lambda v: v
    vol_mod.All = lambda *a: a[0]
    vol_mod.Range = lambda **kw: None
    vol_mod.Coerce = lambda t: t
    sys.modules["voluptuous"] = vol_mod

    # custom_components sub-modules
    _const = types.ModuleType("custom_components.pawsistant.const")
    _const.DOMAIN = "pawsistant"
    _const.PLATFORMS = []
    _const.URL_BASE = "/pawsistant"
    _const.CARD_VERSION = "test"
    _const.MDI_ICON_RE = re.compile(r"^(mdi|hass):[a-z0-9-]+$")
    _const.HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
    _const.VALID_BUTTON_METRICS = ["daily_count", "days_since", "last_value", "hours_since"]
    _const.MAX_EVENT_TYPE_KEY_LEN = 30
    _const.EVENT_TYPE_KEY_RE = re.compile(r"^[a-z0-9_]+$")
    _const.DEFAULT_EVENT_TYPES = {}
    sys.modules["custom_components.pawsistant.const"] = _const

    _coord = types.ModuleType("custom_components.pawsistant.coordinator")
    _coord.PawsistantCoordinator = MagicMock
    sys.modules["custom_components.pawsistant.coordinator"] = _coord

    _store = types.ModuleType("custom_components.pawsistant.store")
    _store.PawsistantStore = MagicMock
    _store.VALID_EVENT_TYPES = []
    sys.modules["custom_components.pawsistant.store"] = _store

    # Remove any previously loaded version of the module under test so it
    # re-imports cleanly against our stubs.
    for key in list(sys.modules):
        if key in ("custom_components.pawsistant", "custom_components"):
            del sys.modules[key]


_inject_stubs()

# Ensure repo root is on sys.path so custom_components resolves to our source
_repo_root = str(pathlib.Path(__file__).parent.parent)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

# Now import the module under test
import custom_components.pawsistant as _init_mod  # noqa: E402
from custom_components.pawsistant import (  # noqa: E402
    PawsistantCardRegistration,
    _ensure_frontend_registered,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_hass(state: CoreState, resource_mode: str = "storage") -> MagicMock:
    """Return a minimal mock hass object."""
    hass = MagicMock()
    hass.state = state

    hass.http.async_register_static_paths = AsyncMock()

    lovelace = MagicMock()
    lovelace.resource_mode = resource_mode
    # Remove the 'mode' attribute so _resource_mode falls through to resource_mode
    del lovelace.mode

    resources = MagicMock()
    resources.loaded = False
    resources.async_load = AsyncMock()
    resources.async_items = MagicMock(return_value=[])
    resources.async_create_item = AsyncMock()
    lovelace.resources = resources

    hass.data = {"lovelace": lovelace}
    hass.bus.async_listen_once = MagicMock()

    return hass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestImmediateRegistration:
    """Registration always happens immediately regardless of HA state."""

    @pytest.mark.asyncio
    async def test_resource_registered_immediately_when_not_running(self):
        """Lovelace resource is created immediately even when HA is not yet running."""
        hass = _make_hass(CoreState.not_running, resource_mode="storage")

        await _ensure_frontend_registered(hass)

        # Static path registered immediately
        hass.http.async_register_static_paths.assert_called_once()

        # Lovelace resource registered immediately — no listener needed
        lovelace_resources = hass.data["lovelace"].resources
        lovelace_resources.async_create_item.assert_called_once()

        # No deferred listener registered
        hass.bus.async_listen_once.assert_not_called()

    @pytest.mark.asyncio
    async def test_resource_registered_immediately_when_starting(self):
        """Lovelace resource is created immediately even during CoreState.starting."""
        hass = _make_hass(CoreState.starting, resource_mode="storage")

        await _ensure_frontend_registered(hass)

        hass.http.async_register_static_paths.assert_called_once()
        hass.data["lovelace"].resources.async_create_item.assert_called_once()
        hass.bus.async_listen_once.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_listener_when_running(self):
        """async_listen_once must NOT be called when CoreState is running."""
        hass = _make_hass(CoreState.running, resource_mode="storage")

        await _ensure_frontend_registered(hass)

        hass.bus.async_listen_once.assert_not_called()

    @pytest.mark.asyncio
    async def test_resource_registered_immediately_when_running(self):
        """Lovelace resource must be created immediately when HA is running."""
        hass = _make_hass(CoreState.running, resource_mode="storage")

        await _ensure_frontend_registered(hass)

        hass.http.async_register_static_paths.assert_called_once()
        lovelace_resources = hass.data["lovelace"].resources
        lovelace_resources.async_create_item.assert_called_once()


class TestYamlModeLogging:
    """YAML-mode Lovelace must log an INFO message instead of crashing."""

    @pytest.mark.asyncio
    async def test_yaml_mode_logs_info_on_startup(self, caplog):
        """YAML mode during startup should log INFO immediately, not raise."""
        import logging
        hass = _make_hass(CoreState.not_running, resource_mode="yaml")

        with caplog.at_level(logging.INFO, logger="custom_components.pawsistant"):
            await _ensure_frontend_registered(hass)

        assert any(
            "YAML mode detected" in record.message
            for record in caplog.records
        ), f"Expected YAML mode INFO log. Got: {[r.message for r in caplog.records]}"

        # No listener registered — everything is immediate
        hass.bus.async_listen_once.assert_not_called()

    @pytest.mark.asyncio
    async def test_yaml_mode_logs_info_when_running(self, caplog):
        """async_register() in YAML mode should log INFO when HA is already running."""
        import logging
        hass = _make_hass(CoreState.running, resource_mode="yaml")

        with caplog.at_level(logging.INFO, logger="custom_components.pawsistant"):
            await _ensure_frontend_registered(hass)

        assert any(
            "YAML mode detected" in record.message
            for record in caplog.records
        ), f"Expected YAML mode INFO log. Got: {[r.message for r in caplog.records]}"
