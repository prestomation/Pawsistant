# Pawsistant 🐾

[![GitHub Release](https://img.shields.io/github/v/release/prestomation/Pawsistant?style=for-the-badge)](https://github.com/prestomation/Pawsistant/releases)
[![GitHub Downloads](https://img.shields.io/github/downloads/prestomation/Pawsistant/total.svg?style=for-the-badge)](https://github.com/prestomation/Pawsistant/releases)
[![GitHub Latest Downloads](https://img.shields.io/github/downloads-pre/prestomation/Pawsistant/latest/total?style=for-the-badge)](https://github.com/prestomation/Pawsistant/releases)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![HACS Validation](https://github.com/prestomation/Pawsistant/actions/workflows/hacs.yml/badge.svg)](https://github.com/prestomation/Pawsistant/actions/workflows/hacs.yml)
[![License](https://img.shields.io/github/license/prestomation/Pawsistant)](LICENSE)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2024.4%2B-blue.svg)](https://www.home-assistant.io/)

A local-only dog activity tracker for Home Assistant. Log walks, bathroom breaks, meals, medications, weight, and more — all stored privately in your HA instance with no cloud dependency.

---

## Screenshots

<p align="center">
  <img src="https://community-assets.home-assistant.io/original/4X/c/2/d/c2da3490e52f485712c07f1ecc7aa4d49cb9647e.jpeg" width="300" alt="Pawsistant Card — Quick-log buttons and timeline" />
  &nbsp;&nbsp;
  <img src="https://community-assets.home-assistant.io/original/4X/a/c/5/ac5da266ad6e6b56d3ba93aa4a55648bc5772deb.jpeg" width="300" alt="Pawsistant Card — Backdate and weight logging" />
</p>

---

## Features

- **Local storage only** — all data stored in HA's `.storage` directory, no cloud accounts or tokens required
- **Per-event sensors** — most-recent timestamp for each event type (pee, poop, medicine, walk, food, treat, water, grooming, training, sleep, weight, vaccine, sick)
- **Daily count sensors** — today's counts for common event types (resets at local midnight)
- **Days-since-medicine sensor** — track medication intervals for automation reminders
- **Weight sensor** — track your dog's weight over time
- **Pawsistant Card** — built-in Lovelace card auto-registers on install; log events, view the full event timeline with infinite scroll, and track stats without leaving the dashboard
- **Multi-dog support** — add and remove dogs via services at any time
- **Timezone-aware** — daily counts use your HA instance's local timezone

---

## Installation

### Via HACS (recommended)

1. Open **HACS → Integrations → ⋮ → Custom repositories**
2. Add `https://github.com/prestomation/Pawsistant` with category **Integration**
3. Search for **Pawsistant** and install
4. Restart Home Assistant

### Manual

1. Copy `custom_components/pawsistant/` into your HA config's `custom_components/` directory
2. Restart Home Assistant

---

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Pawsistant**
3. Enter your first dog's name (required), breed, and birth date (both optional)
4. HA creates sensors for your dog and auto-registers the Pawsistant card as a Lovelace resource

---

## Lovelace Card

The Pawsistant card is automatically registered when the integration loads. Add it to any dashboard:

```yaml
type: custom:pawsistant-card
dog: Sharky
```

**Card features:**
- Quick-log buttons (tap to log now, hold to backdate)
- Weight logging form with configurable unit (lbs/kg)
- Full event timeline with infinite scroll, inline edit and delete
- Stats row: pee count, poop count, days since medicine

**Card config options:**

| Key | Default | Description |
|-----|---------|-------------|
| `dog` | *(required)* | Dog's display name (must match the name used in services) |
| `shown_types` | `['poop','pee','medicine','sick','weight']` | Which event-type buttons to show |
| `weight_unit` | `lbs` | Weight unit: `lbs` or `kg` |
| `timeline_entity` | auto-detected | Override timeline sensor entity ID |
| `pee_count_entity` | auto-detected | Override pee count sensor entity ID |
| `poop_count_entity` | auto-detected | Override poop count sensor entity ID |
| `medicine_days_entity` | auto-detected | Override days-since-medicine sensor entity ID |
| `weight_entity` | auto-detected | Override weight sensor entity ID |

---

## Services

### `pawsistant.log_event`
Log an activity for a dog.

| Field | Required | Description |
|-------|----------|-------------|
| `dog` | ✅ | Dog name (case-insensitive) |
| `event_type` | ✅ | One of: `poop`, `pee`, `medicine`, `sick`, `food`, `treat`, `walk`, `water`, `sleep`, `vaccine`, `training`, `weight`, `grooming`, `teeth_brushing` |
| `note` | — | Optional note |
| `value` | — | Numeric value (required for `weight` events; lbs) |
| `timestamp` | — | ISO 8601 timestamp for backdating; defaults to now |

### `pawsistant.delete_event`
Delete an event by ID.

| Field | Required | Description |
|-------|----------|-------------|
| `event_id` | ✅ | Event ID (available in sensor `extra_state_attributes`) |

### `pawsistant.add_dog`
Register a new dog (triggers integration reload to create sensors).

| Field | Required | Description |
|-------|----------|-------------|
| `name` | ✅ | Dog's name |
| `breed` | — | Breed |
| `birth_date` | — | Birth date (YYYY-MM-DD) |

### `pawsistant.remove_dog`
Remove a dog and all associated events.

| Field | Required | Description |
|-------|----------|-------------|
| `dog` | ✅ | Dog name (case-insensitive) |

### `pawsistant.list_events`
Query events for a dog. Returns data via service response (`response_variable`).

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `dog` | ✅ | | Dog name |
| `event_type` | — | all types | Filter by event type |
| `days` | — | `7` | Number of past days to include |

**Example automation:**
```yaml
action:
  - service: pawsistant.list_events
    data:
      dog: Sharky
      event_type: medicine
      days: 30
    response_variable: medicine_events
```

### `pawsistant.import_events`
Bulk-import events from a JSON array (for migrating from other systems).

| Field | Required | Description |
|-------|----------|-------------|
| `events` | ✅ | List of event dicts with keys: `event_type`, `timestamp`, `dog_id`, `note`, `value` |

---

## Sensors

For a dog named `Sharky`, the following entities are created:

| Entity | Description |
|--------|-------------|
| `sensor.sharky_most_recent_pee` | Timestamp of last pee event |
| `sensor.sharky_most_recent_poop` | Timestamp of last poop event |
| `sensor.sharky_most_recent_medicine` | Timestamp of last medicine event |
| `sensor.sharky_most_recent_walk` | Timestamp of last walk |
| `sensor.sharky_most_recent_food` | Timestamp of last meal |
| `sensor.sharky_daily_pee_count` | Pee events today |
| `sensor.sharky_poop_count_today` | Poop events today |
| `sensor.sharky_daily_walk_count` | Walks today |
| `sensor.sharky_weight` | Most recent weight (lbs) |
| `sensor.sharky_days_since_medicine` | Days since last medicine event |
| `sensor.sharky_recent_timeline` | Count + list of events in last 24h |

---

## Storage

Events are stored in HA's `.storage` directory:

- `.storage/pawsistant` — dog registry (names, breeds, IDs)
- `.storage/pawsistant_events_YYYY` — events partitioned by year

No external database, no cloud sync, no tokens.

---

## License

MIT
