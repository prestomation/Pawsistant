# Pawsistant — working notes for Claude

## Pull request workflow

- **Always publish a preview release when a PR implements a new feature.** Add the
  `preview-release` label to the PR. That triggers `.github/workflows/preview-release.yml`,
  which builds the card + zip, stamps a `X.Y.Z.dev<PR>` version into the manifest (zip only,
  never committed), and publishes an ephemeral, HACS-installable pre-release. It re-publishes
  on each push and is deleted when the PR closes. Skip this for pure bugfix/docs/chore PRs that
  don't add user-facing functionality.
