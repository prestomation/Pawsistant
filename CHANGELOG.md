# Changelog

All notable changes to Pawsistant will be documented in this file.

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
