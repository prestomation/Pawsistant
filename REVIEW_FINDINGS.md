# Pawsistant Code Review Findings

Consolidated from 3 independent reviews (2026-03-19).
Items marked ✅ are already fixed. Items marked 🔄 are pending.

## Ecosystem / HACS Readiness

| # | Sev | Issue | Status |
|---|-----|-------|--------|
| E1 | 🔴 | `strings.json`/`translations/en.json` describe old Firebase flow | 🔄 |
| E2 | 🔴 | Card version mismatch (__init__.py 2.1.1 vs JS 2.1.0) | 🔄 |
| E3 | 🔴 | No `const.py` — DOMAIN defined in 4 files | 🔄 |
| E4 | 🔴 | README documents old Firebase integration | 🔄 |
| E5 | 🟡 | Weight sensor missing `SensorDeviceClass.WEIGHT` | 🔄 |
| E6 | 🟡 | Days-since-medicine should use `UnitOfTime.DAYS` | 🔄 |
| E7 | 🟡 | `list_events` should use `ServiceResponse` pattern | 🔄 |
| E8 | 🟡 | Options flow is dead-end empty form | 🔄 |
| E9 | 🟡 | No `async_migrate_entry` for schema versions | 🔄 |
| E10 | 🟡 | Zero integration tests | 🔄 |
| E11 | 🟡 | `pydoglib` in CI but not in manifest requirements | 🔄 |
| E12 | 🔵 | Missing `hacs.json` with `render_readme` | 🔄 |
| E13 | 🔵 | CI should use `hassfest` + `hacs/action` | 🔄 |
| E14 | 🔵 | No `quality_scale.yaml` | 🔄 |
| E15 | 🔵 | Frontend `__init__.py` placeholder unnecessary | 🔄 |

## UX / Frontend

| # | Sev | Issue | Status |
|---|-----|-------|--------|
| U1 | 🔴 | Long-press undiscoverable — no visual hint | 🔄 |
| U2 | 🔴 | No aria-labels on buttons | 🔄 |
| U3 | 🔴 | Backdate form keyboard-inaccessible | 🔄 |
| U4 | 🔴 | Hard-coded pill colors bypass theming | 🔄 |
| U5 | 🔴 | No disconnectedCallback — timer leaks | 🔄 |
| U6 | 🟡 | Delete button touch target ~22px (need 44px) | 🔄 |
| U7 | 🟡 | No debounce on rapid taps | 🔄 |
| U8 | 🟡 | Form panel overflows in landscape | 🔄 |
| U9 | 🟡 | `window.confirm()` unreliable in HA webviews | 🔄 |
| U10 | 🟡 | Form labels not `<label for>` | 🔄 |
| U11 | 🟡 | No feedback on failure | 🔄 |
| U12 | 🟡 | Timeline scroll bleeds (overscroll-behavior) | 🔄 |
| U13 | 🟡 | `slugify()` breaks on non-ASCII names | 🔄 |
| U14 | 🟡 | Long notes truncated, no expand | 🔄 |
| U15 | 🟡 | Slider range too restrictive (10-180min) | 🔄 |
| U16 | 🟡 | 9 event types not reachable from card | 🔄 |
| U17 | 🟡 | Focus not returned after form close | 🔄 |
| U18 | 🔵 | Medicine status color-only (colorblind) | 🔄 |
| U19 | 🔵 | `--rgb-primary-color` not standard HA var | 🔄 |
| U20 | 🔵 | Dead code: `_loggedTypes` Set | 🔄 |
| U21 | 🔵 | Weight input needs `inputmode="decimal"` | 🔄 |
| U22 | 🔵 | Weight hardcoded lbs, no metric option | 🔄 |

## Prior Code Review (already fixed)

| # | Issue | Status |
|---|-------|--------|
| C1 | Backdated events break sort order | ✅ |
| C2 | delete_event fails for old-year events | ✅ |
| C4 | Stale `__import__("datetime")` | ✅ |
| C5 | No entities for dogs added after setup | ✅ |
| C6 | Services use has_service guards | ✅ |
| C7 | XSS in card editor | ✅ |
| I1 | Weight unit should use UnitOfMass.POUNDS | ✅ |
| I2 | Coordinator keyed by name not ID | ✅ |
| I3 | Pruning runs every 5 min | ✅ |
| I4 | import_events no validation | ✅ |
| I5 | Legacy duplicate poop sensor | ✅ |
| I6 | Weight validation range too narrow | ✅ |
| I7 | Lovelace resource errors swallowed | ✅ |
| I8 | add_dog no name uniqueness check | ✅ |

## Notes

- `iot_class: local_push` is CORRECT — data changes are user-initiated push via service calls. The 5-min coordinator recalculates time-derived values (days_since_medicine, daily counts), not fetching new data.
- Full domain rename `doglog` → `pawsistant` planned as final step.
