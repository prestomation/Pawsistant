# HACS Integration Guide

## Required Files

### `hacs.json` (repository root)

```json
{
  "name": "DogLog",
  "homeassistant": "2024.1.0",
  "render_readme": true
}
```

| Field | Value | Notes |
|-------|-------|-------|
| `name` | `"DogLog"` | **Required.** Display name in HACS. |
| `homeassistant` | `"2024.1.0"` | Minimum HA version. We use modern patterns (SensorEntityDescription, DataUpdateCoordinator) that are stable since 2024.1. |
| `render_readme` | `true` | HACS renders README.md in the integration page. |

### `custom_components/doglog/manifest.json`

```json
{
  "domain": "doglog",
  "name": "DogLog",
  "version": "0.1.0",
  "documentation": "https://github.com/<owner>/ha-doglog",
  "issue_tracker": "https://github.com/<owner>/ha-doglog/issues",
  "codeowners": ["@<owner>"],
  "config_flow": true,
  "dependencies": [],
  "iot_class": "cloud_polling",
  "requirements": ["pydoglog>=0.1.0"]
}
```

| Field | Value | Notes |
|-------|-------|-------|
| `domain` | `"doglog"` | Internal integration identifier. Must match the directory name. |
| `name` | `"DogLog"` | Display name in HA integrations list. |
| `version` | `"0.1.0"` | **Required for HACS.** Semver. |
| `documentation` | URL | Link to docs/README. |
| `issue_tracker` | URL | Link to GitHub issues. |
| `codeowners` | `["@<owner>"]` | GitHub usernames of maintainers. |
| `config_flow` | `true` | Enables UI-based setup. Requires `config_flow.py` + `strings.json`. |
| `iot_class` | `"cloud_polling"` | We poll the Firebase cloud API on an interval. |
| `requirements` | `["pydoglog>=0.1.0"]` | HA will `pip install` these automatically. |

### `custom_components/doglog/strings.json`

Required when `config_flow: true`. Contains English strings for the config flow UI and services.

```json
{
  "config": {
    "step": {
      "user": {
        "title": "Connect to DogLog",
        "description": "Enter your DogLog refresh token to connect your account.",
        "data": {
          "refresh_token": "Refresh Token"
        }
      }
    },
    "error": {
      "invalid_auth": "Invalid refresh token. Please check and try again.",
      "cannot_connect": "Could not connect to DogLog. Please try again later."
    },
    "abort": {
      "already_configured": "This DogLog account is already configured."
    }
  },
  "services": {
    "log_event": {
      "name": "Log Event",
      "description": "Log a new event to DogLog for a pet.",
      "fields": {
        "dog_id": {
          "name": "Dog",
          "description": "The dog to log the event for."
        },
        "event_type": {
          "name": "Event Type",
          "description": "The type of event to log."
        },
        "note": {
          "name": "Note",
          "description": "Optional note or comment."
        }
      }
    }
  }
}
```

### `custom_components/doglog/translations/en.json`

Copy of `strings.json`. HA uses this for localization at runtime.

---

## Repository Structure Checklist

HACS expects this layout for a custom integration:

```
repo-root/
├── hacs.json                           ✅ HACS metadata
├── custom_components/
│   └── doglog/
│       ├── __init__.py                 ✅ Integration setup
│       ├── manifest.json               ✅ HA integration metadata
│       ├── config_flow.py              ✅ UI config flow
│       ├── const.py                    ✅ Constants
│       ├── coordinator.py              ✅ DataUpdateCoordinator
│       ├── sensor.py                   ✅ Sensor platform
│       ├── services.yaml               ✅ Service definitions
│       ├── strings.json                ✅ English strings
│       └── translations/
│           └── en.json                 ✅ English translations
├── README.md                           ✅ User-facing docs
└── LICENSE                             ✅ Open source license
```

## HACS Submission Checklist

Before submitting to the HACS default repository list:

- [ ] Repository is public on GitHub
- [ ] `hacs.json` exists at repo root with `"name"` field
- [ ] `custom_components/<domain>/manifest.json` exists with valid `version` field
- [ ] `manifest.json` has `requirements`, `codeowners`, `iot_class`, `domain`, `name`
- [ ] Integration loads and works on latest HA release
- [ ] `README.md` has install instructions and usage documentation
- [ ] Repository has at least one GitHub release/tag matching `manifest.json` version
- [ ] No `example` or `test` in the integration domain name
- [ ] Repository has a description on GitHub
- [ ] Repository has topics/tags on GitHub (e.g., `home-assistant`, `hacs`, `doglog`)
- [ ] Code follows HA coding standards (ruff/pylint clean)
- [ ] `LICENSE` file exists (MIT, Apache-2.0, etc.)

### Adding as a Custom Repository (before default listing)

Users can install immediately by adding as a custom HACS repository:
1. HACS → Integrations → three-dot menu → Custom repositories
2. Enter the GitHub URL
3. Category: Integration
4. Click Add

This works without being in the HACS default list.

## Versioning

Use semantic versioning. Both `manifest.json` and GitHub releases must have matching version numbers.

- `manifest.json`: `"version": "0.1.0"`
- GitHub release tag: `v0.1.0` or `0.1.0`

HACS uses GitHub releases to detect updates and present them to users.
