#!/usr/bin/env python3
"""Check which Home Assistant version the test environment resolved.

``pip install pytest-homeassistant-custom-component`` does not fail when the Python
is older than Home Assistant needs. It goes back to an old release, and the job tests
an API that nobody runs. This script fails a job that did not get the version that it
asked for.

    python ci/check-ha-version.py oldest   # must be exactly OLDEST_HA
    python ci/check-ha-version.py stable   # must be the newest stable on PyPI

When PyPI is not reachable, the ``stable`` check is skipped. A network error must not
turn CI red.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from packaging.version import InvalidVersion, Version

_PYPI = "https://pypi.org/pypi/homeassistant/json"
_ENV = Path(__file__).with_name("oldest-ha.env")


def read_env(text: str) -> dict[str, str]:
    """Read the KEY=value lines of ``oldest-ha.env``."""
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def newest_stable(releases: dict[str, list[dict]]) -> Version | None:
    """Pick the newest installable stable version from a PyPI ``releases`` mapping."""
    found = []
    for raw, files in releases.items():
        if not files or all(f.get("yanked") for f in files):
            continue
        try:
            version = Version(raw)
        except InvalidVersion:
            continue
        if not version.is_prerelease and not version.is_devrelease:
            found.append(version)
    return max(found, default=None)


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in ("oldest", "stable"):
        print(__doc__)
        return 2
    from homeassistant.const import __version__

    installed = Version(__version__)
    print(f"Installed Home Assistant: {installed}")
    if argv[1] == "oldest":
        wanted = Version(read_env(_ENV.read_text())["OLDEST_HA"])
        if installed != wanted:
            print(f"FAIL: the oldest lane needs {wanted}.")
            return 1
        return 0
    try:
        with urllib.request.urlopen(_PYPI, timeout=30) as response:
            newest = newest_stable(json.load(response)["releases"])
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError):
        print("PyPI is not reachable. The check is skipped.")
        return 0
    if newest is not None and installed < newest:
        print(
            f"FAIL: the newest stable is {newest}. Check the Python version of the job."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
