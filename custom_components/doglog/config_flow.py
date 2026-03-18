"""Config flow for Pawsistant (DogLog) integration."""

from __future__ import annotations

import base64
import json
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


def _decode_jwt_payload(token: str) -> dict:
    """Decode the payload segment of a JWT without verification."""
    payload_b64 = token.split(".")[1]
    # Add padding if needed
    padding = 4 - len(payload_b64) % 4
    if padding != 4:
        payload_b64 += "=" * padding
    return json.loads(base64.urlsafe_b64decode(payload_b64))


class DogLogConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Pawsistant."""

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
                id_token = token_data["id_token"]

                # Decode JWT to extract uid and email
                try:
                    claims = _decode_jwt_payload(id_token)
                except Exception:
                    errors["base"] = "invalid_auth"
                    claims = {}

                uid = claims.get("user_id", claims.get("sub", ""))
                email = claims.get("email", "")

                if not errors:
                    # Validate we can access the API
                    try:
                        client = DogLogClient(
                            id_token=id_token,
                            refresh_token=refresh_token,
                            uid=uid,
                        )
                        packs = await self.hass.async_add_executor_job(
                            client.get_packs
                        )
                        if not packs:
                            errors["base"] = "no_packs"
                    except Exception:
                        errors["base"] = "cannot_connect"

                if not errors:
                    await self.async_set_unique_id(uid)
                    self._abort_if_unique_id_configured()

                    return self.async_create_entry(
                        title=f"Pawsistant ({email})",
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
