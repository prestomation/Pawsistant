# IDEAS.md — Pawsistant Future Features

## Card

- **Configurable timeline range** — extend the 24h timeline to show last 2, 3, or 7 days, configurable in card options. Useful for reviewing and deleting old events directly from the UI.
- **Customizable button set** — let users configure which buttons appear, their order, labels, and icons via the card editor. Currently hardcoded to `shown_types` list; should support arbitrary event types and custom buttons.
- **Multi-dog card UX** — currently one card per dog. Consider: dog switcher dropdown, auto-discover all dogs with tabs, or combined "all dogs" view.

## Data

- **Track who created events** — add `created_by` field storing the HA user ID, so multi-person households can see who logged what.

## Architecture

- **Shared services manifest** — Define all Pawsistant services (name, domain, field names, types) in a single source of truth (e.g. `services_manifest.json` or YAML). Then:
  - `services.yaml` is validated against it (or auto-generated)
  - `services.js` wrapper functions are auto-generated from it
  - `__init__.py` schema registration references it
  - CI checks that all three consumers (Python, YAML, JS) stay in sync
  - Adding a new service = one place to update, everything else follows. Eliminates the class of bug where frontend calls a service that isn't registered yet, or uses camelCase vs snake_case field names that don't match the schema.