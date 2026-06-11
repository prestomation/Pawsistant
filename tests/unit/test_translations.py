"""Validate that every translation file mirrors strings.json exactly.

This enforces, for every custom_components/pawsistant/translations/<lang>.json:
  * identical key tree to strings.json (no missing or extra leaves),
  * every leaf is a non-empty string,
  * the set of {placeholder} tokens in each leaf matches the English source.

Keeping these in lockstep prevents shipping a locale with a stale key tree or a
broken/var-mismatched interpolation token after strings.json changes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

INTEG = Path(__file__).resolve().parents[2] / "custom_components" / "pawsistant"
STRINGS = INTEG / "strings.json"
TRANSLATIONS_DIR = INTEG / "translations"
PLACEHOLDER = re.compile(r"\{[^}]+\}")


def _leaf_paths(obj, prefix=""):
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield from _leaf_paths(value, f"{prefix}/{key}")
    else:
        yield prefix, obj


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


EN_LEAVES = dict(_leaf_paths(_load(STRINGS)))
TRANSLATION_FILES = sorted(TRANSLATIONS_DIR.glob("*.json"))


def test_translation_files_exist():
    """Sanity check: we actually discovered locale files to validate."""
    assert TRANSLATION_FILES, f"No translation files found in {TRANSLATIONS_DIR}"


@pytest.mark.parametrize("path", TRANSLATION_FILES, ids=lambda p: p.stem)
def test_translation_mirrors_strings(path: Path):
    tree = _load(path)
    leaves = dict(_leaf_paths(tree))

    missing = sorted(set(EN_LEAVES) - set(leaves))
    extra = sorted(set(leaves) - set(EN_LEAVES))
    assert not missing, f"{path.name}: missing keys {missing[:10]}"
    assert not extra, f"{path.name}: extra keys {extra[:10]}"

    for leaf_path, en_value in EN_LEAVES.items():
        value = leaves[leaf_path]
        assert isinstance(value, str) and value.strip(), (
            f"{path.name}: empty/non-string value at {leaf_path}"
        )
        en_tokens = sorted(PLACEHOLDER.findall(en_value))
        value_tokens = sorted(PLACEHOLDER.findall(value))
        assert en_tokens == value_tokens, (
            f"{path.name}: placeholder mismatch at {leaf_path}: "
            f"{en_tokens} (en) vs {value_tokens}"
        )
