#!/usr/bin/env bash
set -euo pipefail

# Verify the release asset we are about to publish, by reading the zip itself
# rather than the working tree it was supposedly built from.
#
#   ci/verify-zip.sh 2.24.0
#
# v2.15.0 shipped a zip whose manifest said 2.14.0 — byte-identical to a stale
# pawsistant.zip that used to be committed at the repo root. The old check only
# asserted the file existed, which it always did, straight from the checkout.
# This one asserts the contents.

if [ $# -ne 1 ]; then
  echo "usage: $0 <expected-version>" >&2
  exit 2
fi

VERSION="$1"
export VERSION

if [ ! -f pawsistant.zip ]; then
  echo "::error::pawsistant.zip not found — the release would have no HACS asset."
  exit 1
fi

python3 - <<'PY'
import json
import os
import re
import sys
import zipfile

version = os.environ["VERSION"]
errors = []

with zipfile.ZipFile("pawsistant.zip") as zf:
    names = set(zf.namelist())

    required = {"manifest.json", "const.py", "frontend/pawsistant-card.js"}
    for missing in sorted(required - names):
        errors.append(f"{missing} is missing from the zip")

    if "manifest.json" in names:
        manifest_version = json.loads(zf.read("manifest.json")).get("version")
        if manifest_version != version:
            errors.append(
                f"manifest.json in the zip says {manifest_version!r}, expected {version!r}"
            )

    if "const.py" in names:
        const_src = zf.read("const.py").decode("utf-8")
        match = re.search(r'^CARD_VERSION\s*=\s*"([^"]+)"', const_src, re.MULTILINE)
        card_version = match.group(1) if match else None
        if card_version != version:
            errors.append(
                f"const.py in the zip has CARD_VERSION {card_version!r}, expected {version!r}"
            )

    if "frontend/pawsistant-card.js" in names:
        # The bundle carries the version in its banner and injects the same
        # value as the `card-version` module. If it disagrees, the card was
        # built before the version was stamped.
        banner = zf.read("frontend/pawsistant-card.js")[:1024].decode("utf-8", "replace")
        match = re.search(r"^ \* Version: (.+)$", banner, re.MULTILINE)
        bundle_version = match.group(1).strip() if match else None
        if bundle_version != version:
            errors.append(
                f"pawsistant-card.js was built at version {bundle_version!r},"
                f" expected {version!r} — stamp the version before building the card"
            )

    # Files that should never ship. Their presence means the zip was appended
    # to an older archive instead of built fresh.
    unwanted = sorted(
        n
        for n in names
        if n.endswith((".pyc", "package.json", "package-lock.json", "tsconfig.json", "rollup.config.mjs"))
        or "/node_modules/" in n
        or "/__pycache__/" in n
        or "/src/" in n
        or "/test/" in n
    )
    if unwanted:
        errors.append("zip contains files that should be excluded: " + ", ".join(unwanted))

if errors:
    for err in errors:
        print(f"::error::{err}")
    sys.exit(1)

print(f"pawsistant.zip verified at version {version}")
PY

echo "pawsistant.zip is $(du -h pawsistant.zip | cut -f1)"
