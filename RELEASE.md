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
   4. Stamp `X.Y.Z` into `manifest.json` and `const.py` (`ci/stamp-version.sh`) — a no-op given step 2, but it means the shipped version is written by the workflow rather than trusted to be whatever the checkout contained.
   5. Build `pawsistant-card.js` from TypeScript via Rollup. Rollup reads `CARD_VERSION` from `const.py`, so this must come after the stamp.
   6. Build `pawsistant.zip` (HACS asset) from scratch (`ci/build-zip.sh`).
   7. Verify the built zip (`ci/verify-zip.sh`): its `manifest.json`, its `const.py` `CARD_VERSION`, and the version baked into the card bundle must all equal `X.Y.Z`, and it must contain no build files that should have been excluded. Fails the release if not.
   8. Push tag `vX.Y.Z` to `main`.
   9. Create the GitHub Release with the changelog section as the body and `pawsistant.zip` attached.

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

## Preview releases (test a PR build without merging)

Sometimes you want to **install and try a PR's build via HACS** before merging it —
without bumping the version or cutting a real release. Add the **`preview-release`**
label to the PR and `preview-release.yml` stamps a synthetic version (`X.Y.Z.dev<pr>`)
into the zip's `manifest.json` *and* `const.py`, builds the card + `pawsistant.zip` from
the PR head, and publishes an **ephemeral GitHub pre-release** with the zip attached.
Stamping `CARD_VERSION` too is what keeps the preview's Lovelace resource URL
(`/pawsistant/pawsistant-card.js?v=<CARD_VERSION>`) distinct from the stable release's,
so a browser doesn't keep serving the cached stable bundle after you install the
preview. Install it from
HACS: open *Pawsistant* → ⋮ → **Redownload**, enable **Show beta versions**, and pick
`X.Y.Z.dev<pr>` (or download `pawsistant.zip` from the release and unzip into
`config/custom_components/pawsistant/`).

- **Opt-in only** — nothing happens without the label (and only users with write
  access can label).
- **Same-repo PRs only** — fork PRs get no token and are not built this way.
- **Owner approval** — the publish job runs in the `preview-release` GitHub
  Environment; add **Required reviewers** to it (Settings → Environments) to make each
  build wait for an explicit approval.
- **Ephemeral & low-noise** — it's a **pre-release** (`prerelease: true`), so it's
  offered only to users who enabled *Show beta versions*; the `.dev<pr>` version sorts
  *below* the real `X.Y.Z` release so it never nags anyone as an update; it's
  re-published on each push and **deleted automatically when the PR closes**.

## Why this design

- **Single source of truth for version**: `manifest.json`. The tag name is derived from it, not typed by hand, and `ci/stamp-version.sh` propagates it to `const.py` so the two can't drift within a build.
- **No CI writes to `main`**: the workflow only pushes tags (which aren't branch-protected). Branch protection on `main` stays fully enforced.
- **Self-validating**: mismatched versions or a missing changelog entry fail the workflow with a clear error instead of producing a broken release.
- **The artifact is checked, not assumed**: `ci/verify-zip.sh` reads the built zip and asserts its contents, because "the file exists" was never evidence that it was built from this commit. `v2.15.0` shipped a zip whose manifest said `2.14.0` — byte-identical to a stale `pawsistant.zip` that used to be committed at the repo root — and the old existence check passed happily.
- **Idempotent**: pushing the same `main` commit twice (e.g., re-running the workflow) is a no-op once the tag exists.

## Constraints

- **Never push directly to `main`.** All changes, including the release PR, go through PRs.
- **Never create GitHub releases manually.** The release workflow handles tag, zip build, and release creation.
- **The `pawsistant-card.js` file is gitignored.** It's built by CI from TypeScript source. Do not commit it.
- **`pawsistant.zip` is gitignored.** It's a build artifact. Committing it once already caused a release to ship a months-old copy of the integration; `ci/build-zip.sh` now deletes any zip in the workspace before building, because `zip -r` appends to an existing archive and keeps entries for files that no longer exist.
- **`hacs.json` must have `zip_release: true`** with `filename: pawsistant.zip` — HACS installs from the zip asset, not source.

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| Workflow fails: "manifest.json is at X.Y.Z but CHANGELOG.md has no '## [X.Y.Z]' section" | Forgot to add the changelog entry in the release PR | Open a follow-up PR adding the entry; merge to retrigger |
| Workflow fails: "manifest.json version does not match const.py CARD_VERSION" | Bumped one but not the other | Open a follow-up PR aligning both values |
| Workflow runs but exits with "Tag vX.Y.Z already exists" | Manifest version wasn't bumped (or matches a previously released version) | Bump the version in a new PR |
| HACS install fails / "No valid version found" | Missing `pawsistant.zip` asset on release | Check that `hacs.json` has `zip_release: true` and the release has the zip asset |
| Workflow fails: "manifest.json in the zip says 'A', expected 'B'" | The zip wasn't built from this commit — usually a stale `pawsistant.zip` in the workspace | Confirm `pawsistant.zip` is gitignored and that `ci/build-zip.sh` ran; never commit the zip |
| Workflow fails: "pawsistant-card.js was built at version 'A', expected 'B'" | The card was bundled before the version was stamped | Keep `ci/stamp-version.sh` ahead of `ci/build-card.sh` — Rollup bakes `const.py`'s `CARD_VERSION` into the bundle |
| Card doesn't appear after installing a build, but works after a full restart | Two builds shipped the same `CARD_VERSION`, so the Lovelace resource URL's `?v=` cache-buster never changed | Every published build must carry a distinct `CARD_VERSION`; `ci/verify-zip.sh` enforces this |
| Need to re-run the release workflow for a `main` commit | e.g., transient network failure during zip upload | Use the **Run workflow** button on the Release workflow page (workflow_dispatch) |
