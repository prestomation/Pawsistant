#!/usr/bin/env bash
set -euo pipefail

# Assumes Docker Home Assistant is already running
# Socket access is enabled via conftest.py (pytest-socket compat)
cd tests/integration
python -m pytest . -v --tb=short --override-ini="asyncio_mode=auto" -p no:pytest_socket
