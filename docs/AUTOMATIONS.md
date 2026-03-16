# DogLog HA Automations

Ready-to-paste Home Assistant automation YAML for DogLog sensors. Add these to your `automations.yaml` or via the HA UI.

## 1. Daily Medicine Reminder (6pm)

Sends a notification if Sharky hasn't had medicine in over 30 days.

```yaml
alias: DogLog - Daily Medicine Reminder
trigger:
  - platform: time
    at: '18:00:00'
condition:
  - condition: template
    value_template: >
      {% set last = states('sensor.sharky_most_recent_medicine') %}
      {% if last in ['unknown', 'unavailable'] %}
        true
      {% else %}
        {{ (now() - as_datetime(last)).days > 30 }}
      {% endif %}
action:
  - service: notify.mobile_app_prestons_phone
    data:
      title: 'DogLog Reminder'
      message: "Sharky hasn't had medicine in over 30 days!"
  - service: notify.mobile_app_tess_phone
    data:
      title: 'DogLog Reminder'
      message: "Sharky hasn't had medicine in over 30 days!"
```

## 2. Pee Alert (>4 hours)

Checks every 30 minutes if Sharky hasn't peed in over 4 hours.

```yaml
alias: DogLog - Sharky Pee Alert
trigger:
  - platform: time_pattern
    minutes: '/30'
condition:
  - condition: template
    value_template: >
      {% set last = states('sensor.sharky_most_recent_pee') %}
      {% if last in ['unknown', 'unavailable'] %}
        false
      {% else %}
        {{ (now() - as_datetime(last)).total_seconds() > 14400 }}
      {% endif %}
action:
  - service: notify.mobile_app_prestons_phone
    data:
      title: 'DogLog Alert'
      message: "Sharky hasn't peed in over 4 hours!"
  - service: notify.mobile_app_tess_phone
    data:
      title: 'DogLog Alert'
      message: "Sharky hasn't peed in over 4 hours!"
```

## 3. Poop Alert (after 2pm, <2 poops today)

Checks every 30 minutes after 2pm if Sharky has pooped fewer than 2 times today.

```yaml
alias: DogLog - Sharky Poop Alert
trigger:
  - platform: time_pattern
    minutes: '/30'
condition:
  - condition: time
    after: '14:00:00'
  - condition: template
    value_template: >
      {{ states('sensor.sharky_poop_count_today') | int(0) < 2 }}
action:
  - service: notify.mobile_app_prestons_phone
    data:
      title: 'DogLog Alert'
      message: "Sharky has only pooped {{ states('sensor.sharky_poop_count_today') }} time(s) today!"
  - service: notify.mobile_app_tess_phone
    data:
      title: 'DogLog Alert'
      message: "Sharky has only pooped {{ states('sensor.sharky_poop_count_today') }} time(s) today!"
```
