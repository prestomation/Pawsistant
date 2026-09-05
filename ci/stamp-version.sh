#!/usr/bin/env bash
set -euo pipefail

# Stamp a version into every place that carries one, so a release can never
# ship a manifest and a card bundle that disagree.
#
#   ci/stamp-version.sh 2.24.0
#
# Writes:
#   custom_components/pawsistant/manifest.json  ->  "version"
#   custom_components/pawsistant/const.py       ->  CARD_VERSION
#
# CARD_VERSION is the cache-buster on the Lovelace resource URL
# (/pawsistant/pawsistant-card.js?v=<CARD_VERSION>) *and* is baked into the
# bundle by rollup.config.mjs, so this must run BEFORE ci/build-card.sh.
#
# In the release workflow the stamp is a no-op (the release PR already bumped
# both files, and CI refuses to ship if they disagree). In the preview-release
# workflow it is what keeps a dev build from reusing the stable release's
# cache-buster.

if [ $# -ne 1 ]; then
  echo "usage: $0 <version>" >&2
  exit 2
fi

VERSION="$1"
export VERSION

python3 - <<'PY'
import json
import os
import re
from pathlib import Path

version = os.environ["VERSION"]
base = Path("custom_components/pawsistant")

manifest_path = base / "manifest.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
manifest["version"] = version
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

const_path = base / "const.py"
const_src = const_path.read_text(encoding="utf-8")
const_src, n = re.subn(
    r'^CARD_VERSION\s*=\s*".*"$',
    f'CARD_VERSION = "{version}"',
    const_src,
    count=1,
    flags=re.MULTILINE,
)
if n != 1:
    raise SystemExit(f"::error::CARD_VERSION assignment not found in {const_path}")
const_path.write_text(const_src, encoding="utf-8")

print(f"Stamped version {version} into manifest.json and const.py")
PY
