# Changelog

All notable changes to Pawsistant will be documented in this file.

## [Unreleased]

## [2.20.0] - 2026-06-14

### Added
- **Event log popup for the button card** — the compact button card can now open the full event timeline in a popup, matching the big card's functionality (day headers, load-more pagination, edit, and two-tap delete). Enable it with the new opt-in `show_event_log` option (also available as a checkbox in the card editor); a 📋 button then appears in the card header. The popup is keyboard accessible (focus trap, Escape/backdrop/✕ to close) and localized in all 16 languages.

### Fixed
- **Button metric badges now show correct values on both the main card and the button card.** Several metrics were broken or misleading: the dog's weight showed up on every button, and `daily_count`, `hours_since`, and `days_since` either did nothing or only worked for a few event types. All four now compute correctly for every event type, and `days_since` no longer leaks between two event types that share a display name.
- **Future-dated events no longer show a negative age** — `days_since` now reads `0d` instead of `-1d`.
- **The main card now shows a clear "Unknown dog" error** when its configured `dog` doesn't exist, instead of silently rendering an empty card.

## [2.20.0b2] - 2026-06-13

### Fixed
- **Button metric badges now show correct values on both the main card and the button card.** Several metrics were broken or misleading: the dog's weight showed up on every button, and `daily_count`, `hours_since`, and `days_since` either did nothing or only worked for a few event types. All four now compute correctly for every event type, and `days_since` no longer leaks between two event types that share a display name.
- **Future-dated events no longer show a negative age** — `days_since` now reads `0d` instead of `-1d`.
- **The main card now shows a clear "Unknown dog" error** when its configured `dog` doesn't exist, instead of silently rendering an empty card.

## [2.20.0b1] - 2026-06-12

### Added
- **Event log popup for the button card** — the compact button card can now open the full event timeline in a popup, matching the big card's functionality (day headers, load-more pagination, edit, and two-tap delete). Enable it with the new opt-in `show_event_log` option (also available as a checkbox in the card editor); a 📋 button then appears in the card header. The popup is keyboard accessible (focus trap, Escape/backdrop/✕ to close) and localized in all 16 languages.

### Notes
- Beta release — feedback on the popup UX welcome before the stable 2.20.0 release.

## [2.19.0] - 2026-06-12

### Added
- **Full localization (15 languages)** — the integration's config/options/services UI and the Lovelace card UI are now translatable, with Arabic, German, Spanish, French, Hindi, Italian, Japanese, Korean, Dutch, Polish, Portuguese (BR), Russian, Swedish, Turkish, and Simplified Chinese shipped. The card follows your Home Assistant language automatically.

## [2.19.0b1] - 2026-06-12

### Added
- **Full localization (15 languages)** — the integration's config/options/services UI and the Lovelace card UI are now translatable, with Arabic, German, Spanish, French, Hindi, Italian, Japanese, Korean, Dutch, Polish, Portuguese (BR), Russian, Swedish, Turkish, and Simplified Chinese shipped. The card follows your Home Assistant language automatically.

### Notes
- Beta release — translations are machine-authored with structure/placeholder validation; native-speaker wording review still welcome.

## [2.18.0] - 2026-05-29

### Added
- **Pawsistant Button Card** — new Lovelace card for placing quick-log buttons on any dashboard. Multiple buttons per card, configurable grid layout, visual editor with add/remove/reorder. Tap to backdate, long-press to log instantly.
- Long-press now provides haptic feedback in HA Companion apps.

## [2.17.0] - 2026-05-26

### Added
- **Add event type dialog** — the key is now auto-generated from the display name as you type (e.g. "Vet Visit" → `vet_visit`). No more guessing what format to use
- **Icon picker** — event type icons now use HA's built-in icon browser instead of a plain text field
- **Delete event type cleanup** — removing an event type no longer leaves ghost buttons on the card

### Fixed
- **Days-since sensors now work for all event types** — teeth brushing, vaccines, and other days-since types now show their own independent count instead of sharing medicine's count
- **Form values preserved on validation error** — adding or editing an event type no longer clears all fields if something is wrong

## [2.15.0] - 2026-05-04

### Added
- **Paginated timeline via WebSocket** — Load historical events beyond the 24-hour limit with "Load more" pagination
- **Infinite scroll** — Auto-loads more events when you scroll to the bottom, with click fallback

### Fixed
- Updating one custom event type's metric (e.g. "sick" → "days_since") no longer resets other custom event type metrics back to "daily_count"

## [2.14.0] - 2026-04-23

### Added
- **Edit events in the timeline** — tap the ✏️ icon on any event row to open a pre-filled form. Change the time, note, or weight value, then tap "Update Event" to save. Event type is preserved.
- Edit icon appears on hover/touch for each timeline event row.
- Backdate slider starts at the event's original time when editing, so you can change just the note without altering the timestamp.

## [2.13.1] - 2026-04-17

### Fixed
- Poop sensor entity ID and friendly_name suffix corrected (external contributor GasparMDQ)
- Removed dead `food` branch that referenced `peeCount`

