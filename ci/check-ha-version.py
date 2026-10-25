#!/usr/bin/env python3
"""Check which Home Assistant version the test environment resolved.

``pip install pytest-homeassistant-custom-component`` does not fail when the Python
is older than Home Assistant needs. It goes back to an old release, and the job tests
an API that nobody runs. This script fails a job that did not get the version that it
asked for.

    python ci/check-ha-version.py oldest   # must be exactly OLDEST_HA
    python ci/check-ha-version.py stable   # must be the version that the newest
                                           # pytest-homeassistant-custom-component pins

The newest Home Assistant on PyPI is not the target. A Home Assistant patch release
comes out some hours before the test package that pins it, and the job cannot install
it before then.

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

_PYPI = "https://pypi.org/pypi/pytest-homeassistant-custom-component/json"
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


def pinned_ha(requires_dist: list[str] | None) -> Version | None:
    """Read the ``homeassistant==X`` pin from a PyPI ``requires_dist`` list."""
    for requirement in requires_dist or []:
        name, sep, pin = requirement.partition("==")
        if sep and name.strip() == "homeassistant":
            try:
                return Version(pin.split(";")[0].strip())
            except InvalidVersion:
                return None
    return None


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
            newest = pinned_ha(json.load(response)["info"]["requires_dist"])
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError):
        print("PyPI is not reachable. The check is skipped.")
        return 0
    if newest is not None and installed < newest:
        print(
            f"FAIL: the newest test package pins {newest}. "
            "Check the Python version of the job."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
