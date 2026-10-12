"""The oldest supported Home Assistant is named in one file and must agree everywhere."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_ha_version", ROOT / "ci" / "check-ha-version.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECKER = _load_checker()
ENV = CHECKER.read_env((ROOT / "ci" / "oldest-ha.env").read_text())


def test_env_has_every_key():
    assert set(ENV) == {"OLDEST_HA", "OLDEST_HA_MIN", "OLDEST_PHCC", "OLDEST_PYTHON"}


def test_hacs_json_minimum_matches():
    hacs = json.loads((ROOT / "hacs.json").read_text())
    assert hacs["homeassistant"] == ENV["OLDEST_HA_MIN"]


def test_readme_badge_matches():
    major_minor = ".".join(ENV["OLDEST_HA_MIN"].split(".")[:2])
    assert f"Home%20Assistant-{major_minor}%2B" in (ROOT / "README.md").read_text()


def test_tested_version_is_not_below_the_minimum():
    from packaging.version import Version

    assert Version(ENV["OLDEST_HA"]) >= Version(ENV["OLDEST_HA_MIN"])


def test_tested_version_is_in_the_same_minor_release_as_the_minimum():
    # HACS offers the install from OLDEST_HA_MIN. CI must test that minor release.
    assert ENV["OLDEST_HA"].split(".")[:2] == ENV["OLDEST_HA_MIN"].split(".")[:2]


def test_read_env_skips_comments_and_blank_lines():
    assert CHECKER.read_env("# note\n\nA=1\n B = two \n") == {"A": "1", "B": "two"}


def test_newest_stable_skips_prerelease_yanked_and_empty():
    files = [{"yanked": False}]
    releases = {
        "2026.10.0": files,  # sorts below 2026.9.0 as a string
        "2026.11.0b1": files,
        "2026.12.0": [{"yanked": True}],
        "2027.1.0": [],
        "not-a-version": files,
    }
    assert str(CHECKER.newest_stable(releases)) == "2026.10.0"


def test_newest_stable_is_none_without_releases():
    assert CHECKER.newest_stable({}) is None
