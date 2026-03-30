"""Config flow for OpenAI Codex Usage integration."""

from __future__ import annotations

import json
import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import aiohttp_client

from .const import (
    CODEX_USAGE_API_URL,
    WHAM_USAGE_API_URL,
    CONF_ACCESS_TOKEN,
    CONF_ACCOUNT_ID,
    CONF_REFRESH_TOKEN,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class CodexUsageConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OpenAI Codex Usage."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle setup with manual credential input."""
        errors: dict[str, str] = {}

        if user_input is not None:
            access_token = _normalize_credential_value(user_input.get(CONF_ACCESS_TOKEN, ""))
            account_id = _normalize_credential_value(user_input.get(CONF_ACCOUNT_ID, ""))
            refresh_token = _normalize_credential_value(user_input.get(CONF_REFRESH_TOKEN, ""))

            if not access_token:
                errors[CONF_ACCESS_TOKEN] = "missing_access_token"
            else:
                if await self._validate_credentials(access_token, account_id):
                    await self.async_set_unique_id(DOMAIN)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title="OpenAI Codex Usage",
                        data={
                            CONF_ACCESS_TOKEN: access_token,
                            CONF_ACCOUNT_ID: account_id,
                            CONF_REFRESH_TOKEN: refresh_token,
                        },
                        options={
                            CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                            CONF_ACCESS_TOKEN: access_token,
                            CONF_ACCOUNT_ID: account_id,
                            CONF_REFRESH_TOKEN: refresh_token,
                        },
                    )
                errors[CONF_ACCESS_TOKEN] = "invalid_access_token"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ACCESS_TOKEN): str,
                    vol.Optional(CONF_ACCOUNT_ID, default=""): str,
                    vol.Optional(CONF_REFRESH_TOKEN, default=""): str,
                }
            ),
            errors=errors,
        )

    async def _validate_credentials(self, access_token: str, account_id: str) -> bool:
        """Validate credentials by performing a codex usage request."""
        try:
            session = aiohttp_client.async_get_clientsession(self.hass)
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                **({"ChatGPT-Account-Id": account_id} if account_id else {}),
            }
            for url in (CODEX_USAGE_API_URL, WHAM_USAGE_API_URL):
                resp = await session.get(
                    url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15),
                )
                if resp.ok:
                    return True
                if resp.status in (401, 403, 404):
                    continue
                return False
            _LOGGER.warning("Codex auth validation failed on all usage endpoints")
            return False
        except aiohttp.ClientError:
            _LOGGER.exception("Codex auth validation request failed")
            return False

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Handle reauth when credentials are invalid or expired."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reauth with replacement credentials."""
        errors: dict[str, str] = {}

        if user_input is not None:
            access_token = _normalize_credential_value(user_input.get(CONF_ACCESS_TOKEN, ""))
            account_id = _normalize_credential_value(user_input.get(CONF_ACCOUNT_ID, ""))
            refresh_token = _normalize_credential_value(user_input.get(CONF_REFRESH_TOKEN, ""))
            if not access_token:
                errors[CONF_ACCESS_TOKEN] = "missing_access_token"
            elif await self._validate_credentials(access_token, account_id):
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(),
                    data_updates={
                        CONF_ACCESS_TOKEN: access_token,
                        CONF_ACCOUNT_ID: account_id,
                        CONF_REFRESH_TOKEN: refresh_token,
                    },
                )
            else:
                errors[CONF_ACCESS_TOKEN] = "invalid_access_token"

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ACCESS_TOKEN): str,
                    vol.Optional(CONF_ACCOUNT_ID, default=""): str,
                    vol.Optional(CONF_REFRESH_TOKEN, default=""): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow."""
        return CodexUsageOptionsFlow()


class CodexUsageOptionsFlow(OptionsFlow):
    """Handle options for OpenAI Codex Usage."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current_interval = self.config_entry.options.get(
            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
        )
        current_access_token = self.config_entry.options.get(
            CONF_ACCESS_TOKEN,
            self.config_entry.data.get(CONF_ACCESS_TOKEN, ""),
        )
        current_account_id = self.config_entry.options.get(
            CONF_ACCOUNT_ID,
            self.config_entry.data.get(CONF_ACCOUNT_ID, ""),
        )
        current_refresh_token = self.config_entry.options.get(
            CONF_REFRESH_TOKEN,
            self.config_entry.data.get(CONF_REFRESH_TOKEN, ""),
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_UPDATE_INTERVAL, default=current_interval): vol.All(
                        int, vol.Range(min=60, max=3600)
                    ),
                    vol.Required(CONF_ACCESS_TOKEN, default=current_access_token): str,
                    vol.Optional(CONF_ACCOUNT_ID, default=current_account_id): str,
                    vol.Optional(CONF_REFRESH_TOKEN, default=current_refresh_token): str,
                }
            ),
        )


def _normalize_credential_value(value: Any) -> str:
    """Accept plain tokens, quoted tokens, or JSON object with `data`."""
    if not isinstance(value, str):
        return ""
    raw = value.strip()
    if not raw:
        return ""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if isinstance(parsed, str):
        return parsed.strip()
    if isinstance(parsed, dict):
        data = parsed.get("data")
        if isinstance(data, str):
            return data.strip()
    return raw
