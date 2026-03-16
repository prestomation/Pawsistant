# ha-doglog Design

## Overview

ha-doglog is a Home Assistant custom component that integrates with the [DogLog](https://doglogapp.com) pet tracking app. It uses the `pydoglog` Python library to communicate with DogLog's Firebase backend, exposing pet activity data as HA sensors and providing a service to log new events from automations.

## Architecture

```
Firebase RTDB ←→ pydoglog (sync HTTP) ←→ DataUpdateCoordinator ←→ Sensors / Services
                                              ↕
                                     Config Flow (auth)
```

- **Config flow**: User pastes a Firebase refresh token. The flow validates it via `pydoglog.auth.refresh_id_token()`, discovers the user's packs and dogs, and stores credentials in a config entry.
- **Coordinator**: One `DataUpdateCoordinator` per config entry. Polls `client.list_events()` every 5 minutes. Wraps synchronous pydoglog calls with `hass.async_add_executor_job()`. Raises `ConfigEntryAuthFailed` on permanent auth failure to trigger reauthentication.
- **Sensors**: Created per-dog. Each dog becomes an HA device with sensors grouped under it.
- **Service**: `doglog.log_event` lets automations write events back to DogLog.

## File Structure

```
custom_components/doglog/
├── __init__.py          # Platform setup, service registration
├── manifest.json        # HA integration metadata
├── config_flow.py       # Refresh-token config flow
├── coordinator.py       # DataUpdateCoordinator
├── sensor.py            # All sensor entities
├── services.yaml        # Service schema
├── strings.json         # UI strings
└── translations/en.json # English translations
hacs.json                # HACS metadata
```

## Sensor Naming

All sensors use a slug-safe dog name (lowercase, spaces → underscores).

### Most-recent event sensors

Pattern: `sensor.<dog>_most_recent_<type>` (e.g., `sensor.sharky_most_recent_walk`)

- State: ISO 8601 timestamp of the most recent event of that type
- Attributes: `note`, `value` (if present), `event_id`
- Types: food, treat, walk, pee, poop, water, sleep, teeth_brushing, grooming, training, medicine, vaccine

### Daily count sensors

Pattern: `sensor.<dog>_daily_<type>_count` (e.g., `sensor.sharky_daily_walks_count`)

- State: integer count of events today
- Types: food, treat, walk, pee, poop, water

### Measurement sensors

- `sensor.<dog>_weight` — latest weight value in lbs, state_class=measurement

## Config Flow

1. User adds integration, searches "DogLog"
2. Single step: paste Firebase refresh token
3. Validation: `refresh_id_token(token)` → `DogLogClient(id_token, uid)` → `get_packs()` / `get_dogs()`
4. On success: stores `refresh_token`, `uid`, `email` in config entry titled "DogLog (<email>)"
5. On token expiry: coordinator raises `ConfigEntryAuthFailed` → HA prompts reauthentication

**How to get a refresh token**: Use the pydoglog CLI (`doglog auth token`) or the token-dumper app.

## HACS

- `hacs.json`: `name`, `content_type: "integration"`, `config_flow: true`
- `manifest.json`: `domain: "doglog"`, `requirements: ["pydoglog>=0.1.0"]`, `config_flow: true`, `iot_class: "cloud_polling"`
- Versioning: `manifest.json` version must match GitHub release tags

## Services

### `doglog.log_event`

Log a pet activity event to DogLog.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| dog | string | yes | Dog name |
| event_type | string | yes | Event type (food, walk, poop, etc.) |
| note | string | no | Optional note |
| value | float | no | Optional numeric value (e.g., weight) |

## Automations

See [AUTOMATIONS.md](./AUTOMATIONS.md) for ready-to-paste Home Assistant automation YAML examples, including daily medicine reminders, pee alerts, and poop count alerts.
