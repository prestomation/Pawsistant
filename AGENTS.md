# ha-doglog

Home Assistant custom component for the [DogLog](https://doglogapp.com) pet tracking app. Exposes pet activity data as HA sensors and provides a service to log events from automations.

## Design

See [docs/DESIGN.md](docs/DESIGN.md) for architecture, sensor naming, config flow, and service details.

## Build / Dev

### Local HA development

Copy the integration into your HA config directory:

```bash
cp -r custom_components/doglog /path/to/ha-config/custom_components/
```

Then restart Home Assistant.

### Linting / Compilation check

```bash
python -m py_compile custom_components/doglog/__init__.py
python -m py_compile custom_components/doglog/config_flow.py
python -m py_compile custom_components/doglog/coordinator.py
python -m py_compile custom_components/doglog/sensor.py
```

### CI

GitHub Actions runs on push and PR. See `.github/workflows/lint.yml`.

## Notes for coding agents

- **pydoglog source**: `/root/doglog/pydoglog/src/pydoglog/` — the Python library wrapping DogLog's Firebase API
- **Do not commit real tokens** — refresh tokens and ID tokens are secrets
- The integration uses `hass.async_add_executor_job()` to call synchronous pydoglog methods from async HA context
