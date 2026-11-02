#!/usr/bin/env bash
set -euo pipefail

# Build the HACS release asset from the current working tree.
#
# The `rm -f` is load-bearing: `zip -r archive .` *appends* to an existing
# archive. It replaces entries whose files still exist, but silently keeps
# entries for files that have since been deleted or renamed — so a stale
# pawsistant.zip left in the workspace leaks removed files into every
# subsequent release. Always start from nothing.
rm -f pawsistant.zip

cd custom_components/pawsistant
# Exclusion patterns are matched against the *stored* path, so a bare
# "package.json" would not match "frontend/package.json". Spell out the
# frontend build files explicitly.
zip -r ../../pawsistant.zip . \
  -x "*/__pycache__/*" \
  -x "*/__pycache__" \
  -x "__pycache__/*" \
  -x "__pycache__" \
  -x "*.pyc" \
  -x "*/node_modules/*" \
  -x "*/node_modules" \
  -x "*/src/*" \
  -x "*/test/*" \
  -x "*rollup.config.mjs" \
  -x "*package.json" \
  -x "*package-lock.json" \
  -x "*tsconfig.json"
