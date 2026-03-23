"""Fixtures for Pawsistant tests."""

from collections.abc import Generator
from unittest.mock import Mock, patch

import pytest


@pytest.fixture(autouse=True, scope="session")
def mock_network() -> Generator[None, None, None]:
    """Override the pytest-homeassistant-custom-component mock_network fixture.

    Newer versions of homeassistant changed the import path for ifaddr, causing
    the upstream fixture to fail with AttributeError on
    ``homeassistant.components.network.util.ifaddr``.  We patch the canonical
    ``ifaddr.get_adapters`` directly so the tests work across all supported HA
    versions.

    When ``ifaddr`` is not installed (e.g. plain integration tests that use
    requests against a real Docker HA instance), we yield without mocking.
    """
    try:
        import ifaddr  # noqa: F401 — presence check only
    except ImportError:
        # Not installed in this environment; skip the mock entirely.
        yield
        return

    adapters = [
        Mock(
            nice_name="eth0",
            ips=[Mock(is_IPv6=False, ip="10.10.10.10", network_prefix=24)],
            index=0,
        )
    ]

    with patch("ifaddr.get_adapters", return_value=adapters):
        yield
