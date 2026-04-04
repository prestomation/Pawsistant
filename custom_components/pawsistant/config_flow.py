"""Config flow for Pawsistant integration.

Local dog-setup flow — no authentication required. All data is stored locally
in HA's .storage directory.

Flow:
  1. async_step_user  — Enter the first dog's name (required) plus optional
                        breed and birth_date.  Creates the config entry titled
                        "Pawsistant".
  2. Options flow     — Add or remove dogs after initial setup (multi-step).
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

from .const import CONF_SPECIES, DEFAULT_SPECIES, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("dog_name"): str,
        vol.Optional("breed", default=""): str,
        vol.Optional("birth_date", default=""): str,
        vol.Optional(CONF_SPECIES, default=DEFAULT_SPECIES): str,
    }
)

# Action constants for the init step selector
ACTION_ADD_DOG = "add_dog"
ACTION_REMOVE_DOG = "remove_dog"
ACTION_DONE = "done"


class PawsistantConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial config flow for Pawsistant.

    Only one Pawsistant config entry is allowed.  Multiple dogs are managed via
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
                await self.async_set_unique_id("pawsistant_local")
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title="Pawsistant",
                    data={
                        "initial_dog": {
                            "name": dog_name,
                            "breed": user_input.get("breed", ""),
                            "birth_date": user_input.get("birth_date", ""),
                            CONF_SPECIES: user_input.get(CONF_SPECIES, DEFAULT_SPECIES) or DEFAULT_SPECIES,
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
    def async_get_options_flow(config_entry: ConfigEntry) -> PawsistantOptionsFlow:
        """Return the options flow handler."""
        return PawsistantOptionsFlow()


class PawsistantOptionsFlow(OptionsFlow):
    """Options flow for Pawsistant.

    Multi-step flow:
      init       — Overview of current dogs + action selector
      add_dog    — Form to add a new dog
      remove_dog — Selector to remove an existing dog
    """

    def _get_store_and_coord(self):
        """Return (store, coordinator) from the config entry's runtime_data."""
        coord = getattr(self.config_entry, "runtime_data", None)
        if coord is None or not hasattr(coord, "store"):
            return None, None
        return coord.store, coord

    def _get_dogs(self) -> dict:
        """Return dogs dict from store, or empty dict on error."""
        store, _ = self._get_store_and_coord()
        if store is None:
            return {}
        try:
            return store.get_dogs() or {}
        except Exception:  # noqa: BLE001
            return {}

    # ------------------------------------------------------------------
    # Step 1: init — overview + action selector
    # ------------------------------------------------------------------

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Hub step: show dog list and route to add/remove/done."""
        dogs = self._get_dogs()

        # If no dogs exist, go straight to add_dog
        if not dogs:
            return await self.async_step_add_dog()

        if user_input is not None:
            action = user_input.get("action")
            if action == ACTION_ADD_DOG:
                return await self.async_step_add_dog()
            if action == ACTION_REMOVE_DOG:
                return await self.async_step_remove_dog()
            # ACTION_DONE or anything else — close the dialog
            return self.async_create_entry(title="", data={})

        # Build a human-readable summary of current dogs
        dog_lines = []
        for dog in dogs.values():
            line = dog.get("name", "?")
            parts = []
            if dog.get("breed"):
                parts.append(dog["breed"])
            if dog.get("birth_date"):
                parts.append(dog["birth_date"])
            if parts:
                line += f" ({', '.join(parts)})"
            dog_lines.append(line)
        dogs_summary = "\n".join(f"• {l}" for l in dog_lines)

        action_options = {
            ACTION_ADD_DOG: "Add a pet",
            ACTION_REMOVE_DOG: "Remove a pet",
            ACTION_DONE: "Done",
        }

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required("action", default=ACTION_DONE): vol.In(action_options),
                }
            ),
            description_placeholders={"current_dogs": dogs_summary},
        )

    # ------------------------------------------------------------------
    # Step 2: add_dog — form with name / breed / birth_date
    # ------------------------------------------------------------------

    async def async_step_add_dog(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle adding a new dog."""
        errors: dict[str, str] = {}

        if user_input is not None:
            dog_name = user_input.get("dog_name", "").strip()

            if not dog_name:
                errors["dog_name"] = "name_required"
            else:
                # Case-insensitive duplicate check
                dogs = self._get_dogs()
                existing_names = [d.get("name", "").lower() for d in dogs.values()]
                if dog_name.lower() in existing_names:
                    errors["dog_name"] = "name_already_exists"

            if not errors:
                store, _ = self._get_store_and_coord()
                if store is None:
                    # Store unavailable — surface as a generic error rather than
                    # silently succeeding without persisting data.
                    _LOGGER.error(
                        "Options flow: store unavailable when adding dog '%s'",
                        dog_name,
                    )
                    errors["dog_name"] = "store_unavailable"
                else:
                    try:
                        await store.add_dog(
                            name=dog_name,
                            breed=user_input.get("breed", ""),
                            birth_date=user_input.get("birth_date", ""),
                            species=user_input.get(CONF_SPECIES, DEFAULT_SPECIES) or DEFAULT_SPECIES,
                        )
                        _LOGGER.info(
                            "Options flow: added dog '%s'", dog_name
                        )
                    except ValueError as err:
                        _LOGGER.error(
                            "Options flow add_dog error: %s", err
                        )
                        errors["dog_name"] = "name_already_exists"

                if not errors:
                    # Reload integration so new sensor entities are created
                    self.hass.async_create_task(
                        self.hass.config_entries.async_reload(
                            self.config_entry.entry_id
                        )
                    )
                    return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="add_dog",
            data_schema=vol.Schema(
                {
                    vol.Required("dog_name"): str,
                    vol.Optional("breed", default=""): str,
                    vol.Optional("birth_date", default=""): str,
                    vol.Optional(CONF_SPECIES, default=DEFAULT_SPECIES): str,
                }
            ),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Step 3: remove_dog — dropdown of current dogs with warning
    # ------------------------------------------------------------------

    async def async_step_remove_dog(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle removing an existing dog."""
        dogs = self._get_dogs()

        # If somehow no dogs exist, bail back to init
        if not dogs:
            return await self.async_step_init()

        dog_name_options = {
            dog.get("name", dog_id): dog.get("name", dog_id)
            for dog_id, dog in dogs.items()
        }

        errors: dict[str, str] = {}

        if user_input is not None:
            selected_name = user_input.get("dog_name")
            store, coord = self._get_store_and_coord()

            if store is not None and selected_name:
                result = store.get_dog_by_name(selected_name)
                if result is None:
                    errors["dog_name"] = "dog_not_found"
                else:
                    dog_id, _ = result
                    await store.remove_dog(dog_id)
                    _LOGGER.info(
                        "Options flow: removed dog '%s'", selected_name
                    )
                    if coord is not None:
                        await coord.async_refresh()
                    return self.async_create_entry(title="", data={})
            else:
                errors["dog_name"] = "dog_not_found"

        if not dog_name_options:
            return await self.async_step_init()

        first_dog_name = next(iter(dog_name_options))

        return self.async_show_form(
            step_id="remove_dog",
            data_schema=vol.Schema(
                {
                    vol.Required("dog_name", default=first_dog_name): vol.In(
                        dog_name_options
                    ),
                }
            ),
            errors=errors,
        )
