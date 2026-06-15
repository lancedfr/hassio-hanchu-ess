"""Config flow for Hanchu."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_NAME
from homeassistant.core import callback

from .const import (
    CONF_ACCOUNT,
    CONF_DATA_POLL_SECONDS,
    CONF_POWER_POLL_SECONDS,
    CONF_PWD,
    CONF_SN,
    DATA_POLL_SECONDS,
    DEFAULT_NAME,
    DOMAIN,
    POWER_POLL_SECONDS,
)


class HanchuConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Hanchu."""

    VERSION = 1
    MINOR_VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> HanchuOptionsFlowHandler:
        """Return the options flow handler."""
        return HanchuOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input: dict | None = None) -> ConfigFlowResult:
        """Handle the initial step."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        errors: dict[str, str] = {}

        if user_input is not None:
            if not user_input.get(CONF_ACCOUNT, "").strip():
                errors[CONF_ACCOUNT] = "account_required"
            if not user_input.get(CONF_PWD, ""):
                errors[CONF_PWD] = "pwd_required"
            if not user_input.get(CONF_SN, "").strip():
                errors[CONF_SN] = "sn_required"

            if not errors:
                name = user_input.get(CONF_NAME) or DEFAULT_NAME
                return self.async_create_entry(
                    title=name,
                    data={
                        CONF_NAME: name,
                        CONF_ACCOUNT: user_input[CONF_ACCOUNT].strip(),
                        CONF_PWD: user_input[CONF_PWD],
                        CONF_SN: user_input[CONF_SN].strip(),
                        CONF_DATA_POLL_SECONDS: user_input.get(CONF_DATA_POLL_SECONDS, DATA_POLL_SECONDS),
                        CONF_POWER_POLL_SECONDS: user_input.get(CONF_POWER_POLL_SECONDS, POWER_POLL_SECONDS),
                    },
                )

        data_schema = vol.Schema(
            {
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Required(CONF_ACCOUNT): str,
                vol.Required(CONF_PWD): str,
                vol.Required(CONF_SN): str,
                vol.Optional(CONF_DATA_POLL_SECONDS, default=DATA_POLL_SECONDS): vol.All(int, vol.Range(min=60)),
                vol.Optional(CONF_POWER_POLL_SECONDS, default=POWER_POLL_SECONDS): vol.All(int, vol.Range(min=30)),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Handle re-authentication when credentials are rejected by the API."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict | None = None) -> ConfigFlowResult:
        """Handle re-authentication confirmation."""
        reauth_entry = self._get_reauth_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            if not user_input.get(CONF_ACCOUNT, "").strip():
                errors[CONF_ACCOUNT] = "account_required"
            if not user_input.get(CONF_PWD, ""):
                errors[CONF_PWD] = "pwd_required"
            if not user_input.get(CONF_SN, "").strip():
                errors[CONF_SN] = "sn_required"

            if not errors:
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data_updates={
                        CONF_ACCOUNT: user_input[CONF_ACCOUNT].strip(),
                        CONF_PWD: user_input[CONF_PWD],
                        CONF_SN: user_input[CONF_SN].strip(),
                    },
                )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_ACCOUNT, default=reauth_entry.data.get(CONF_ACCOUNT, "")): str,
                vol.Required(CONF_PWD): str,
                vol.Required(CONF_SN, default=reauth_entry.data.get(CONF_SN, "")): str,
            }
        )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=data_schema,
            errors=errors,
        )


class HanchuOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Hanchu options (poll intervals)."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(self, user_input: dict | None = None) -> ConfigFlowResult:
        """Manage the poll interval options."""
        errors: dict[str, str] = {}

        current_data = self._entry.data
        current_options = self._entry.options

        current_data_poll = (
            current_options.get(CONF_DATA_POLL_SECONDS)
            or current_data.get(CONF_DATA_POLL_SECONDS)
            or DATA_POLL_SECONDS
        )
        current_power_poll = (
            current_options.get(CONF_POWER_POLL_SECONDS)
            or current_data.get(CONF_POWER_POLL_SECONDS)
            or POWER_POLL_SECONDS
        )

        if user_input is not None:
            data_poll = user_input.get(CONF_DATA_POLL_SECONDS, current_data_poll)
            power_poll = user_input.get(CONF_POWER_POLL_SECONDS, current_power_poll)
            if data_poll < 60:
                errors[CONF_DATA_POLL_SECONDS] = "poll_too_short"
            if power_poll < 30:
                errors[CONF_POWER_POLL_SECONDS] = "poll_too_short"
            if not errors:
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_DATA_POLL_SECONDS: data_poll,
                        CONF_POWER_POLL_SECONDS: power_poll,
                    },
                )

        data_schema = vol.Schema(
            {
                vol.Optional(CONF_DATA_POLL_SECONDS, default=current_data_poll): vol.All(int, vol.Range(min=60)),
                vol.Optional(CONF_POWER_POLL_SECONDS, default=current_power_poll): vol.All(int, vol.Range(min=30)),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=data_schema,
            errors=errors,
        )