## [2.13.0] - 2026-04-16

### Fixed
- Weight-unit display: when unit is kg, button badge and form pre-fill now show the converted value instead of raw lbs (e.g. 36.3 kg instead of 80 kg)

## [2.12.1] - 2026-04-13

### Fixed
- Most-recent sensor bug: `_get_most_recent_event()` now uses `max(key=_to_datetime)` instead of first-match scan, and store sorts use `_parse_timestamp()` instead of string comparison. Fixes stale sensor values when events have mixed timezone offsets.

## [2.12.0] - 2026-04-13

### Changed
- Backdate slider defaults to "Now" (0 min) instead of 1 min ago
- Card JS removed from git tracking (built on-the-fly by CI)
- Integration test CI now builds card JS before Docker starts

## [2.11.0] - 2026-04-11

### Added
- **Hold-to-log, tap-to-backdate**: Long-press any event button (500ms) to log instantly. Tap to open the backdate form with a time slider and optional note.
- **Custom event type management**: Add, edit, and delete event types from the gear panel in the card. Deleted types can be restored by re-adding them.

### Changed
- Removed inline confirm UI (two-press to log). Hold is now the instant-log gesture; tap opens the backdate form.
- Instant sensor updates after logging an event.

### Fixed
- Card no longer fails to appear after some HA restarts.
- Button visibility checkboxes now reflect the current state reliably.
- Third-party sensors with `event_types` arrays no longer break the card.

## [2.8.0] - 2026-04-01

### Added
- Backdate slider now shows the resolved wall-clock time in the user's local timezone alongside the relative offset (e.g. "15 min ago · 2:01 PM"). Time updates live as the slider moves.

## [2.7.1] - 2026-04-01

### Changed
- HACS now installs from a release zip asset (`pawsistant.zip`), enabling the GitHub Downloads badge to accurately reflect install counts.

## [2.7.0] - 2026-04-01

### Fixed
- Pawsistant card now loads reliably after every HA restart. The Lovelace resource registration was previously deferred and could be silently skipped under certain startup conditions, causing "Custom element doesn't exist: pawsistant-card" errors. Registration now happens immediately and unconditionally.

## [2.6.0] - 2026-03-24

### Added
- **Dog management in UI**: Settings → Integrations → Pawsistant → Configure now lets you add and remove dogs directly, with a proper multi-step form. No more service calls required.
- **Configurable button layout**: Choose which event type buttons appear on the card using checkboxes in the visual editor (all 15 types available). Set `buttons_per_row` (2–6) for a fixed grid layout instead of flex-wrap. Maximum 12 buttons.
- **Rename-safe entity resolution**: The card now finds its sensors via `attributes.dog` and friendly name matching instead of slugifying the dog name. Renaming a sensor entity in HA no longer breaks the card.
- Dog name is now a dropdown in the card editor, populated automatically from registered dogs.
- Entity override fields removed from the card editor (still configurable via YAML for power users).

### Fixed
- Sensor `extra_state_attributes` now includes `dog` on all sensor types — used by the card for stable entity lookup.

## [2.5.0] - 2026-03-23

### Fixed
- Pawsistant card now auto-registers correctly on fresh install. Previously, a startup race condition caused the Lovelace resource registration to be silently skipped (the Lovelace component hadn't loaded yet when the integration set up). Registration is now deferred until `EVENT_HOMEASSISTANT_STARTED`, so the card appears in the dashboard editor automatically after restart.
- YAML-mode Lovelace users now receive a clear log message with the URL to add manually.

### Added
- Integration test: verifies the card resource is registered in Lovelace after install
- Unit tests: 7 tests covering deferred/immediate registration paths and YAML-mode logging

## [2.4.0] - 2026-03-19

### Fixed
- Multi-dog bug: removing and re-adding a dog with the same name no longer causes sensors to stay unavailable (entity registry cleanup on dog removal)

### Added
- Diagnostics support: download debug info from Settings → Devices → Pawsistant
- HACS validation workflow
- Brand icons for HACS store listing
- Integration tests for multi-dog isolation, edge case dog names, backdating, and fresh install migration check
- Release workflow now requires CI to pass before publishing
- Auto version bump from git tag (no more manual manifest/card edits)

### Changed
- README HACS install URL updated to Pawsistant repo

## [2.3.0] - 2026-03-19

### Changed
- Moved pee/poop counts and medicine days from stats pill row into the quick-log button labels
- Switched button layout from fixed grid to flex-wrap for natural flow with any number of buttons
- Removed stats pill row from card

### Added
- IDEAS.md for tracking future features

### Removed
- DogLog migration section from README and AGENTS.md
- All legacy doglog scripts (replaced by Pawsistant card's direct service calls)

## [1.0.0] - 2026-03-16

### Added
- Initial HACS release
- Local-only dog activity tracking with year-partitioned `.storage` backend
- Per-event sensors (most recent timestamp) and daily count sensors
- Pawsistant Lovelace card with quick-log buttons, backdate form, weight logging, and 24h timeline
- Multi-dog support via services
- Firebase migration support (import_events service)
