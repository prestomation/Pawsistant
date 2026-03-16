# Config Flow

## Overview

The DogLog integration uses a UI-based config flow where the user pastes their DogLog refresh token. No OAuth browser redirect is needed — the refresh token is obtained externally (from the DogLog app/CLI) and entered directly.

## User-Facing Steps

### Step 1: Add Integration

1. User navigates to **Settings → Devices & Services → Add Integration**
2. Searches for "DogLog"
3. Clicks to add

### Step 2: Enter Refresh Token

A form appears with a single field:

| Field | Type | Label | Description |
|-------|------|-------|-------------|
| `refresh_token` | text (password) | Refresh Token | Your DogLog refresh token |

The user pastes their refresh token. This can be obtained by:
- Running `doglog login-google` or `doglog login` via the `pydoglog` CLI
- Copying from `~/.doglog/config.json` on a machine where they've logged in
- Using the token-dumper companion app

### Step 3: Validation (automatic)

On submit, the config flow:

1. Calls `pydoglog.auth.refresh_id_token(refresh_token)` to exchange the refresh token for a valid ID token
2. If this fails → show `invalid_auth` error, stay on the form
3. Creates a `DogLogClient` with the obtained credentials
4. Calls `client.get_packs()` to fetch all accessible packs
5. Calls `client.get_dogs()` for each pack to discover all dogs
6. If API calls fail → show `cannot_connect` error

### Step 4: Success

A config entry is created with:

```python
{
    "title": "DogLog (<user_email>)",
    "data": {
        "refresh_token": "<refresh_token>",
        "email": "<user_email>",
        "uid": "<firebase_uid>",
    }
}
```

The integration sets up immediately. Dogs appear as devices, sensors populate on first data fetch.

## Implementation

### `config_flow.py`

```python
"""Config flow for DogLog integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_TOKEN

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("refresh_token"): str,
    }
)


class DogLogConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for DogLog."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            refresh_token = user_input["refresh_token"]

            try:
                # Validate the refresh token
                creds = await self.hass.async_add_executor_job(
                    self._validate_token, refresh_token
                )
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                # Check if already configured for this account
                await self.async_set_unique_id(creds["uid"])
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"DogLog ({creds['email']})",
                    data={
                        "refresh_token": refresh_token,
                        "email": creds["email"],
                        "uid": creds["uid"],
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    def _validate_token(self, refresh_token: str) -> dict:
        """Validate refresh token and return credentials."""
        from pydoglog.auth import refresh_id_token
        from pydoglog import DogLogClient, DogLogAuthError, DogLogAPIError

        try:
            result = refresh_id_token(refresh_token)
        except Exception as err:
            _LOGGER.error("Failed to refresh token: %s", err)
            raise InvalidAuth from err

        try:
            client = DogLogClient(
                id_token=result["id_token"],
                refresh_token=refresh_token,
                uid=result.get("uid", ""),
                email=result.get("email", ""),
            )
            # Verify we can actually fetch data
            client.get_packs()
        except DogLogAuthError as err:
            raise InvalidAuth from err
        except (DogLogAPIError, Exception) as err:
            raise CannotConnect from err

        return {
            "uid": result.get("uid", client.uid),
            "email": result.get("email", client.email),
        }

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle reauthentication."""
        return await self.async_step_user()


class InvalidAuth(Exception):
    """Error to indicate invalid authentication."""


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""
```

### Reauthentication Flow

When the coordinator detects a permanent auth failure, it raises `ConfigEntryAuthFailed`. HA then:

1. Marks the integration as needing reauthentication
2. Shows a "Reauthenticate" button in the UI
3. User clicks it → `async_step_reauth` is called
4. User enters a new/refreshed token
5. Config entry is updated, integration reloads

### How to Obtain a Refresh Token

Users need to get their refresh token once. Methods:

1. **pydoglog CLI** (recommended):
   ```bash
   pip install pydoglog
   doglog login-google   # opens browser, saves token
   cat ~/.doglog/config.json | jq .refresh_token
   ```

2. **Token Dumper app**: Install the companion APK on Android, sign in with Google, copy the displayed refresh token.

3. **Manual**: Sign into Google with the DogLog app's OAuth client ID and extract the refresh token from the response.

We will document method 1 as the primary approach in the README.
