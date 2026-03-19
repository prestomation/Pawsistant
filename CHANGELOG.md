# Changelog

All notable changes to Pawsistant will be documented in this file.

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
