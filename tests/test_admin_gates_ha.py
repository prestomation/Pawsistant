"""Home Assistant tests for the admin-only bulk services.

``pawsistant.import_events`` and ``pawsistant.remove_dog`` change many records at
once, so only an administrator can call them. A call with no user (an automation or
a script) still works. These use real Home Assistant (the ``real_ha`` marker), so
they run in the first pytest process.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.real_ha

from homeassistant.core import Context  # noqa: E402
from homeassistant.exceptions import Unauthorized  # noqa: E402
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

from custom_components.pawsistant.const import DOMAIN  # noqa: E402

FRONTEND = "custom_components.pawsistant._ensure_frontend_registered"


async def _setup(hass) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data={"initial_dog": {"name": "Buddy"}})
    entry.add_to_hass(hass)
    # The card needs the compiled frontend, which the test env does not have.
    hass.config.components.add("http")
    hass.config.components.add("frontend")
    with patch(FRONTEND, new=AsyncMock()):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


def _dog_id(entry: MockConfigEntry) -> str:
    result = entry.runtime_data.store.get_dog_by_name("Buddy")
    assert result is not None
    return result[0]


async def _import_events(hass, entry, context=None) -> None:
    event = {
        "id": "ev-admin-1",
        "dog_id": _dog_id(entry),
        "event_type": "walk",
        "timestamp": "2026-01-05T08:00:00+00:00",
        "note": "imported",
    }
    await hass.services.async_call(
        DOMAIN, "import_events", {"events": [event]}, blocking=True, context=context
    )
    await hass.async_block_till_done()


async def _remove_dog(hass, context=None) -> None:
    with patch(FRONTEND, new=AsyncMock()):
        await hass.services.async_call(
            DOMAIN, "remove_dog", {"dog": "Buddy"}, blocking=True, context=context
        )
        await hass.async_block_till_done()


async def _imported(entry: MockConfigEntry) -> bool:
    return await entry.runtime_data.store.get_event("ev-admin-1") is not None


@pytest.mark.asyncio
async def test_non_admin_cannot_import_events(
    hass, enable_custom_integrations, hass_read_only_user
):
    entry = await _setup(hass)
    with pytest.raises(Unauthorized):
        await _import_events(hass, entry, Context(user_id=hass_read_only_user.id))
    assert not await _imported(entry)


@pytest.mark.asyncio
async def test_admin_can_import_events(hass, enable_custom_integrations, hass_admin_user):
    entry = await _setup(hass)
    await _import_events(hass, entry, Context(user_id=hass_admin_user.id))
    assert await _imported(entry)


@pytest.mark.asyncio
async def test_call_without_user_can_import_events(hass, enable_custom_integrations):
    entry = await _setup(hass)
    await _import_events(hass, entry)
    assert await _imported(entry)


@pytest.mark.asyncio
async def test_non_admin_cannot_remove_dog(
    hass, enable_custom_integrations, hass_read_only_user
):
    entry = await _setup(hass)
    with pytest.raises(Unauthorized):
        await _remove_dog(hass, Context(user_id=hass_read_only_user.id))
    assert entry.runtime_data.store.get_dog_by_name("Buddy") is not None


@pytest.mark.asyncio
async def test_admin_can_remove_dog(hass, enable_custom_integrations, hass_admin_user):
    entry = await _setup(hass)
    await _remove_dog(hass, Context(user_id=hass_admin_user.id))
    assert entry.runtime_data.store.get_dog_by_name("Buddy") is None


@pytest.mark.asyncio
async def test_call_without_user_can_remove_dog(hass, enable_custom_integrations):
    entry = await _setup(hass)
    await _remove_dog(hass)
    assert entry.runtime_data.store.get_dog_by_name("Buddy") is None
