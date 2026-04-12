#!/usr/bin/env bash
set -euo pipefail

# Assumes Docker Home Assistant is already running
cd tests/integration
python -m pytest . -v --tb=short --override-ini="asyncio_mode=auto"
