"""Unit tests for per-dog analytics settings in PawsistantStore.

The weight-trend window and threshold are configurable per dog, because the
right interval depends on the animal: a pet under treatment is weighed weekly
and wants a short window, while a healthy adult is weighed at vet visits and
wants a long one.

Settings are keyed by ``dog_id`` (not name) so they survive a rename, matching
the convention used for entity unique IDs.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
from typing import Any

import pytest


# ── HA stubs ───────────────────────────────────────────────────────────────────
# store.py imports HomeAssistant / Store / dt_util at module scope.

def _inject_stubs() -> None:
    if "homeassistant" not in sys.modules:
        sys.modules["homeassistant"] = types.ModuleType("homeassistant")

    core_mod = sys.modules.get("homeassistant.core") or types.ModuleType("homeassistant.core")
    if not hasattr(core_mod, "HomeAssistant"):
        core_mod.HomeAssistant = type("HomeAssistant", (), {})
    sys.modules["homeassistant.core"] = core_mod

    if "homeassistant.helpers" not in sys.modules:
        sys.modules["homeassistant.helpers"] = types.ModuleType("homeassistant.helpers")

    storage_mod = types.ModuleType("homeassistant.helpers.storage")

    class _Store:
        """Store double that keeps saved data in memory."""

        def __init__(self, hass: Any, version: int, key: str) -> None:
            self.key = key
            self._data: Any = None

        async def async_load(self) -> Any:
            return self._data

        async def async_save(self, data: Any) -> None:
            self._data = data

    storage_mod.Store = _Store
    sys.modules["homeassistant.helpers.storage"] = storage_mod

    if "homeassistant.util" not in sys.modules:
        sys.modules["homeassistant.util"] = types.ModuleType("homeassistant.util")

    if "homeassistant.util.dt" not in sys.modules:
        from datetime import datetime, timezone

        dt_mod = types.ModuleType("homeassistant.util.dt")
        dt_mod.now = lambda tz=None: datetime.now(tz or timezone.utc)
        dt_mod.utcnow = lambda: datetime.now(timezone.utc)
        dt_mod.DEFAULT_TIME_ZONE = timezone.utc
        sys.modules["homeassistant.util.dt"] = dt_mod


_inject_stubs()

for _key in list(sys.modules):
    if _key == "custom_components.pawsistant" or _key.startswith("custom_components.pawsistant."):
        del sys.modules[_key]

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
_PKG = _REPO_ROOT / "custom_components" / "pawsistant"


def _load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_const_mod = _load_module("custom_components.pawsistant.const", _PKG / "const.py")
_store_mod = _load_module("custom_components.pawsistant.store", _PKG / "store.py")
_analytics_mod = _load_module(
    "custom_components.pawsistant.sensor_analytics", _PKG / "sensor_analytics.py"
)

PawsistantStore = _store_mod.PawsistantStore
DEFAULT_WINDOW = _analytics_mod.WEIGHT_TREND_DEFAULT_WINDOW_DAYS


def test_default_window_constants_agree() -> None:
    """The default window is spelled out in two places; keep them in step.

    sensor_analytics.py is imported standalone by its own tests, so it cannot
    use package-relative imports and cannot share a constant with store.py
    directly. This test is what stops the two copies drifting apart.
    """
    assert _const_mod.DEFAULT_WEIGHT_WINDOW_DAYS == DEFAULT_WINDOW


@pytest.fixture
async def store():
    """A loaded store with two dogs."""
    st = PawsistantStore(object())
    await st.load()
    fido = await st.add_dog("Fido")
    luna = await st.add_dog("Luna")
    return st, fido, luna


class TestAnalyticsSettingsDefaults:
    async def test_unset_dog_returns_defaults(self, store):
        st, fido, _ = store
        settings = st.get_analytics_settings(fido)
        assert settings["weight_window_days"] == DEFAULT_WINDOW
        # No threshold override — the analytics layer derives one from the
        # window, so None here means "use the scaled default".
        assert settings["weight_threshold_pct"] is None

    async def test_unknown_dog_id_returns_defaults(self, store):
        """A stale dog_id must not raise — sensors may outlive a removal."""
        st, _, _ = store
        settings = st.get_analytics_settings("does-not-exist")
        assert settings["weight_window_days"] == DEFAULT_WINDOW


class TestAnalyticsSettingsRoundTrip:
    async def test_set_and_get(self, store):
        st, fido, _ = store
        await st.set_analytics_settings(fido, weight_window_days=14, weight_threshold_pct=2.0)
        settings = st.get_analytics_settings(fido)
        assert settings["weight_window_days"] == 14
        assert settings["weight_threshold_pct"] == 2.0

    async def test_settings_are_per_dog(self, store):
        st, fido, luna = store
        await st.set_analytics_settings(fido, weight_window_days=14)
        assert st.get_analytics_settings(fido)["weight_window_days"] == 14
        assert st.get_analytics_settings(luna)["weight_window_days"] == DEFAULT_WINDOW

    async def test_partial_update_preserves_other_fields(self, store):
        st, fido, _ = store
        await st.set_analytics_settings(fido, weight_window_days=14, weight_threshold_pct=2.0)
        await st.set_analytics_settings(fido, weight_window_days=30)
        settings = st.get_analytics_settings(fido)
        assert settings["weight_window_days"] == 30
        assert settings["weight_threshold_pct"] == 2.0, "threshold should survive"

    async def test_none_window_means_all_history(self, store):
        """Explicitly opting out of windowing must be storable and distinct
        from 'never configured'."""
        st, fido, _ = store
        await st.set_analytics_settings(fido, weight_window_days=None)
        assert st.get_analytics_settings(fido)["weight_window_days"] is None

    async def test_settings_persist_across_reload(self, store):
        st, fido, _ = store
        await st.set_analytics_settings(fido, weight_window_days=14)
        # Reload from the same backing store to prove it reached "disk" rather
        # than only the in-memory dict.
        reloaded = PawsistantStore(object())
        reloaded._meta_store = st._meta_store
        await reloaded.load()
        assert reloaded.get_analytics_settings(fido)["weight_window_days"] == 14


class TestAnalyticsSettingsCleanup:
    async def test_removing_a_dog_drops_its_settings(self, store):
        """Otherwise settings accumulate forever for dogs that no longer exist.

        remove_dog already scrubs events and care schedules; analytics settings
        need the same treatment.
        """
        st, fido, luna = store
        await st.set_analytics_settings(fido, weight_window_days=14)
        await st.set_analytics_settings(luna, weight_window_days=30)

        await st.remove_dog(fido)

        assert st.get_analytics_settings(fido)["weight_window_days"] == DEFAULT_WINDOW, (
            "removed dog's settings should be gone, not merely orphaned"
        )
        assert fido not in st._meta.get("analytics_settings", {})
        # The surviving dog is untouched.
        assert st.get_analytics_settings(luna)["weight_window_days"] == 30

    async def test_removing_a_dog_without_settings_is_safe(self, store):
        st, fido, _ = store
        assert await st.remove_dog(fido) is True


class TestRenameSafety:
    async def test_settings_survive_a_rename(self, store):
        """Settings are keyed on dog_id, so renaming must not lose them."""
        st, fido, _ = store
        await st.set_analytics_settings(fido, weight_window_days=14)
        st._meta["dogs"][fido]["name"] = "Fido Jr"
        await st._save_meta()
        assert st.get_analytics_settings(fido)["weight_window_days"] == 14
