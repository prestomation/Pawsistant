"""Pytest configuration for Pawsistant tests."""
import pytest
import sys
from unittest.mock import MagicMock
import types


@pytest.fixture(autouse=True)
def mock_homeassistant(request):
    """Stub out HA modules so tests can import pawsistant without a running HA."""
    if request.node.get_closest_marker("real_ha"):
        yield
        return
    _haconst = types.ModuleType("homeassistant.const")
    _haconst.VOLUME_MIN = 0
    _haconst.VOLUME_MAX = 100

    mocks = {}
    mocks["homeassistant"] = MagicMock()
    mocks["homeassistant.core"] = MagicMock()
    mocks["homeassistant.exceptions"] = MagicMock()
    mocks["homeassistant.helpers"] = MagicMock(__version__="2024.1.0")
    mocks["homeassistant.helpers.service"] = MagicMock()
    mocks["homeassistant.helpers.translation"] = MagicMock()
    mocks["homeassistant.helpers.translation"].__version__ = "2024.1.0"
    mocks["homeassistant.const"] = _haconst

    for name, mock in mocks.items():
        sys.modules[name] = mock

    # Patch const attr on the homeassistant MagicMock so attribute
    # access (homeassistant.const.VOLUME_MIN) returns our stub
    mocks["homeassistant"].const = _haconst

    yield

    for name in mocks:
        if name in sys.modules:
            del sys.modules[name]






