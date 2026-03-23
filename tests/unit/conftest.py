"""conftest.py for pure unit tests.

Overrides the autouse fixtures from pytest-homeassistant-custom-component that
try to patch real HA internals — these fixtures don't apply here since we're
running pure Python unit tests with all HA dependencies mocked out.
"""

import pytest


@pytest.fixture(autouse=True)
def skip_stop_scripts():
    """No-op override: HA script helpers aren't loaded in unit tests."""
    yield


@pytest.fixture(autouse=True)
def verify_cleanup():
    """No-op override: lingering task/timer checks don't apply to unit tests."""
    yield


@pytest.fixture(autouse=True)
def bcrypt_cost():
    """No-op override: bcrypt not used in unit tests."""
    yield


@pytest.fixture(autouse=True)
def mock_network():
    """No-op override: network component not loaded in unit tests."""
    yield


@pytest.fixture(autouse=True)
def mock_get_source_ip():
    """No-op override: network source IP not needed in unit tests."""
    yield


@pytest.fixture(autouse=True)
def fail_on_log_exception():
    """No-op override: HA log exception hooks not applicable in unit tests."""
    yield
