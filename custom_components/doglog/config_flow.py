"""Config flow for DogLog integration.

Replaces the Firebase-token-based flow with a simple local dog-setup flow.
No authentication is required — all data is stored locally in HA's .storage
directory.

Flow:
  1. async_step_user  — Enter the first dog's name (required) plus optional
                        breed and birth_date.  Creates the config entry titled
                        "DogLog".
  2. Options flow     — Add or remove dogs after initial setup.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("dog_name"): str,
        vol.Optional("breed", default=""): str,
        vol.Optional("birth_date", default=""): str,
    }
)


class DogLogConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial config flow for DogLog.

    Only one DogLog config entry is allowed.  Multiple dogs are managed via
    the add_dog / remove_dog services (or the options flow).
    """

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step: enter a dog's name."""
        errors: dict[str, str] = {}

        if user_input is not None:
            dog_name = user_input["dog_name"].strip()
            if not dog_name:
                errors["dog_name"] = "name_required"
            else:
                # Prevent duplicate config entries
                await self.async_set_unique_id("doglog_local")
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title="DogLog",
                    data={
                        "initial_dog": {
                            "name": dog_name,
                            "breed": user_input.get("breed", ""),
                            "birth_date": user_input.get("birth_date", ""),
                        }
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> DogLogOptionsFlow:
        """Return the options flow handler."""
        return DogLogOptionsFlow()


class DogLogOptionsFlow(OptionsFlow):
    """Options flow for DogLog.

    Shows currently registered dogs and instructions for managing them.
    Actual dog CRUD is performed via service calls (add_dog / remove_dog).
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the options form with current dogs list."""
        if user_input is not None:
            return self.async_create_entry(title="", data={})

        # Get current dogs from the coordinator if available
        dogs_info = ""
        try:
            coord = getattr(self.config_entry, "runtime_data", None)
            if coord is not None and hasattr(coord, "store"):
                dogs = coord.store.get_dogs()
                if dogs:
                    dog_names = [d["name"] for d in dogs.values()]
                    dogs_info = ", ".join(dog_names)
                else:
                    dogs_info = "No dogs registered yet"
        except Exception:  # noqa: BLE001
            dogs_info = "Unable to load dogs"

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({}),
            description_placeholders={
                "current_dogs": dogs_info,
                "manage_dogs_tip": (
                    "Use the doglog.add_dog and doglog.remove_dog services "
                    "to manage your dogs."
                ),
            },
        )
