"""Config flow for the PostNord integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import parse_tracking_input
from .const import (
    CONF_API_KEY,
    CONF_COUNTRY,
    CONF_DISPLAY_NAME,
    CONF_OWNER,
    CONF_PACKAGES,
    CONF_POSTAL_CODE,
    CONF_TRACKING_ID,
    CONF_UPDATE_INTERVAL,
    DEFAULT_COUNTRY,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MIN_UPDATE_INTERVAL_MINUTES,
    SUPPORTED_COUNTRIES,
)


class PostNordConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle initial setup: API key + optional postal code."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            postal_code = user_input.get(CONF_POSTAL_CODE, "").strip()

            if not api_key:
                errors[CONF_API_KEY] = "api_key_required"

            if not errors:
                await self.async_set_unique_id(api_key[:8])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="PostNord",
                    data={
                        CONF_API_KEY: api_key,
                        CONF_POSTAL_CODE: postal_code,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                    vol.Optional(CONF_POSTAL_CODE, default=""): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.TEXT)
                    ),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return PostNordOptionsFlow(config_entry)


class PostNordOptionsFlow(OptionsFlow):
    """Handle options: add/remove packages, change postal code, change interval."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry
        self._packages: list[dict[str, Any]] = list(
            config_entry.options.get(CONF_PACKAGES, [])
        )
        self._update_interval: int = config_entry.options.get(
            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=["add_package", "remove_package", "change_interval", "change_postal_code"],
        )

    # ------------------------------------------------------------------
    # Add packages
    # ------------------------------------------------------------------
    async def async_step_add_package(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            raw_lines = (user_input.get("tracking_inputs") or "").splitlines()
            owner = (user_input.get(CONF_OWNER) or "").strip()
            country = user_input.get(CONF_COUNTRY, DEFAULT_COUNTRY)

            tracking_ids = [
                parse_tracking_input(line)
                for line in raw_lines
                if line.strip()
            ]

            if not tracking_ids:
                errors["tracking_inputs"] = "no_tracking_ids"
            else:
                existing_ids = {p[CONF_TRACKING_ID] for p in self._packages}
                added = 0
                for tid in tracking_ids:
                    if tid and tid not in existing_ids:
                        self._packages.append(
                            {
                                CONF_TRACKING_ID: tid,
                                CONF_DISPLAY_NAME: tid,
                                CONF_OWNER: owner,
                                CONF_COUNTRY: country,
                            }
                        )
                        existing_ids.add(tid)
                        added += 1

                if added == 0:
                    errors["tracking_inputs"] = "already_configured"
                else:
                    return self.async_create_entry(
                        title="",
                        data={
                            CONF_PACKAGES: self._packages,
                            CONF_UPDATE_INTERVAL: self._update_interval,
                        },
                    )

        return self.async_show_form(
            step_id="add_package",
            data_schema=vol.Schema(
                {
                    vol.Required("tracking_inputs"): TextSelector(
                        TextSelectorConfig(
                            type=TextSelectorType.TEXT,
                            multiline=True,
                        )
                    ),
                    vol.Optional(CONF_OWNER, default=""): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.TEXT)
                    ),
                    vol.Optional(CONF_COUNTRY, default=DEFAULT_COUNTRY): SelectSelector(
                        SelectSelectorConfig(
                            options=SUPPORTED_COUNTRIES,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Remove packages
    # ------------------------------------------------------------------
    async def async_step_remove_package(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if not self._packages:
            return self.async_abort(reason="no_packages")

        if user_input is not None:
            to_remove: list[str] = user_input.get("packages_to_remove", [])
            self._packages = [
                p for p in self._packages
                if p[CONF_TRACKING_ID] not in to_remove
            ]
            return self.async_create_entry(
                title="",
                data={
                    CONF_PACKAGES: self._packages,
                    CONF_UPDATE_INTERVAL: self._update_interval,
                },
            )

        package_options = [
            {
                "value": p[CONF_TRACKING_ID],
                "label": f"{p.get(CONF_DISPLAY_NAME) or p[CONF_TRACKING_ID]} ({p[CONF_TRACKING_ID]})",
            }
            for p in self._packages
        ]

        return self.async_show_form(
            step_id="remove_package",
            data_schema=vol.Schema(
                {
                    vol.Required("packages_to_remove"): SelectSelector(
                        SelectSelectorConfig(
                            options=package_options,
                            multiple=True,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
        )

    # ------------------------------------------------------------------
    # Change poll interval
    # ------------------------------------------------------------------
    async def async_step_change_interval(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._update_interval = int(user_input[CONF_UPDATE_INTERVAL])
            return self.async_create_entry(
                title="",
                data={
                    CONF_PACKAGES: self._packages,
                    CONF_UPDATE_INTERVAL: self._update_interval,
                },
            )

        return self.async_show_form(
            step_id="change_interval",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_UPDATE_INTERVAL, default=self._update_interval
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_UPDATE_INTERVAL_MINUTES,
                            max=1440,
                            step=5,
                            mode=NumberSelectorMode.BOX,
                            unit_of_measurement="min",
                        )
                    ),
                }
            ),
        )

    # ------------------------------------------------------------------
    # Change postal code
    # ------------------------------------------------------------------
    async def async_step_change_postal_code(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            postal_code = (user_input.get(CONF_POSTAL_CODE) or "").strip()
            # Update the config entry data (postal code lives in data, not options)
            self.hass.config_entries.async_update_entry(
                self._config_entry,
                data={**self._config_entry.data, CONF_POSTAL_CODE: postal_code},
            )
            return self.async_create_entry(
                title="",
                data={
                    CONF_PACKAGES: self._packages,
                    CONF_UPDATE_INTERVAL: self._update_interval,
                },
            )

        current = self._config_entry.data.get(CONF_POSTAL_CODE, "")
        return self.async_show_form(
            step_id="change_postal_code",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_POSTAL_CODE, default=current): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.TEXT)
                    ),
                }
            ),
        )
