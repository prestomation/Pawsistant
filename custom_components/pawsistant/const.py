"""Constants for the Pawsistant integration."""

import re

DOMAIN = "pawsistant"
PLATFORMS = ["sensor"]
URL_BASE = "/pawsistant"
CARD_VERSION = "2.11.0"

# ── Validation constants ──────────────────────────────────────────────────
MDI_ICON_RE = re.compile(r"^(mdi|hass):[a-z0-9-]+$")
HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
VALID_BUTTON_METRICS = ["daily_count", "days_since", "last_value", "hours_since"]
# Max length for a custom event type key
MAX_EVENT_TYPE_KEY_LEN = 30
EVENT_TYPE_KEY_RE = re.compile(r"^[a-z0-9_]+$")

CONF_SPECIES = "species"
DEFAULT_SPECIES = "Dog"

# Config entry option keys
CONF_EVENT_TYPES = "event_types"
CONF_BUTTON_METRICS = "button_metrics"

# ── Default event type registry ─────────────────────────────────────────────
# 14 built-in event types.  All are user-editable: a user may rename "walk" to
# "stroll", change the icon/color, or add entirely custom types.  The store
# saves only user overrides (partial dict); the registry merges stored values
# over these defaults with stored values winning for any overridden key.
DEFAULT_EVENT_TYPES = {
    "food":     {"name": "Food",     "icon": "mdi:bowl",           "color": "#4CAF50"},
    "treat":    {"name": "Treat",    "icon": "mdi:cookie",         "color": "#FF9800"},
    "water":    {"name": "Water",   "icon": "mdi:cup-water",       "color": "#2196F3"},
    "walk":     {"name": "Walk",    "icon": "mdi:walk",            "color": "#8BC34A"},
    "pee":      {"name": "Pee",     "icon": "mdi:water",           "color": "#FFEB3B"},
    "poop":     {"name": "Poop",    "icon": "mdi:emoticon-poop",   "color": "#795548"},
    "medicine": {"name": "Medicine","icon": "mdi:pill",             "color": "#F44336"},
    "weight":   {"name": "Weight",  "icon": "mdi:scale-bathroom",  "color": "#9C27B0"},
    "vaccine":  {"name": "Vaccine", "icon": "mdi:needle",          "color": "#E91E63"},
    "sleep":    {"name": "Sleep",   "icon": "mdi:sleep",           "color": "#3F51B5"},
    "grooming": {"name": "Grooming","icon": "mdi:content-cut",     "color": "#00BCD4"},
    "training": {"name": "Training","icon": "mdi:hand-pointing-up", "color": "#FF5722"},
    "teeth":    {"name": "Teeth",   "icon": "mdi:toothbrush",      "color": "#009688"},
    "sick":     {"name": "Sick",    "icon": "mdi:emoticon-sick",   "color": "#F44336"},
}

# Button metrics — controls what label appears on each sensor button.
# Allowed values:
#   daily_count   → "N today"
#   days_since    → "N days"
#   last_value    → "[value] [unit]" (from most recent event)
#   hours_since   → "N hours"
# Types not in this dict default to "daily_count".
DEFAULT_BUTTON_METRICS = {
    "medicine": "days_since",
    "weight":   "last_value",
    "vaccine":  "days_since",
    "walk":     "daily_count",
}