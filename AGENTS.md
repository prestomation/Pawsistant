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
- **Update RELEASE.md and AGENTS.md** whenever there are architectural or workflow changes (new CI steps, build process changes, branch protection updates, etc.). These docs must stay accurate.
- **Always post screenshots to the PR when a change adds, changes, or fixes UI.** Capture the relevant card/dashboard state with the Playwright e2e harness (see `tests/e2e/screenshots.capture.ts`), commit the PNG(s) under `docs/images/`, and embed them in the PR description (or a PR comment) via a `raw.githubusercontent.com/<owner>/<repo>/<commit-sha>/docs/images/<file>.png` URL pinned to the commit that added them — this is how reviewers see before/after without the GitHub web composer. (Example: PR #56.)

## Project Structure

- **Domain:** `pawsistant` (renamed from `doglog` in March 2026)
- **Display name:** Pawsistant
- **Storage:** Local only, year-partitioned in `.storage/pawsistant_events_YYYY`
- **Frontend:** TypeScript + Rollup build at `custom_components/pawsistant/frontend/`. Source in `src/*.ts`, builds to `pawsistant-card.js` (gitignored, built by CI). See `ci/build-card.sh`.
- **Tests:** Use `pytest-homeassistant-custom-component` for proper HA test fixtures. No hand-rolled HA mocks.

## Conventions

- Sensor utility functions operate on `list[dict]` (not model objects)
- Events are stored as plain dicts with keys: `id`, `event_type`, `timestamp`, `note`, `value`, `dog_id`
- Entity unique IDs are anchored to `dog_id` (survives renames)
- Use HA CSS variables in card styling (dark mode compat)
- Escape all user content before innerHTML injection (`_escapeHTML()` helper)

## Card JS — Entity Resolution Rule

**Never build entity IDs by slugifying the dog name.** Users can rename entities in HA and slugified lookups will silently break.

All Pawsistant sensors expose `attributes.dog` (the canonical dog name string). The card must resolve entities by:
1. Scanning `hass.states` for entities where `state.attributes.dog === dogName` (case-insensitive)
2. Identifying sensor role by `friendly_name` suffix (e.g. "Recent Timeline", "Daily Pee Count")
3. Allowing explicit `*_entity` config overrides to win (for YAML power users)

The helper for this is `findEntitiesByDog(hass, dogName)` in `pawsistant-card.js`.

When adding new sensors: always include `"dog": self._dog_name` in `extra_state_attributes`. This is the stable anchor the card relies on.

## Internationalization (i18n)

- **Backend** (config/options/services UI): `strings.json` is the source of truth; per-locale files live in `translations/<lang>.json`. They are kept in lockstep by `tests/unit/test_translations.py`, which enforces an identical key tree, non-empty values, and matching `{placeholder}` tokens for every locale. After editing `strings.json`, update every `translations/*.json` (the test will fail otherwise).
- **Card frontend**: a dependency-free module at `frontend/src/i18n/`. `en.ts` is the typed source of truth (`TranslationKey`/`Dict`); each locale is a `Dict`; `locales.ts` is the registry. The card reads `hass.language` and calls `setLang()` in its `hass` setter; render code uses the ambient `T()`/`TP()` wrappers. `frontend/test/i18n.test.js` asserts every locale mirrors the English key set.
- **Built-in event-type labels** are localized for **display only** (`_displayLabel`). The button card reads per-type metric values (daily_count / days_since / hours_since) from the timeline sensor's `daily_counts` / `days_since` / `last_event_ts` map attributes, keyed by the language-independent `event_type`. A legacy `friendly_name`-suffix match for `days_since` remains only as a backward-compat fallback — it uses the English label, so never localize that fallback path.

## Browser e2e tests (Playwright)

- Location: `tests/e2e/` (Playwright + Chromium) drives a real browser against the same HA Docker container as `tests/integration`, on the seeded `pawsistant-e2e` YAML dashboard.
- Run locally / in a session: `bash ci/e2e-up.sh` (builds the card, starts HA, runs Playwright, tears down). `KEEP_UP=1` leaves HA running.
- Environment prep: `ci/setup-browser-env.sh` starts the Docker daemon and installs Chromium. It is wired to a Claude Code **SessionStart** hook (`.claude/settings.json`) so web sessions are e2e-ready.
- Auth: `tests/e2e/global-setup.ts` completes HA onboarding and performs a real UI login, saving an authenticated storage state.

## CI

- `.github/workflows/test.yml` — lint, pytest, HACS validation, hassfest, frontend tests
- `.github/workflows/integration.yml` — Docker-based integration tests (CI only, not local)
- `.github/workflows/e2e.yml` — Docker + Playwright browser smoke tests; uploads the Playwright report on failure
- `.github/workflows/release.yml` — tag-triggered release: tests, version bump via PR, build zip, create GitHub release
- Uses `pytest-homeassistant-custom-component` (not raw `homeassistant` package)

## Release Process

See [RELEASE.md](RELEASE.md) for the full release process, including tag workflow, CI pipeline, and troubleshooting.
