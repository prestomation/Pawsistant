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
import re
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback

from .const import CONF_SPECIES, DEFAULT_SPECIES, DOMAIN, CONF_EVENT_TYPES, CONF_BUTTON_METRICS, DEFAULT_EVENT_TYPES, DEFAULT_BUTTON_METRICS

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
ACTION_EDIT_EVENT_TYPES = "edit_event_types"

# Allowed button metric values
VALID_BUTTON_METRICS = ["daily_count", "days_since", "last_value", "hours_since"]

# MDI icon validation pattern
MDI_ICON_RE = re.compile(r"^(mdi|hass):")

# Human-readable labels for button metrics
METRIC_LABELS = {
    "daily_count": "shows daily count",
    "days_since": "shows days since",
    "last_value": "shows last value",
    "hours_since": "shows hours since",
}


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
            if action == ACTION_EDIT_EVENT_TYPES:
                return await self.async_step_manage_event_types()
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
            ACTION_EDIT_EVENT_TYPES: "Edit event types",
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

    # ------------------------------------------------------------------
    # Step 4: manage_event_types — list all event types
    # ------------------------------------------------------------------

    async def async_step_manage_event_types(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """List all event types with Edit/Delete/Add actions."""
        store, _ = self._get_store_and_coord()
        if store is None:
            return self.async_create_entry(title="", data={})

        event_types = store.get_event_types()
        button_metrics = store.get_button_metrics()

        if user_input is not None:
            action = user_input.get("action", "")
            if action == "add":
                return await self.async_step_edit_event_type(user_input={})
            if action == "done":
                return self.async_create_entry(title="", data={})
            if action.startswith("edit_"):
                key = action[5:]
                return await self.async_step_edit_event_type(
                    user_input={"event_type": key}
                )
            if action.startswith("delete_"):
                key = action[7:]
                # Cannot delete built-in types
                if key in DEFAULT_EVENT_TYPES:
                    errors = await self._validate_manage_event_types(store, button_metrics)
                    errors["base"] = "cannot_delete_default"
                    return self.async_show_form(
                        step_id="manage_event_types",
                        data_schema=self._build_manage_event_types_schema(
                            event_types, button_metrics
                        ),
                        errors=errors,
                    )
                # Perform deletion
                current = store.get_event_types()
                del current[key]
                store.save_event_types(current)
                bm = store.get_button_metrics()
                if key in bm and key not in DEFAULT_BUTTON_METRICS:
                    del bm[key]
                    store.save_button_metrics(bm)
                store.sync_save_meta()
                return await self.async_step_manage_event_types()

        return self.async_show_form(
            step_id="manage_event_types",
            data_schema=self._build_manage_event_types_schema(
                event_types, button_metrics
            ),
            description_placeholders={"count": str(len(event_types))},
        )

    async def _validate_manage_event_types(self, store, button_metrics):
        """Re-validate — currently no per-field errors for manage step."""
        return {}

    def _build_manage_event_types_schema(
        self,
        event_types: dict[str, dict[str, str]],
        button_metrics: dict[str, str],
    ) -> vol.Schema:
        """Build the selector schema for manage_event_types."""
        # Build action options dict
        actions = {}
        for key in sorted(event_types.keys()):
            meta = event_types[key]
            metric = button_metrics.get(key, "daily_count")
            metric_label = METRIC_LABELS.get(metric, metric)
            label = (
                f"{meta.get('icon', 'mdi:help')} {meta.get('name', key)} "
                f"(#{meta.get('color', '?')}) — {metric_label}"
            )
            actions[f"edit_{key}"] = f"Edit {label}"
            if key not in DEFAULT_EVENT_TYPES:
                actions[f"delete_{key}"] = f"Delete {label}"
        actions["add"] = "+ Add new event type"
        actions["done"] = "Done"

        return vol.Schema({vol.Required("action", default="done"): vol.In(actions)})

    # ------------------------------------------------------------------
    # Step 5: edit_event_type — add or edit a single event type
    # ------------------------------------------------------------------

    async def async_step_edit_event_type(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add or edit a single event type.

        user_input carries "event_type" key when editing existing type.
        When adding, "event_type" is absent or empty.
        """
        store, _ = self._get_store_and_coord()
        if store is None:
            return self.async_create_entry(title="", data={})

        existing_key = (
            user_input.get("event_type", "") if user_input else ""
        )
        is_edit = bool(existing_key) and existing_key in store.get_event_types()
        errors: dict[str, str] = {}

        if user_input is not None:
            key = (
                user_input.get("event_type_key") or existing_key
            ).strip()
            name = (user_input.get("name", "")).strip()
            icon = (user_input.get("icon", "")).strip()
            color = (user_input.get("color", "")).strip()
            metric = user_input.get("metric", "daily_count")

            # Validate key
            if not key:
                errors["event_type_key"] = "required"
            elif len(key) > 30:
                errors["event_type_key"] = "key_too_long"
            elif not re.match(r"^[a-z0-9_]+$", key):
                errors["event_type_key"] = "invalid_key_format"
            else:
                # Duplicate check
                if not is_edit or (is_edit and key != existing_key):
                    if key in store.get_event_types():
                        errors["event_type_key"] = "key_already_exists"

            # Validate name
            if not name:
                errors["name"] = "required"

            # Validate icon
            if not icon:
                errors["icon"] = "required"
            elif not MDI_ICON_RE.match(icon):
                errors["icon"] = "invalid_icon_format"

            # Validate color
            if not color:
                errors["color"] = "required"
            elif not re.match(r"^#[0-9a-fA-F]{6}$", color):
                errors["color"] = "invalid_color_format"

            # Validate metric
            if metric not in VALID_BUTTON_METRICS:
                errors["metric"] = "invalid_metric"

            if not errors:
                # Persist event type entry
                entry = {
                    "name": name,
                    "icon": icon,
                    "color": color.upper(),
                }
                all_types = store.get_event_types()
                all_types[key] = entry
                store.save_event_types(all_types)

                # Persist button metric if non-default
                bm = store.get_button_metrics()
                default_metric = DEFAULT_BUTTON_METRICS.get(key, "daily_count")
                if metric != default_metric:
                    bm[key] = metric
                    store.save_button_metrics(bm)
                elif key in bm and key not in DEFAULT_BUTTON_METRICS:
                    del bm[key]
                    store.save_button_metrics(bm)

                store.sync_save_meta()

                if is_edit:
                    _, coord = self._get_store_and_coord()
                    if coord is not None:
                        await coord.async_refresh()

                return self.async_create_entry(title="", data={})

        # Build form schema
        if is_edit:
            current = store.get_event_types().get(existing_key, {})
            schema_dict = {
                vol.Optional("event_type_key", default=existing_key): str,
                vol.Optional("name", default=current.get("name", "")): str,
                vol.Optional("icon", default=current.get("icon", "")): str,
                vol.Optional("color", default=current.get("color", "")): str,
                vol.Optional(
                    "metric",
                    default=store.get_button_metrics().get(existing_key, "daily_count"),
                ): vol.In({k: k for k in VALID_BUTTON_METRICS}),
            }
        else:
            schema_dict = {
                vol.Optional("event_type_key", default=""): str,
                vol.Optional("name", default=""): str,
                vol.Optional("icon", default="mdi:tag"): str,
                vol.Optional("color", default="#4CAF50"): str,
                vol.Optional(
                    "metric", default="daily_count"
                ): vol.In({k: k for k in VALID_BUTTON_METRICS}),
            }

        return self.async_show_form(
            step_id="edit_event_type",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
            description_placeholders={"mode": "edit" if is_edit else "add"},
        )
