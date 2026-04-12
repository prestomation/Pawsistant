#!/usr/bin/env bash
set -euo pipefail

npm ci
npm ci --prefix custom_components/pawsistant/frontend
pip install -r requirements-test.txt
# Unit tests need HA pytest fixtures + mocks (which pulls in pytest-socket)
pip install pytest-homeassistant-custom-component