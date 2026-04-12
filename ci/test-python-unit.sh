#!/usr/bin/env bash
set -euo pipefail

find custom_components -name "*.py" -exec python -m py_compile {} +
# Run real-HA tests first (before any mock contamination)
python -m pytest tests/test_sensor_utils.py -v
# Run all remaining tests (use HA mocks)
python -m pytest tests/ -v --ignore=tests/integration --ignore=tests/test_sensor_utils.py
