# ha-doglog Sensors

## Naming Convention

All "most recent" sensors use the `most_recent` prefix (not `last`):
- `sensor.<dog>_most_recent_<event_type>`

Entity IDs are auto-generated from the device name + entity description key.

## Device

Each dog is a device. For a dog named "Sharky":
- Device name: `Sharky`
- Device identifiers: `{("doglog", "<dog_id>")}`
- Manufacturer: `DogLog`
- Model: `Pet`

---

## Most Recent Event Sensors

One sensor per event type that tracks when the event last occurred. The **state** is an ISO 8601 timestamp. Attributes carry event details.

| Entity ID | Event Type | device_class | state_class | State | Key Attributes |
|-----------|-----------|--------------|-------------|-------|----------------|
| `sensor.sharky_most_recent_food` | FOOD | `timestamp` | — | last food time | `note`, `quantity`, `quantity_unit` |
| `sensor.sharky_most_recent_treat` | TREAT | `timestamp` | — | last treat time | `note` |
| `sensor.sharky_most_recent_walk` | WALK | `timestamp` | — | last walk time | `note`, `duration_minutes` |
| `sensor.sharky_most_recent_pee` | PEE | `timestamp` | — | last pee time | `note` |
| `sensor.sharky_most_recent_poop` | POOP | `timestamp` | — | last poop time | `note`, `stool_quality` |
| `sensor.sharky_most_recent_water` | WATER | `timestamp` | — | last water time | `note`, `quantity`, `quantity_unit` |
| `sensor.sharky_most_recent_sleep` | SLEEP | `timestamp` | — | last sleep time | `note` |
| `sensor.sharky_most_recent_teeth_brushing` | TEETH_BRUSHING | `timestamp` | — | last brushing time | `note` |
| `sensor.sharky_most_recent_grooming` | GROOMING | `timestamp` | — | last grooming time | `note` |
| `sensor.sharky_most_recent_training` | TRAINING | `timestamp` | — | last training time | `note`, `duration_minutes` |
| `sensor.sharky_most_recent_medicine` | MEDICINE | `timestamp` | — | last medicine time | `note`, `medicine_unit` |
| `sensor.sharky_most_recent_vaccine` | VACCINE | `timestamp` | — | last vaccine time | `note`, `vaccine` |

### Attributes (common to all most_recent sensors)

| Attribute | Type | Description |
|-----------|------|-------------|
| `event_id` | string | Firebase event ID |
| `note` | string | User-entered note/comment |
| `created_by` | string | Email of user who logged it |
| `pet_name` | string | Dog name |

### Additional attributes (type-specific)

| Event Type | Extra Attributes |
|-----------|-----------------|
| FOOD, WATER | `quantity` (float), `quantity_unit` (string) |
| WALK, TRAINING | `duration_minutes` (float, computed from start/end time) |
| POOP | `stool_quality` (string) |
| MEDICINE | `medicine_unit` (string) |
| VACCINE | `vaccine` (string) |

---

## Daily Count Sensors

Track how many times an event has occurred today. Resets at midnight (HA timezone).

| Entity ID | Event Type | device_class | state_class | unit |
|-----------|-----------|--------------|-------------|------|
| `sensor.sharky_daily_food_count` | FOOD | — | `total_daily` | `events` |
| `sensor.sharky_daily_treat_count` | TREAT | — | `total_daily` | `events` |
| `sensor.sharky_daily_walk_count` | WALK | — | `total_daily` | `events` |
| `sensor.sharky_daily_pee_count` | PEE | — | `total_daily` | `events` |
| `sensor.sharky_daily_poop_count` | POOP | — | `total_daily` | `events` |
| `sensor.sharky_daily_water_count` | WATER | — | `total_daily` | `events` |

These cover the event types most useful for daily tracking. Less frequent events (vaccine, grooming) don't need daily counts.

---

## Measurement Sensors

Sensors for numeric measurements that track the latest recorded value.

| Entity ID | Event Type | device_class | state_class | unit | Notes |
|-----------|-----------|--------------|-------------|------|-------|
| `sensor.sharky_weight` | WEIGHT | `weight` | `measurement` | `kg` | Latest weight. Attributes include `weight_lb` for imperial. |
| `sensor.sharky_temperature` | TEMPERATURE | `temperature` | `measurement` | `°C` | Latest body temp. Attributes include `temperature_f`. |
| `sensor.sharky_blood_glucose` | BLOOD_GLUCOSE | — | `measurement` | `mg/dL` | Latest glucose reading. Attributes include `glucose_unit`. |

### Unit Handling

- **Weight**: stored in the unit the user logged it in. The `extra` dict contains both `weightKg` and `weightPound`. We use kg as the native unit and let HA's unit conversion handle display preferences.
- **Temperature**: same approach — native unit is °C, HA converts for display.
- **Blood glucose**: uses the unit from the event's `glucoseUnit` field.

---

## Sensor Implementation Notes

### SensorEntityDescription

Each sensor type is defined as a `SensorEntityDescription`:

```python
@dataclass(frozen=True)
class DogLogSensorEntityDescription(SensorEntityDescription):
    """Describes a DogLog sensor."""
    event_type: EventType | None = None
    value_fn: Callable[[dict], StateType | datetime] = None
    attr_fn: Callable[[dict], dict[str, Any]] = None
```

### Entity Unique IDs

Format: `doglog_{dog_id}_{sensor_key}`

Example: `doglog_pet_abc123_most_recent_food`

This ensures uniqueness across multiple dogs and accounts.

### Unavailable State

If no event of a given type has ever been logged, the sensor state is `None` (shown as "Unknown" in HA). This is preferred over showing a fake/default value.

### Icon Mapping

| Event Type | Icon |
|-----------|------|
| FOOD | `mdi:food-drumstick` |
| TREAT | `mdi:cookie` |
| WALK | `mdi:walk` |
| PEE | `mdi:water` |
| POOP | `mdi:emoticon-poop` |
| WATER | `mdi:cup-water` |
| SLEEP | `mdi:sleep` |
| TEETH_BRUSHING | `mdi:toothbrush` |
| GROOMING | `mdi:content-cut` |
| TRAINING | `mdi:school` |
| MEDICINE | `mdi:pill` |
| VACCINE | `mdi:needle` |
| WEIGHT | `mdi:scale` |
| TEMPERATURE | `mdi:thermometer` |
| BLOOD_GLUCOSE | `mdi:blood-bag` |
