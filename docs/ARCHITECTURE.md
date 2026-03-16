# ha-doglog Architecture

## Overview

`ha-doglog` is a Home Assistant custom component that integrates with the [DogLog](https://doglog.app) pet tracking app via the `pydoglog` Python library. It exposes pet activity data as HA sensors and provides a service to log new events.

## Directory Structure

```
ha-doglog/
├── hacs.json                          # HACS metadata (repo root)
├── custom_components/
│   └── doglog/
│       ├── __init__.py                # Integration setup, service registration
│       ├── manifest.json              # HA integration metadata + pip dependencies
│       ├── config_flow.py             # UI-based configuration (refresh token input)
│       ├── const.py                   # Constants (DOMAIN, config keys, defaults)
│       ├── coordinator.py             # DataUpdateCoordinator subclass
│       ├── sensor.py                  # Sensor entity definitions
│       ├── services.yaml              # Service action definitions for UI
│       ├── strings.json               # English strings for config flow + services
│       └── translations/
│           └── en.json                # English translations (copy of strings.json)
├── docs/                              # Implementation plan (this directory)
├── LICENSE
└── README.md
```

## Component Lifecycle

### 1. Installation (via HACS)

HACS clones the repo and copies `custom_components/doglog/` into the user's HA `custom_components/` directory. HA reads `manifest.json` and installs `pydoglog` from PyPI automatically via the `requirements` field.

### 2. Configuration (Config Flow)

1. User adds the "DogLog" integration via HA UI
2. `config_flow.py` presents a form asking for their DogLog **refresh token**
3. We call `pydoglog.auth.refresh_id_token()` to validate the token
4. On success, we call `DogLogClient.get_packs()` and `get_dogs()` to discover pets
5. A config entry is created storing the refresh token and discovered pack/dog metadata

### 3. Setup (`__init__.py → async_setup_entry`)

1. Create a `DogLogClient` instance from the stored refresh token
2. Create a `DogLogCoordinator` (one per config entry) that polls for events
3. Forward setup to the `sensor` platform
4. Register the `doglog.log_event` service

### 4. Data Polling (`coordinator.py`)

`DogLogCoordinator` extends `DataUpdateCoordinator`:
- Default poll interval: **5 minutes**
- On each update, fetches recent events for all dogs in all packs via `client.list_events()`
- Wraps the synchronous `pydoglog` client calls in `hass.async_add_executor_job()`
- Stores structured data: most recent event per type per dog, daily counts, latest measurements

### 5. Sensors (`sensor.py`)

Sensors read from the coordinator's cached data. Each dog gets its own HA **device** (via device registry), and sensors are grouped under that device. See [SENSORS.md](SENSORS.md) for the full sensor list.

### 6. Services (`__init__.py`)

The `doglog.log_event` service allows automations and scripts to log events to DogLog. See [SERVICES.md](SERVICES.md) for details.

## Key Design Decisions

### Synchronous pydoglog, Async HA

`pydoglog` is synchronous (uses `requests`). All client calls must be wrapped in `hass.async_add_executor_job()` to avoid blocking the HA event loop.

### One Coordinator Per Config Entry

Each config entry (one per DogLog account) gets its own coordinator. The coordinator fetches data for all packs/dogs accessible to that account.

### Device Per Dog

Each dog is registered as a separate device in the HA device registry. This groups all of a dog's sensors together and provides a clean UI. Device info:
- `identifiers`: `{(DOMAIN, dog_id)}`
- `name`: dog's name (e.g., "Sharky")
- `manufacturer`: "DogLog"
- `model`: "Pet"

### Sensor Entity Descriptions

Sensors are defined using `SensorEntityDescription` dataclasses for clean, declarative definitions. Entity IDs follow the pattern: `sensor.<dog_name>_<description>` (e.g., `sensor.sharky_most_recent_food`).

### Token Refresh

The coordinator calls `client.ensure_token()` before each data fetch. `pydoglog` handles token refresh automatically using the stored refresh token. If auth fails permanently, the coordinator raises `ConfigEntryAuthFailed` to trigger a reauthentication flow.

## Data Flow

```
DogLog Firebase DB
       │
       ▼
  pydoglog (sync HTTP)
       │
       ▼
  DogLogCoordinator (async_add_executor_job)
       │  polls every 5 min
       ▼
  coordinator.data = {
    "dogs": { dog_id: Dog, ... },
    "events": {
      dog_id: {
        "most_recent": { EventType: DogEvent, ... },
        "daily_counts": { EventType: int, ... },
        "latest_weight": float | None,
        "latest_temperature": float | None,
      }, ...
    }
  }
       │
       ▼
  Sensor entities (read from coordinator.data)
       │
       ▼
  Home Assistant UI / Automations
```

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Token refresh fails (transient) | Coordinator retries on next poll interval |
| Token permanently invalid | Raise `ConfigEntryAuthFailed` → HA shows "Reauthenticate" |
| Firebase API error | `UpdateFailed` exception → HA marks integration as unavailable |
| Network timeout | `UpdateFailed` exception → retries on next poll |
