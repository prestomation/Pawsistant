# Plan: Reimplement ha-doglog Without pydoglog

## Goal

Remove the `pydoglog` dependency and Firebase backend. Replace with Home Assistant's native local storage so the integration is fully self-contained. Keep the core value: tracking dog events (especially weight and medicine over time) with notifications via HA automations, and entering events via service calls from an HA dashboard.

## Architecture Change

```
BEFORE:  Firebase RTDB ←→ pydoglog ←→ Coordinator ←→ Sensors / Services

AFTER:   HA Local Store (.storage/doglog) ←→ Coordinator ←→ Sensors / Services
                                ↕
                      Config Flow (dog setup)
                      Service Calls (event CRUD)
```

- **iot_class** changes from `cloud_polling` to `local_push` (data is local, updates are immediate on service call)
- **No external requirements** — remove `pydoglog` from manifest.json and pyproject.toml

## Data Model (stored in `.storage/doglog`)

HA's `Store` helper (`homeassistant.helpers.storage.Store`) provides JSON persistence with atomic writes.

```json
{
  "version": 1,
  "data": {
    "dogs": {
      "<dog_id>": {
        "name": "Sharky",
        "breed": "",
        "birth_date": ""
      }
    },
    "events": [
      {
        "id": "uuid4",
        "dog_id": "<dog_id>",
        "event_type": "weight",
        "timestamp": "2026-03-18T10:30:00-04:00",
        "note": "After breakfast",
        "value": 65.2
      }
    ]
  }
}
```

### Event Types (kept from current)

Core set focused on user's needs:
- **food**, **treat**, **water** — nutrition
- **walk**, **pee**, **poop** — activity/toilet
- **medicine** — with note for medicine name, track over time
- **weight** — with value (lbs), track over time
- **vaccine** — with note for vaccine name
- **sleep**, **grooming**, **training**, **teeth_brushing** — care

### Event Retention

Keep all weight and medicine events indefinitely (they're the time-series the user cares about). For high-frequency events (food, pee, poop, walk, etc.), keep 90 days by default and prune on coordinator reload. This keeps the JSON store small.

## Implementation Steps

### Step 1: New storage layer — `store.py`

Create `custom_components/doglog/store.py`:
- Class `DogLogStore` wrapping `homeassistant.helpers.storage.Store`
- Methods:
  - `async load()` — load or initialize empty store
  - `async save()` — persist to disk
  - `async add_dog(name, breed?, birth_date?)` → dog_id
  - `async remove_dog(dog_id)`
  - `async add_event(dog_id, event_type, note?, value?)` → event
  - `async delete_event(event_id)`
  - `get_events(dog_id, event_type?, since?)` → list of events (in-memory filter)
  - `get_dogs()` → dict of dogs
  - `async prune_old_events()` — remove non-weight/medicine events older than 90 days

### Step 2: Rewrite config flow — `config_flow.py`

Replace Firebase token auth with simple dog setup:
1. Step 1: "Add a dog" — fields: name (required), breed (optional), birth_date (optional)
2. Config entry title: "DogLog" (single entry, multiple dogs managed via services)
3. No authentication needed — all data is local
4. Options flow: allow adding/removing dogs after initial setup

### Step 3: Rewrite coordinator — `coordinator.py`

- No more polling — data is local
- `DogLogCoordinator` reads from `DogLogStore` on refresh
- `async_request_refresh()` called after every service call that mutates data
- Coordinator data shape stays the same: `{dog_name: [events]}` so sensors don't need major changes

### Step 4: Update sensors — `sensor.py`

Minimal changes needed since coordinator data shape is preserved:
- Update imports (remove pydoglog model references)
- Use plain dicts instead of pydoglog `DogEvent` objects
- Keep all existing sensor types:
  - Most-recent event sensors (timestamp + note attribute)
  - Daily count sensors (food, treat, walk, pee, poop, water)
  - Weight sensor (latest value)
- Add new sensor: **days since last medicine** — useful for reminders

### Step 5: Expand services — `__init__.py` + `services.yaml`

Replace `doglog.log_event` and add dog management:

| Service | Fields | Description |
|---------|--------|-------------|
| `doglog.log_event` | dog, event_type, note?, value? | Log an event (same as today) |
| `doglog.delete_event` | event_id | Delete an event by ID |
| `doglog.add_dog` | name, breed?, birth_date? | Add a new dog |
| `doglog.remove_dog` | dog | Remove a dog and all its events |
| `doglog.list_events` | dog, event_type?, days? | Fire an event with results (for automations) |

### Step 6: Update manifest and packaging

- `manifest.json`: remove `requirements`, change `iot_class` to `local_push`
- `pyproject.toml`: remove `pydoglog` dependency
- `hacs.json`: no changes needed
- Update `strings.json` and `translations/en.json` for new config flow

### Step 7: Update tests

- Remove pydoglog mocks
- Test `DogLogStore` CRUD operations
- Test sensor computation from local store data
- Test service call handlers
- Keep existing utility function tests (they're pure functions)

### Step 8: Update documentation

- `DESIGN.md`: new architecture diagram, updated config flow, storage details
- `AUTOMATIONS.md`: update examples (they should mostly work as-is since sensor names don't change)
- `README.md`: simplified setup (no Firebase token needed)
- `AGENTS.md`: remove pydoglog references

## Dashboard (for entering events)

Not part of the integration code, but document how users create a dashboard:
- Use **Mushroom cards** or **button cards** to call `doglog.log_event`
- Example: buttons for "Fed", "Walk", "Pee", "Poop", "Medicine"
- Weight entry: input_number helper → automation calls `doglog.log_event` with value
- History cards: use HA's built-in history/statistics for weight and medicine sensors

## Migration Path

For users coming from the Firebase-backed version:
- No automatic migration (the Firebase data stays in Firebase)
- Document that this is a fresh start — enter current weight, start logging
- Could add a one-time import service later if needed

## What We're NOT Building

- Custom Lovelace cards (use standard HA cards)
- User authentication (local only)
- Multi-user sync (single HA instance)
- Photo attachments
- Firebase connectivity

## File Changes Summary

| File | Action |
|------|--------|
| `store.py` | **NEW** — local JSON storage |
| `__init__.py` | **REWRITE** — new services, no Firebase auth |
| `config_flow.py` | **REWRITE** — simple dog setup, no token |
| `coordinator.py` | **REWRITE** — read from local store |
| `sensor.py` | **MODIFY** — use dicts instead of pydoglog models, add medicine sensor |
| `services.yaml` | **MODIFY** — add new services |
| `manifest.json` | **MODIFY** — remove requirements, change iot_class |
| `strings.json` | **MODIFY** — new config flow strings |
| `translations/en.json` | **MODIFY** — new translations |
| `pyproject.toml` | **MODIFY** — remove pydoglog dep |
| `tests/*` | **REWRITE** — new tests for local store |
| `docs/*` | **UPDATE** — reflect new architecture |
