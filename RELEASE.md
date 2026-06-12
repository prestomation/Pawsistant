# Release Process

## Overview

Releases are produced by merging a single "release" PR to `main`. The PR bumps the version and adds a changelog entry. After merge, CI tags the commit and publishes the GitHub release automatically. No manual `git tag` step. No commits back to `main` from CI.

## Prerequisites

- All feature work merged to `main` via PRs (main is branch-protected)
- All CI checks green on `main`

## Steps

1. **Open a release PR** that contains exactly these changes:
   - `custom_components/pawsistant/manifest.json` — bump `version` to `X.Y.Z`
   - `custom_components/pawsistant/const.py` — bump `CARD_VERSION` to `"X.Y.Z"`
   - `CHANGELOG.md` — add a `## [X.Y.Z] - YYYY-MM-DD` section summarizing user-facing changes

   The two version values must match. The release workflow refuses to ship if they don't.

2. **Merge the PR.** That's it. On the merge commit to `main`, `release.yml` will:
   1. Read the version from `manifest.json`.
   2. Verify a matching `## [X.Y.Z]` entry exists in `CHANGELOG.md` and that `CARD_VERSION` matches. If either check fails, the workflow fails loudly.
   3. Skip silently if tag `vX.Y.Z` already exists (no-op on non-release pushes to main).
   4. Build `pawsistant-card.js` from TypeScript via Rollup.
   5. Build `pawsistant.zip` (HACS asset).
   6. Push tag `vX.Y.Z` to `main`.
   7. Create the GitHub Release with the changelog section as the body and `pawsistant.zip` attached.

3. **HACS picks it up.** HACS reads `hacs.json` (`zip_release: true`) and downloads `pawsistant.zip` from the release assets.

## Beta / pre-release releases

Betas go through the *exact same flow* as a stable release — the only difference is the version string. Use a PEP 440 pre-release suffix on the version: `bN` (beta), `aN` (alpha), or `rcN` (release candidate), e.g. `2.19.0b1`.

1. **Open a release PR** with the same three changes as a stable release, using the pre-release version:
   - `custom_components/pawsistant/manifest.json` — bump `version` to `2.19.0b1`
   - `custom_components/pawsistant/const.py` — bump `CARD_VERSION` to `"2.19.0b1"`
   - `CHANGELOG.md` — add a `## [2.19.0b1] - YYYY-MM-DD` section

2. **Merge the PR.** `release.yml` recognizes the pre-release version string and publishes the GitHub release with `prerelease: true`. Everything else (version/changelog validation, tag `v2.19.0b1`, zip build) is identical to a stable release.

3. **HACS shows it only to beta users.** Because the release is marked as a pre-release, HACS offers `2.19.0b1` only to users who enabled **"Show beta versions"** for the integration. Everyone else stays on the latest stable release.

4. **Going stable.** When the beta is ready, open another PR bumping to the final `2.19.0` (and add a `## [2.19.0]` changelog section). That cuts the normal release all users are offered. The beta version lives in `main`'s `manifest.json` until this bump.

Iterate with `2.19.0b2`, `2.19.0b3`, … as needed — each is its own PR, release, and `## [2.19.0bN]` changelog section, so `CHANGELOG.md` keeps an accurate record of every cut.

## Why this design

- **Single source of truth for version**: `manifest.json`. The tag name is derived from it, not typed by hand.
- **No CI writes to `main`**: the workflow only pushes tags (which aren't branch-protected). Branch protection on `main` stays fully enforced.
- **Self-validating**: mismatched versions or a missing changelog entry fail the workflow with a clear error instead of producing a broken release.
- **Idempotent**: pushing the same `main` commit twice (e.g., re-running the workflow) is a no-op once the tag exists.

## Constraints

- **Never push directly to `main`.** All changes, including the release PR, go through PRs.
- **Never create GitHub releases manually.** The release workflow handles tag, zip build, and release creation.
- **The `pawsistant-card.js` file is gitignored.** It's built by CI from TypeScript source. Do not commit it.
- **`hacs.json` must have `zip_release: true`** with `filename: pawsistant.zip` — HACS installs from the zip asset, not source.

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| Workflow fails: "manifest.json is at X.Y.Z but CHANGELOG.md has no '## [X.Y.Z]' section" | Forgot to add the changelog entry in the release PR | Open a follow-up PR adding the entry; merge to retrigger |
| Workflow fails: "manifest.json version does not match const.py CARD_VERSION" | Bumped one but not the other | Open a follow-up PR aligning both values |
| Workflow runs but exits with "Tag vX.Y.Z already exists" | Manifest version wasn't bumped (or matches a previously released version) | Bump the version in a new PR |
| HACS install fails / "No valid version found" | Missing `pawsistant.zip` asset on release | Check that `hacs.json` has `zip_release: true` and the release has the zip asset |
| Need to re-run the release workflow for a `main` commit | e.g., transient network failure during zip upload | Use the **Run workflow** button on the Release workflow page (workflow_dispatch) |
