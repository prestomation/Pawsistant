# Release Process

## Overview

Releases are triggered by pushing a `vX.Y.Z` git tag to main. The CI workflow handles version bumping, building, and publishing automatically.

## Prerequisites

- All changes merged to main via PR (main branch is protected)
- CHANGELOG.md has an entry for the version being released
- All CI checks pass on main

## Steps

1. **Add changelog entry** — Edit `CHANGELOG.md` with a `## [X.Y.Z] - YYYY-MM-DD` section summarizing user-facing changes. Push via PR.

2. **Tag the release** — Once the changelog PR is merged to main:
   ```bash
   git fetch origin main
   git checkout main
   git pull origin main  # or: git reset --hard origin/main
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```

3. **CI takes over** — The `release.yml` workflow runs:
   - **Test job**: lint, unit tests, integration tests, HACS validation, hassfest
   - **Release job** (only on tag push):
     1. Bumps version in `manifest.json` and `const.py` (CARD_VERSION)
     2. Builds `pawsistant-card.js` from TypeScript source via Rollup
     3. Creates a `bump/vX.Y.Z` branch, opens a PR, waits for CI, merges with `--admin`
     4. Pulls merged main with version bump
     5. Extracts changelog section for release notes
     6. Builds `pawsistant.zip` (HACS asset)
     7. Creates GitHub Release with changelog body + zip attachment

4. **HACS picks it up** — HACS reads `hacs.json` (`zip_release: true`) and downloads `pawsistant.zip` from the GitHub release assets.

## Constraints

- **Never push directly to main.** All changes (including changelog entries) go through PRs.
- **Never create GitHub releases manually.** The release workflow handles everything.
- **The `pawsistant-card.js` file is gitignored.** It's built by CI from TypeScript source. Do not commit it.
- **`hacs.json` must have `zip_release: true`** with `filename: pawsistant.zip` — HACS installs from the zip asset, not source.
- **CHANGELOG.md must have an entry for the version** or the release workflow fails with an error.

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| Release workflow fails at "Commit version bump" | Main branch protection blocks direct push | Fixed: workflow now uses PR + `--admin` merge |
| HACS install fails / "No valid version found" | Missing `pawsistant.zip` asset on release | Check that `hacs.json` has `zip_release: true` and release has zip asset |
| `pawsistant-card.js` not found in CI | Build step must run before card JS is needed | `ci/build-card.sh` step must precede any step that needs it |
| hassfest fails on `node_modules` JSON | npm installs `tsconfig.json` files with JSON5 comments | `rm -rf custom_components/pawsistant/frontend/node_modules` before hassfest step |