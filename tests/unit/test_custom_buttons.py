"""Unit tests for the custom buttons feature: shown_types selection, buttons_per_row, max 12.

These tests mirror the JS card logic in Python to verify the configuration
contract without requiring a live HA instance or JavaScript execution.

Feature spec:
- shown_types: any subset of the 15 valid event types; max 12 enforced
- buttons_per_row: integer 2–6, clamped; None/absent = flex-wrap (auto)
- No button_labels — labels/emojis come from EVENT_META only
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Mirror of JS constants / helpers
# ---------------------------------------------------------------------------

ALL_EVENT_TYPES = [
    'poop', 'pee', 'medicine', 'sick', 'food', 'treat',
    'walk', 'water', 'sleep', 'vaccine', 'training',
    'weight', 'teeth_brushing', 'grooming',
]

EVENT_META = {
    'poop':     {'emoji': '💩', 'label': 'Poop'},
    'pee':      {'emoji': '💧', 'label': 'Pee'},
    'medicine': {'emoji': '💊', 'label': 'Medicine'},
    'sick':     {'emoji': '🤒', 'label': 'Sick'},
    'food':     {'emoji': '🍖', 'label': 'Food'},
    'treat':    {'emoji': '🍪', 'label': 'Treat'},
    'walk':     {'emoji': '🦮', 'label': 'Walk'},
    'water':    {'emoji': '🥤', 'label': 'Water'},
    'sleep':    {'emoji': '😴', 'label': 'Sleep'},
    'vaccine':  {'emoji': '💉', 'label': 'Vaccine'},
    'training': {'emoji': '🎓', 'label': 'Training'},
    'weight':   {'emoji': '⚖️', 'label': 'Weight'},
    'teeth_brushing': {'emoji': '🦷', 'label': 'Teeth'},
    'grooming': {'emoji': '✂️', 'label': 'Grooming'},
}

DEFAULT_SHOWN_TYPES = ['poop', 'pee', 'medicine', 'sick', 'weight']
MAX_BUTTONS = 12


def resolve_shown_types(cfg: dict) -> list[str]:
    """Mirror JS _shownTypes() — returns shown types, trimmed to MAX_BUTTONS."""
    t = cfg.get('shown_types')
    types = list(t) if (isinstance(t, list) and len(t) > 0) else list(DEFAULT_SHOWN_TYPES)
    if len(types) > MAX_BUTTONS:
        types = types[:MAX_BUTTONS]
    return types


def resolve_buttons_per_row(cfg: dict) -> int | None:
    """Mirror JS buttonsPerRow logic — clamp 2–6 or return None."""
    bpr = cfg.get('buttons_per_row')
    if bpr is None or not isinstance(bpr, int):
        return None
    return max(2, min(6, bpr))


def get_button_display(event_type: str) -> tuple[str, str]:
    """Return (emoji, label) for a type — always from EVENT_META, no overrides."""
    meta = EVENT_META.get(event_type, {'emoji': '📝', 'label': event_type})
    return meta['emoji'], meta['label']


# ---------------------------------------------------------------------------
# Tests: shown_types selection
# ---------------------------------------------------------------------------

class TestShownTypes:
    def test_default_when_not_set(self):
        cfg = {'dog': 'Sharky'}
        assert resolve_shown_types(cfg) == DEFAULT_SHOWN_TYPES

    def test_default_when_empty_list(self):
        cfg = {'dog': 'Sharky', 'shown_types': []}
        assert resolve_shown_types(cfg) == DEFAULT_SHOWN_TYPES

    def test_custom_subset(self):
        types = ['poop', 'walk', 'food', 'treat']
        cfg = {'dog': 'Sharky', 'shown_types': types}
        assert resolve_shown_types(cfg) == types

    def test_all_14_types_supported(self):
        """Every type in ALL_EVENT_TYPES is a valid choice (14 types exist)."""
        assert len(ALL_EVENT_TYPES) == 14
        for t in ALL_EVENT_TYPES:
            assert t in EVENT_META, f"Missing meta for type: {t}"

    def test_single_type(self):
        cfg = {'dog': 'Sharky', 'shown_types': ['medicine']}
        assert resolve_shown_types(cfg) == ['medicine']

    def test_order_preserved(self):
        types = ['sleep', 'food', 'poop', 'vaccine']
        cfg = {'dog': 'Sharky', 'shown_types': types}
        assert resolve_shown_types(cfg) == types


# ---------------------------------------------------------------------------
# Tests: max 12 enforcement
# ---------------------------------------------------------------------------

class TestMaxButtons:
    def test_exactly_12_unchanged(self):
        types_12 = ALL_EVENT_TYPES[:12]
        cfg = {'dog': 'Sharky', 'shown_types': types_12}
        result = resolve_shown_types(cfg)
        assert len(result) == 12
        assert result == types_12

    def test_over_12_trimmed(self):
        # All 14 types — should trim to 12
        cfg = {'dog': 'Sharky', 'shown_types': ALL_EVENT_TYPES}
        result = resolve_shown_types(cfg)
        assert len(result) == MAX_BUTTONS
        assert result == ALL_EVENT_TYPES[:MAX_BUTTONS]

    def test_under_12_unchanged(self):
        types = ['poop', 'pee', 'food']
        cfg = {'dog': 'Sharky', 'shown_types': types}
        assert len(resolve_shown_types(cfg)) == 3

    def test_defaults_within_limit(self):
        assert len(DEFAULT_SHOWN_TYPES) <= MAX_BUTTONS


# ---------------------------------------------------------------------------
# Tests: buttons_per_row
# ---------------------------------------------------------------------------

class TestButtonsPerRow:
    def test_not_set_returns_none(self):
        assert resolve_buttons_per_row({'dog': 'Sharky'}) is None

    def test_valid_range(self):
        for n in (2, 3, 4, 5, 6):
            assert resolve_buttons_per_row({'dog': 'Sharky', 'buttons_per_row': n}) == n

    def test_below_min_clamped_to_2(self):
        assert resolve_buttons_per_row({'dog': 'Sharky', 'buttons_per_row': 1}) == 2

    def test_above_max_clamped_to_6(self):
        assert resolve_buttons_per_row({'dog': 'Sharky', 'buttons_per_row': 99}) == 6

    def test_non_integer_returns_none(self):
        assert resolve_buttons_per_row({'dog': 'Sharky', 'buttons_per_row': 'auto'}) is None

    def test_none_explicit_returns_none(self):
        assert resolve_buttons_per_row({'dog': 'Sharky', 'buttons_per_row': None}) is None


# ---------------------------------------------------------------------------
# Tests: button display (no overrides — always from EVENT_META)
# ---------------------------------------------------------------------------

class TestButtonDisplay:
    def test_known_types_use_event_meta(self):
        for t in ALL_EVENT_TYPES:
            emoji, label = get_button_display(t)
            assert emoji == EVENT_META[t]['emoji']
            assert label == EVENT_META[t]['label']

    def test_unknown_type_fallback(self):
        emoji, label = get_button_display('custom_unknown')
        assert emoji == '📝'
        assert label == 'custom_unknown'

    def test_shown_types_buttons_use_meta(self):
        """Buttons rendered for shown_types always use EVENT_META — no overrides."""
        cfg = {
            'dog': 'Sharky',
            'shown_types': ['walk', 'food', 'sleep'],
        }
        for t in resolve_shown_types(cfg):
            emoji, label = get_button_display(t)
            assert emoji == EVENT_META[t]['emoji']
            assert label == EVENT_META[t]['label']


# ---------------------------------------------------------------------------
# Tests: combined config
# ---------------------------------------------------------------------------

class TestCombinedConfig:
    def test_full_config(self):
        cfg = {
            'dog': 'Sharky',
            'buttons_per_row': 4,
            'shown_types': ['poop', 'pee', 'walk', 'food', 'treat', 'medicine'],
        }
        shown = resolve_shown_types(cfg)
        assert shown == ['poop', 'pee', 'walk', 'food', 'treat', 'medicine']
        assert resolve_buttons_per_row(cfg) == 4
        for t in shown:
            emoji, label = get_button_display(t)
            assert emoji and label  # all have non-empty display

    def test_max_12_with_buttons_per_row(self):
        cfg = {
            'dog': 'Sharky',
            'buttons_per_row': 3,
            'shown_types': ALL_EVENT_TYPES,  # 14, trimmed to 12
        }
        shown = resolve_shown_types(cfg)
        assert len(shown) == 12
        assert resolve_buttons_per_row(cfg) == 3
