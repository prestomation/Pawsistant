## Summary

Implements the custom event types feature for Pawsistant — all 14 event types are now fully user-editable, and users can add custom types.

### What changed

**Phase 1 — Registry Backend**
- `const.py`: `DEFAULT_EVENT_TYPES` (14 types with name/icon/color) + `DEFAULT_BUTTON_METRICS`
- `store.py`: `get_event_types()` / `save_event_types()`, `get_button_metrics()` / `save_button_metrics()`, `sync_save_meta()`
- `__init__.py`: Removed `VALID_EVENT_TYPES` whitelist from service schemas — any event_type string is now accepted
- Historical events store only `event_type` key; display metadata always looked up from registry at render time

**Phase 2 — Config Flow UI**
- "Edit event types" added to options hub menu
- `async_step_manage_event_types`: lists all event types with Edit/Delete per row
- `async_step_edit_event_type`: add or edit with key/name/icon/color/metric
- Validation: duplicate key, max 30 chars, lowercase alphanumeric, MDI icon format, hex color, valid metric
- Built-in types cannot be deleted; button metric saved only when non-default

**Phase 3 — Card Integration**
- Sensor attributes expose `event_types` + `button_metrics` from coordinator
- `buildRegistry()` reads from WS state; falls back to FALLBACK_EVENT_META before WS populated
- `getMeta(type, registry)` maps live registry `{name, icon, color}` to card `{emoji, label, color}`
- Button label uses `button_metrics` logic: `daily_count` → "N today", `days_since` → "N days", `last_value` → "28.5 lbs", `hours_since` → "N hours"
- Registry hash in `buildHash()` for render diffing

**Phase 4 — Tests**
- `tests/unit/test_event_types_registry.py`: 11 tests for registry merge, override, delete, metrics
- `tests/integration/test_lifecycle_upgrade.py`: 5 tests for upgrade path with pre-seeded .storage data
- `tests/integration/ha_config/.storage/pawsistant` + `pawsistant_events_2025`: pre-seeded upgrade simulation

**Other fixes**
- Fixed `teeth_brushing` → `teeth` in sensor.py (registry key is `teeth`)
- `sensor.py` `MOST_RECENT_EVENT_TYPES`: updated to use `teeth` key

### Files changed

```
custom_components/pawsistant/const.py       — DEFAULT_EVENT_TYPES + DEFAULT_BUTTON_METRICS
custom_components/pawsistant/store.py        — registry + metrics store methods
custom_components/pawsistant/__init__.py    — removed VALID_EVENT_TYPES whitelist
custom_components/pawsistant/config_flow.py — manage_event_types + edit_event_type steps
custom_components/pawsistant/strings.json    — new step/error translations
custom_components/pawsistant/translations/en.json
custom_components/pawsistant/coordinator.py  — event_types + button_metrics properties
custom_components/pawsistant/sensor.py       — attributes expose registry; teeth_brushing→teeth
custom_components/pawsistant/frontend/pawsistant-card.js — dynamic registry + metric logic
tests/unit/test_event_types_registry.py      — NEW
tests/integration/test_lifecycle_upgrade.py  — NEW
tests/integration/ha_config/.storage/pawsistant
tests/integration/ha_config/.storage/pawsistant_events_2025
tests/unit/test_options_flow.py              — mock const updates
```