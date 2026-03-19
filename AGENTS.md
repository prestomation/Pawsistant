# AGENTS.md — Pawsistant

## Workflow

- **Never push directly to main.** Always use a feature branch and open a PR.
- Wait for CI (tests, HACS validation, Amazon Q code review) and Preston's approval before merging.
- **Always squash merge PRs.**
- **CHANGELOG.md** — update for every user-facing change before tagging a release. Developer-only changes (CI config, AGENTS.md, IDEAS.md) don't need changelog entries.
- **Always run tests locally before pushing.** Never use CI as the test runner.
- Install test deps: `pip install pytest pytest-homeassistant-custom-component`
- Run: `pytest tests/ -v`
- Only push when all tests pass.

## Project Structure

- **Domain:** `pawsistant` (renamed from `doglog` in March 2026)
- **Display name:** Pawsistant
- **Storage:** Local only, year-partitioned in `.storage/pawsistant_events_YYYY`
- **Frontend:** Bundled card at `custom_components/pawsistant/frontend/pawsistant-card.js` — vanilla JS, no build step
- **Tests:** Use `pytest-homeassistant-custom-component` for proper HA test fixtures. No hand-rolled HA mocks.

## Conventions

- Sensor utility functions operate on `list[dict]` (not model objects)
- Events are stored as plain dicts with keys: `id`, `event_type`, `timestamp`, `note`, `value`, `dog_id`
- Entity unique IDs are anchored to `dog_id` (survives renames)
- Use HA CSS variables in card styling (dark mode compat)
- Escape all user content before innerHTML injection (`_escape()` helper)

## CI

- `.github/workflows/lint.yml` — compile check, pytest, hassfest
- `.github/workflows/hacs.yml` — HACS validation
- `.github/workflows/integration.yml` — Docker-based integration tests (CI only, not local)
- `.github/workflows/release.yml` — auto-creates GitHub release from CHANGELOG.md on tag push
- Uses `pytest-homeassistant-custom-component` (not raw `homeassistant` package)
