"""Guard test for the ``blockbuster`` fixture in tests/conftest.py.

If the fixture stops working, the other real-HA tests prove nothing about
blocking calls. This test fails first in that case.
"""

from __future__ import annotations

import time

import pytest
from blockbuster import BlockingError

pytestmark = pytest.mark.real_ha


@pytest.mark.asyncio
async def test_blockbuster_finds_a_blocking_call():
    with pytest.raises(BlockingError):
        time.sleep(0.01)  # noqa: ASYNC251  (blocking on purpose)
