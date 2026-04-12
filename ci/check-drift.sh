#!/usr/bin/env bash
set -euo pipefail

# pawsistant-card.js is now gitignored and built during CI.
# No drift check needed — the build step always produces a fresh copy.
echo "✓ Drift check skipped (pawsistant-card.js is built on-the-fly, not committed)"