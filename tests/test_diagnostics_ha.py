"""Home Assistant tests for diagnostics, with a guard against blocking I/O.

File I/O on the event loop thread blocks all of Home Assistant. The
``no_loop_io`` fixture makes each file call fail when it runs on the loop
thread, so a test fails if the code under test does file I/O there instead of
in an executor job. Use it around any code that runs on the event loop.
"""

from __future__ import annotations

import builtins
import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.real_ha

from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

from custom_components.pawsistant.const import DOMAIN  # noqa: E402
from custom_components.pawsistant.diagnostics import (  # noqa: E402
    async_get_config_entry_diagnostics,
)

FRONTEND = "custom_components.pawsistant._ensure_frontend_registered"
PATH_IO = ("stat", "is_file", "is_dir", "exists", "glob", "iterdir", "read_text", "read_bytes", "open")


@pytest.fixture
def no_loop_io():
    """Return a context manager that fails on file I/O on the calling thread."""

    @contextmanager
    def guard() -> Iterator[None]:
        loop_thread = threading.get_ident()

        def wrap(name: str, real):
            def checked(*args, **kwargs):
                if threading.get_ident() == loop_thread:
                    raise AssertionError(f"blocking I/O in the event loop: {name}{args[:2]}")
                return real(*args, **kwargs)

            return checked

        patches = [patch.object(Path, n, wrap(f"Path.{n}", getattr(Path, n))) for n in PATH_IO]
        patches.append(patch.object(builtins, "open", wrap("open", builtins.open)))
        for p in patches:
            p.start()
        try:
            yield
        finally:
            for p in patches:
                p.stop()

    return guard


async def _setup(hass) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data={"initial_dog": {"name": "Buddy"}})
    entry.add_to_hass(hass)
    hass.config.components.add("http")
    hass.config.components.add("frontend")
    with patch(FRONTEND, new=AsyncMock()):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


@pytest.mark.asyncio
async def test_diagnostics_does_no_blocking_io(hass, enable_custom_integrations, no_loop_io):
    entry = await _setup(hass)
    with no_loop_io():
        result = await async_get_config_entry_diagnostics(hass, entry)

    manifest = Path(__file__).parent.parent / "custom_components" / DOMAIN / "manifest.json"
    assert result["integration_version"] == json.loads(manifest.read_text())["version"]
    assert result["num_dogs"] == 1
    assert "card_file_exists" in result["card_registration"]
    assert isinstance(result["storage_files"], dict)


@pytest.mark.asyncio
async def test_guard_catches_loop_io(no_loop_io):
    """The guard itself works: file I/O on the loop thread fails."""
    with no_loop_io(), pytest.raises(AssertionError, match="blocking I/O"):
        Path(__file__).stat()
