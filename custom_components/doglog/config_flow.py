"""Config flow for DogLog integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from pydoglog import DogLogClient
from pydoglog.auth import refresh_id_token

DOMAIN = "doglog"
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
                token_data = await self.hass.async_add_executor_job(
                    refresh_id_token, refresh_token
                )
            except Exception:
                errors["base"] = "invalid_auth"
            else:
                uid = token_data.get("user_id", token_data.get("uid", ""))
                email = token_data.get("email", "")
                id_token = token_data["id_token"]

                # Validate we can access the API
                try:
                    client = DogLogClient(
                        id_token=id_token,
                        refresh_token=refresh_token,
                        uid=uid,
                    )
                    packs = await self.hass.async_add_executor_job(client.get_packs)
                    if not packs:
                        errors["base"] = "no_packs"
                except Exception:
                    errors["base"] = "cannot_connect"

                if not errors:
                    await self.async_set_unique_id(uid)
                    self._abort_if_unique_id_configured()

                    return self.async_create_entry(
                        title=f"DogLog ({email})",
                        data={
                            "refresh_token": refresh_token,
                            "uid": uid,
                            "email": email,
                        },
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle reauth when token is invalid."""
        return await self.async_step_user()
