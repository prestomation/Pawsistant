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


@pytest.fixture(autouse=True)
def blockbuster(request):
    """Fail a real-HA test when code blocks the event loop thread.

    Blockbuster patches file, socket, sleep and similar calls. When such a call
    runs while an event loop runs in the same thread, it raises BlockingError with
    the file and line. Home Assistant gives the same warning at run time
    ("Detected blocking call"). This fixture finds the problem in the tests
    instead. Only tests with the ``real_ha`` marker run HA code in an event loop.
    The tests with HA stubs have no loop to block.
    """
    if not request.node.get_closest_marker("real_ha"):
        yield None
        return
    from blockbuster import blockbuster_ctx

    with blockbuster_ctx() as bb:
        # The test run installs a stderr log handler. Its write is not code of ours.
        bb.functions["io.TextIOWrapper.write"].can_block_in("logging/__init__.py", "emit")
        yield bb
