# ha-doglog Services

## `doglog.log_event`

Log a new event to DogLog for a specific dog.

### Service Definition (`services.yaml`)

```yaml
log_event:
  name: Log Event
  description: Log a new event to DogLog for a pet.
  fields:
    dog_id:
      name: Dog
      description: The dog to log the event for.
      required: true
      selector:
        device:
          integration: doglog
    event_type:
      name: Event Type
      description: The type of event to log.
      required: true
      selector:
        select:
          options:
            - label: Food
              value: food
            - label: Treat
              value: treat
            - label: Walk
              value: walk
            - label: Pee
              value: pee
            - label: Poop
              value: poop
            - label: Water
              value: water
            - label: Sleep
              value: sleep
            - label: Teeth Brushing
              value: teeth_brushing
            - label: Grooming
              value: grooming
            - label: Training
              value: training
            - label: Medicine
              value: medicine
            - label: Vaccine
              value: vaccine
            - label: Weight
              value: weight
            - label: Temperature
              value: temperature
            - label: Blood Glucose
              value: blood_glucose
    note:
      name: Note
      description: Optional note or comment for the event.
      required: false
      selector:
        text:
    weight_kg:
      name: Weight (kg)
      description: Weight in kilograms (for weight events).
      required: false
      selector:
        number:
          min: 0
          max: 200
          step: 0.1
          unit_of_measurement: kg
    temperature_celsius:
      name: Temperature (°C)
      description: Body temperature in Celsius (for temperature events).
      required: false
      selector:
        number:
          min: 30
          max: 45
          step: 0.1
          unit_of_measurement: °C
    glucose:
      name: Blood Glucose
      description: Blood glucose reading (for blood glucose events).
      required: false
      selector:
        number:
          min: 0
          max: 1000
          step: 1
    glucose_unit:
      name: Glucose Unit
      description: Unit for blood glucose reading.
      required: false
      default: "mg/dL"
      selector:
        select:
          options:
            - "mg/dL"
            - "mmol/L"
    quantity:
      name: Quantity
      description: Amount (for food/water events).
      required: false
      selector:
        number:
          min: 0
          max: 100
          step: 0.1
    quantity_unit:
      name: Quantity Unit
      description: Unit for quantity (cups, grams, ml, etc.).
      required: false
      selector:
        text:
```

### Python Registration

In `__init__.py`:

```python
async def async_setup_entry(hass, entry):
    # ... coordinator setup ...

    async def async_log_event(call):
        """Handle the doglog.log_event service call."""
        dog_device_id = call.data["dog_id"]
        event_type = call.data["event_type"]
        note = call.data.get("note", "")

        # Resolve device_id → (pack_id, dog_id, dog_name)
        device_registry = dr.async_get(hass)
        device = device_registry.async_get(dog_device_id)
        dog_id = next(
            identifier[1]
            for identifier in device.identifiers
            if identifier[0] == DOMAIN
        )

        # Look up pack_id from coordinator data
        coordinator = hass.data[DOMAIN][entry.entry_id]
        pack_id = coordinator.data["dogs"][dog_id].pack_id
        dog_name = coordinator.data["dogs"][dog_id].name

        # Build extra kwargs based on event type
        kwargs = {}
        if weight_kg := call.data.get("weight_kg"):
            kwargs["weightKg"] = weight_kg
            kwargs["weightPound"] = round(weight_kg * 2.20462, 1)
            kwargs["weightMeasure"] = "Kilograms"
        if temp_c := call.data.get("temperature_celsius"):
            kwargs["temperatureCelsius"] = temp_c
            kwargs["temperatureFahrenheit"] = round(temp_c * 9/5 + 32, 1)
            kwargs["temperatureMeasure"] = "Celsius"
        if glucose := call.data.get("glucose"):
            kwargs["glucose"] = glucose
            kwargs["glucoseUnit"] = call.data.get("glucose_unit", "mg/dL")
        if quantity := call.data.get("quantity"):
            kwargs["quantity"] = quantity
            kwargs["quantityUnit"] = call.data.get("quantity_unit", "")

        await hass.async_add_executor_job(
            coordinator.client.create_event,
            pack_id, dog_id, event_type, note, dog_name,
            **kwargs,
        )

        # Trigger an immediate data refresh
        await coordinator.async_request_refresh()

    hass.services.async_register(DOMAIN, "log_event", async_log_event)
```

### Automation Examples

#### Log a walk when leaving home

```yaml
automation:
  - alias: "Log walk when leaving home"
    trigger:
      - platform: zone
        entity_id: person.owner
        zone: zone.home
        event: leave
    action:
      - service: doglog.log_event
        data:
          dog_id: <sharky_device_id>
          event_type: walk
          note: "Walk from home"
```

#### Log food at scheduled times

```yaml
automation:
  - alias: "Log Sharky's morning food"
    trigger:
      - platform: time
        at: "07:30:00"
    action:
      - service: doglog.log_event
        data:
          dog_id: <sharky_device_id>
          event_type: food
          quantity: 1.5
          quantity_unit: cups
          note: "Morning kibble"
```

#### Log weight from a smart scale

```yaml
automation:
  - alias: "Log Sharky's weight from scale"
    trigger:
      - platform: state
        entity_id: sensor.pet_scale_weight
    action:
      - service: doglog.log_event
        data:
          dog_id: <sharky_device_id>
          event_type: weight
          weight_kg: "{{ states('sensor.pet_scale_weight') | float }}"
          note: "Auto-logged from smart scale"
```

#### Alert if no pee in 12 hours

```yaml
automation:
  - alias: "Alert if Sharky hasn't peed in 12h"
    trigger:
      - platform: template
        value_template: >
          {{ (now() - states.sensor.sharky_most_recent_pee.state | as_datetime).total_seconds() > 43200 }}
    action:
      - service: notify.mobile_app
        data:
          title: "DogLog Alert"
          message: "Sharky hasn't peed in 12 hours!"
```
