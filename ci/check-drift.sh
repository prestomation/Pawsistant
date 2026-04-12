#!/usr/bin/env bash
set -euo pipefail

cd custom_components/pawsistant/frontend
# Strip the build date line (changes every build) before comparing
grep -v 'Built:' pawsistant-card.js > /tmp/built.js
grep -v 'Built:' <(git show HEAD:custom_components/pawsistant/frontend/pawsistant-card.js 2>/dev/null || echo '') > /tmp/committed.js || true
# Only fail if committed file exists and differs
if [ -s /tmp/committed.js ]; then
  if ! diff -q /tmp/built.js /tmp/committed.js > /dev/null 2>&1; then
    echo "ERROR: pawsistant-card.js is out of date. Run 'npm run build' and commit the result."
    exit 1
  fi
fi
