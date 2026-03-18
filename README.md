# Pawsistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue.svg)](https://www.home-assistant.io/)

Home Assistant custom component for [DogLog](https://doglog.app/) — your pup's personal assistant. Exposes your dog's activity as sensors in HA so you can build automations around feeding, walks, bathroom habits, and medication.

---

## Features

- **Per-event sensors** — timestamp of the most recent event for each type (pee, poop, medicine, walk, food, treat, water, grooming, training, sleep, weight, vaccine)
- **Daily count sensors** — how many times today for walks, food, treats, water, poop, and more
- **Timezone-aware** — daily counts reset at your HA instance's local midnight, not UTC
- **Fi collar integration** — Pawsistant device links to your dog's Fi collar device in the HA device registry
- **Service** — `doglog.log_event` to record events directly from HA automations
- **HACS compatible** — install and update via HACS

---

## Installation

### Via HACS (recommended)

1. Open HACS -> **Integrations** -> three-dot menu -> **Custom repositories**
2. Add `https://github.com/prestomation/ha-doglog` with category **Integration**
3. Search for **Pawsistant** and install
4. Restart Home Assistant

### Manual

1. Copy `custom_components/doglog/` into your HA config's `custom_components/` directory
2. Restart Home Assistant

---

## Configuration

1. Go to **Settings -> Devices & Services -> Add Integration**
2. Search for **Pawsistant**
3. Paste your DogLog **refresh token** (find this in the DogLog app under Account -> Developer)
4. HA will connect, load your pack, and create sensors for each dog

Credentials are stored in the HA config entry — nothing is written to disk.

---

## Sensors

Sensors are created per dog. For a dog named `Sharky`:

| Entity | Description |
|---|---|
| `sensor.sharky_most_recent_pee` | Timestamp of last pee |
| `sensor.sharky_most_recent_poop` | Timestamp of last poop |
| `sensor.sharky_most_recent_medicine` | Timestamp of last medicine |
| `sensor.sharky_most_recent_walk` | Timestamp of last walk |
| `sensor.sharky_most_recent_food` | Timestamp of last meal |
| `sensor.sharky_poop_count_today` | Poops logged today (local time) |
| `sensor.sharky_daily_walks_count` | Walks logged today |
| `sensor.sharky_daily_food_count` | Meals logged today |
| `sensor.sharky_weight` | Most recent weight |

Timestamp sensors use `device_class: timestamp` so HA displays them in your local timezone.

---

## Dashboard Cards

Copy-paste any of these into a dashboard. Replace `sharky` with your dog's name (lowercased, spaces replaced with underscores).

### Dog Status Card

Shows today's activity counts at a glance:

```yaml
type: vertical-stack
cards:
  - type: entity
    entity: sensor.sharky_weight
    name: Sharky
    icon: mdi:dog
  - type: glance
    title: Today's Activity
    entities:
      - entity: sensor.sharky_daily_food_count
        name: Food
      - entity: sensor.sharky_daily_walks_count
        name: Walks
      - entity: sensor.sharky_daily_pee_count
        name: Pee
      - entity: sensor.sharky_poop_count_today
        name: Poop
      - entity: sensor.sharky_daily_water_count
        name: Water
```

### Last Events Card

When did they last eat, walk, poop, take medicine?

```yaml
type: entities
title: Sharky - Last Events
entities:
  - entity: sensor.sharky_most_recent_food
    name: Last Fed
  - entity: sensor.sharky_most_recent_walk
    name: Last Walk
  - entity: sensor.sharky_most_recent_poop
    name: Last Poop
  - entity: sensor.sharky_most_recent_pee
    name: Last Pee
  - entity: sensor.sharky_most_recent_medicine
    name: Last Medicine
  - entity: sensor.sharky_most_recent_vaccine
    name: Last Vaccine
```

### Quick-Log Buttons

Tap to log an event without opening the DogLog app:

```yaml
type: horizontal-stack
cards:
  - type: button
    name: Poop
    icon: mdi:emoticon-poop
    tap_action:
      action: perform-action
      perform_action: doglog.log_event
      data:
        dog: Sharky
        event_type: poop
  - type: button
    name: Pee
    icon: mdi:water
    tap_action:
      action: perform-action
      perform_action: doglog.log_event
      data:
        dog: Sharky
        event_type: pee
  - type: button
    name: Walk
    icon: mdi:walk
    tap_action:
      action: perform-action
      perform_action: doglog.log_event
      data:
        dog: Sharky
        event_type: walk
  - type: button
    name: Food
    icon: mdi:food-drumstick
    tap_action:
      action: perform-action
      perform_action: doglog.log_event
      data:
        dog: Sharky
        event_type: food
```

### Full Dog Card

Combine everything into one vertical stack:

```yaml
type: vertical-stack
cards:
  - type: entity
    entity: sensor.sharky_weight
    name: Sharky
    icon: mdi:dog
  - type: glance
    title: Today
    entities:
      - entity: sensor.sharky_daily_food_count
        name: Food
      - entity: sensor.sharky_daily_walks_count
        name: Walks
      - entity: sensor.sharky_poop_count_today
        name: Poop
      - entity: sensor.sharky_daily_water_count
        name: Water
  - type: entities
    title: Last Events
    entities:
      - entity: sensor.sharky_most_recent_food
        name: Fed
      - entity: sensor.sharky_most_recent_walk
        name: Walk
      - entity: sensor.sharky_most_recent_poop
        name: Poop
      - entity: sensor.sharky_most_recent_medicine
        name: Medicine
  - type: horizontal-stack
    cards:
      - type: button
        name: Poop
        icon: mdi:emoticon-poop
        tap_action:
          action: perform-action
          perform_action: doglog.log_event
          data:
            dog: Sharky
            event_type: poop
      - type: button
        name: Pee
        icon: mdi:water
        tap_action:
          action: perform-action
          perform_action: doglog.log_event
          data:
            dog: Sharky
            event_type: pee
      - type: button
        name: Walk
        icon: mdi:walk
        tap_action:
          action: perform-action
          perform_action: doglog.log_event
          data:
            dog: Sharky
            event_type: walk
      - type: button
        name: Food
        icon: mdi:food-drumstick
        tap_action:
          action: perform-action
          perform_action: doglog.log_event
          data:
            dog: Sharky
            event_type: food
```

---

## Automations

See [`docs/AUTOMATIONS.md`](docs/AUTOMATIONS.md) for ready-to-use YAML examples including:

- **Medicine reminder** — persistent notification at 6pm if medicine is overdue, auto-clears when logged
- **Pee alert** — persistent notification if no pee in 4+ hours, checks every 30 minutes, auto-clears when logged
- **Poop alert** — persistent notification after 2pm if fewer than 2 poops today, auto-clears when count reaches 2

All automations follow the single-automation two-trigger pattern — alert and dismiss logic live in one place.

---

## Service: `doglog.log_event`

Log an event directly from an HA automation or script:

```yaml
action: doglog.log_event
data:
  dog: Sharky
  event_type: medicine
  note: "Heartworm pill"
  value: 1
```

---

## Requirements

- Home Assistant 2024.1+
- [pydoglog](https://github.com/prestomation/pydoglog) (installed automatically)
- A DogLog account with at least one pack and dog

---

## Contributing

Issues and PRs welcome at [github.com/prestomation/ha-doglog](https://github.com/prestomation/ha-doglog).
