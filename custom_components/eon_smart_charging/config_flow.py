"""Config flow for E.ON Smart Charging integration supporting meineonandroid:// copy-paste."""

from __future__ import annotations

import logging
from typing import Any
import urllib.parse
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    EonApiError,
    EonAuthError,
    EonSmartChargingApiClient,
    generate_pkce,
    get_oauth_authorization_url,
)
from .const import (
    CONF_B2C_TOKEN,
    CONF_CALLBACK_URL,
    CONF_CONFIG_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_TYPE,
    CONF_HEMS_TOKEN,
    CONF_REFRESH_TOKEN,
    DEVICE_TYPE_CAR,
    DEVICE_TYPE_WALLBOX,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def extract_code_from_callback(callback_str: str) -> str | None:
    """Extract code from meineonandroid:// URL or query string."""
    clean = callback_str.strip()
    if not clean:
        return None

    # If it is a full URL or contains query parameters
    if "?" in clean:
        parsed = urllib.parse.urlparse(clean)
        query = urllib.parse.parse_qs(parsed.query)
        if "code" in query and query["code"]:
            return query["code"][0]

    # In case user pasted something like 'code=XYZ'
    if clean.startswith("code="):
        return clean.split("code=", 1)[1].split("&")[0]

    # If user pasted raw code or raw token
    return clean


class EonSmartChargingConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for E.ON Smart Charging."""

    VERSION = 1

    def __init__(self) -> None:
        self._code_verifier: str | None = None
        self._code_challenge: str | None = None
        self._auth_url: str | None = None
        self._hems_token: str | None = None
        self._b2c_token: str | None = None
        self._refresh_token: str | None = None
        self._client: EonSmartChargingApiClient | None = None
        self._devices: list[dict[str, Any]] = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Step 1: Open E.ON login and paste meineonandroid:// URL."""
        errors: dict[str, str] = {}

        if self._code_verifier is None:
            self._code_verifier, self._code_challenge = generate_pkce()
            self._auth_url = get_oauth_authorization_url(self._code_challenge)

        if user_input is not None:
            callback_input = user_input.get(CONF_CALLBACK_URL, "").strip()
            code_or_token = extract_code_from_callback(callback_input)

            if not code_or_token:
                errors["base"] = "missing_callback"
            else:
                session = async_get_clientsession(self.hass)
                self._client = EonSmartChargingApiClient(
                    session=session,
                    b2c_token=None,
                    hems_token=None,
                )
                try:
                    # Check if it looks like an OAuth code or a raw JWT token
                    if code_or_token.startswith("ey"):  # Raw JWT token
                        self._b2c_token = code_or_token
                        await self._client.async_exchange_hems_token()
                    else:
                        # Exchange authorization code using stored PKCE code_verifier
                        tokens = await self._client.async_exchange_oauth_code(
                            code=code_or_token,
                            code_verifier=self._code_verifier,
                        )
                        self._b2c_token = tokens.get("id_token") or tokens.get("access_token")
                        self._refresh_token = tokens.get("refresh_token")
                        self._hems_token = self._client.hems_token

                    # Discover devices
                    cars = await self._client.async_list_electric_cars()
                    wallboxes = await self._client.async_list_wallboxes()

                    devices = []
                    for c in cars:
                        cid = c.get("configId") or c.get("id")
                        name = c.get("name") or c.get("model") or f"Elektroauto ({cid})"
                        devices.append({
                            CONF_CONFIG_ID: cid,
                            CONF_DEVICE_TYPE: DEVICE_TYPE_CAR,
                            CONF_DEVICE_NAME: name,
                        })

                    for w in wallboxes:
                        cid = w.get("configId") or w.get("id")
                        name = w.get("name") or f"Wallbox ({cid})"
                        devices.append({
                            CONF_CONFIG_ID: cid,
                            CONF_DEVICE_TYPE: DEVICE_TYPE_WALLBOX,
                            CONF_DEVICE_NAME: name,
                        })

                    if not devices:
                        errors["base"] = "no_devices_found"
                    else:
                        self._devices = devices
                        return await self.async_step_select_device()

                except EonAuthError as err:
                    _LOGGER.error("Auth error during code exchange: %s", err)
                    errors["base"] = "invalid_auth"
                except EonApiError as err:
                    _LOGGER.error("E.ON API error: %s", err)
                    errors["base"] = "cannot_connect"

        schema = vol.Schema({
            vol.Required(CONF_CALLBACK_URL): str,
        })

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            description_placeholders={
                "auth_url": self._auth_url,
            },
            errors=errors,
        )

    async def async_step_select_device(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Step 2: Choose which car or wallbox to control."""
        if user_input is not None:
            selected_id = user_input[CONF_CONFIG_ID]
            selected = next(d for d in self._devices if d[CONF_CONFIG_ID] == selected_id)

            await self.async_set_unique_id(selected_id)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=selected[CONF_DEVICE_NAME],
                data={
                    CONF_HEMS_TOKEN: self._hems_token,
                    CONF_B2C_TOKEN: self._b2c_token,
                    CONF_REFRESH_TOKEN: self._refresh_token,
                    CONF_CONFIG_ID: selected[CONF_CONFIG_ID],
                    CONF_DEVICE_TYPE: selected[CONF_DEVICE_TYPE],
                    CONF_DEVICE_NAME: selected[CONF_DEVICE_NAME],
                },
            )

        options = {d[CONF_CONFIG_ID]: f"{d[CONF_DEVICE_NAME]} ({d[CONF_DEVICE_TYPE]})" for d in self._devices}
        schema = vol.Schema({
            vol.Required(CONF_CONFIG_ID, default=self._devices[0][CONF_CONFIG_ID]): vol.In(options),
        })
        return self.async_show_form(step_id="select_device", data_schema=schema)
