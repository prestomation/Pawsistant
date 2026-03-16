# Changelog

## [1.0.0] - 2026-03-16

### Added
- Initial release of ha-doglog Home Assistant custom component
- Firebase Realtime Database integration via pydoglog library
- Config flow: paste refresh token to authenticate (credentials stored in HA config entry, not on disk)
- **Sensors** (per dog):
  - `sensor.<dog>_most_recent_<type>` — timestamp of most recent event (FOOD, WALK, PEE, POOP, MEDICINE, TREAT, GROOMING, TRAINING, WATER, WEIGHT, SLEEP, VACCINE)
  - `sensor.<dog>_poop_count_today` — count of poop events since local midnight
  - `sensor.<dog>_weight` — most recent weight reading
  - Daily count sensors for walks, food, treats, water, grooming, training
- **Service**: `doglog.log_event` — log any event type for any dog from HA automations
- **Automation examples** in `docs/AUTOMATIONS.md`:
  - Daily medicine reminder (6pm, triggers if >30 days since last medicine)
  - Pee alert (every 30min, triggers if >4 hours since last pee)
  - Poop alert (after 2pm, triggers if <2 poops today)
- **Device registry**: All sensors grouped under a single dog device
- **Fi collar integration**: Links DogLog device to Fi collar device in HA
- **Timezone-aware**: Daily counts reset at HA instance local midnight (not UTC)
- **Async**: Uses AsyncDogLogClient for native async HA compatibility
- **HACS compatible**: hacs.json included
