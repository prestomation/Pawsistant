#!/usr/bin/env bash
set -euo pipefail

# Assumes Docker Home Assistant is already running
# --allow-hosts: pytest-socket (from pytest-homeassistant-custom-component) blocks
# socket access by default; integration tests need to reach Docker HA on localhost
cd tests/integration
python -m pytest . -v --tb=short --override-ini="asyncio_mode=auto" --allow-hosts=localhost
