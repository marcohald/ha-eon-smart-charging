"""Asynchronous API client for E.ON HEMS / Smart Charging."""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import time
from typing import Any
import urllib.parse
import aiohttp

from .const import (
    DEFAULT_FEH_BASE_URL,
    DEFAULT_FEH_TOKEN_URL,
    DEVICE_TYPE_CAR,
    DEVICE_TYPE_WALLBOX,
    OAUTH_AUTHORIZE_URL,
    OAUTH_CLIENT_ID,
    OAUTH_REDIRECT_URI,
    OAUTH_SCOPES,
    OAUTH_TOKEN_URL,
)

_LOGGER = logging.getLogger(__name__)


class EonApiError(Exception):
    """General E.ON API exception."""


class EonAuthError(EonApiError):
    """Authentication or token exchange failure."""


def generate_pkce() -> tuple[str, str]:
    """Generate code_verifier and code_challenge for PKCE."""
    # RFC 7636: 32 random bytes urlsafe base64 without padding
    code_verifier = base64.urlsafe_b64encode(os.urandom(32)).decode("utf-8").rstrip("=")
    digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")
    return code_verifier, code_challenge


def get_oauth_authorization_url(code_challenge: str) -> str:
    """Build the OAuth authorization URL for user login."""
    params = {
        "client_id": OAUTH_CLIENT_ID,
        "redirect_uri": OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": OAUTH_SCOPES,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "prompt": "login",
    }
    return f"{OAUTH_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


class EonSmartChargingApiClient:
    """API client for E.ON FEH / HEMS backend."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        hems_token: str | None = None,
        b2c_token: str | None = None,
        refresh_token: str | None = None,
        base_url: str = DEFAULT_FEH_BASE_URL,
        token_url: str = DEFAULT_FEH_TOKEN_URL,
    ) -> None:
        self._session = session
        self._hems_token = hems_token
        self._b2c_token = b2c_token
        self._refresh_token = refresh_token
        self._base_url = base_url.rstrip("/")
        self._token_url = token_url
        self._token_expires_at = 0.0

    @property
    def hems_token(self) -> str | None:
        return self._hems_token

    @property
    def b2c_token(self) -> str | None:
        return self._b2c_token

    @property
    def refresh_token(self) -> str | None:
        return self._refresh_token

    async def async_exchange_oauth_code(self, code: str, code_verifier: str) -> dict[str, Any]:
        """Exchange authorization code (from meineonandroid:// callback) for tokens."""
        clean_code = urllib.parse.unquote(code.strip())
        data = {
            "grant_type": "authorization_code",
            "client_id": OAUTH_CLIENT_ID,
            "redirect_uri": OAUTH_REDIRECT_URI,
            "code": clean_code,
            "code_verifier": code_verifier,
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        try:
            async with self._session.post(OAUTH_TOKEN_URL, data=data, headers=headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise EonAuthError(f"OAuth code exchange failed ({resp.status}): {text}")
                tokens = await resp.json()
                self._b2c_token = tokens.get("id_token") or tokens.get("access_token")
                self._refresh_token = tokens.get("refresh_token")
                # Now exchange against HEMS token
                await self.async_exchange_hems_token()
                return tokens
        except aiohttp.ClientError as err:
            raise EonApiError(f"Network error during code exchange: {err}") from err

    async def async_refresh_tokens(self) -> None:
        """Refresh B2C token using refresh_token."""
        if not self._refresh_token:
            return

        data = {
            "grant_type": "refresh_token",
            "client_id": OAUTH_CLIENT_ID,
            "refresh_token": self._refresh_token,
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        try:
            async with self._session.post(OAUTH_TOKEN_URL, data=data, headers=headers) as resp:
                if resp.status == 200:
                    tokens = await resp.json()
                    self._b2c_token = tokens.get("id_token") or tokens.get("access_token")
                    if "refresh_token" in tokens:
                        self._refresh_token = tokens["refresh_token"]
                    await self.async_exchange_hems_token()
                else:
                    _LOGGER.warning("Token refresh failed with status %d", resp.status)
        except Exception as err:
            _LOGGER.error("Failed to refresh E.ON tokens: %s", err)

    async def async_exchange_hems_token(self) -> str:
        """Exchange B2C ID token for HEMS access token."""
        if not self._b2c_token:
            if self._hems_token:
                return self._hems_token
            raise EonAuthError("No token provided to authenticate with E.ON HEMS API")

        headers = {
            "Authorization": f"Bearer {self._b2c_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            async with self._session.post(self._token_url, headers=headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise EonAuthError(f"Failed to exchange HEMS token ({resp.status}): {text}")
                data = await resp.json()
                self._hems_token = data.get("access_token")
                expires_in = data.get("expires_in", 3600)
                self._token_expires_at = time.time() + float(expires_in) - 60
                _LOGGER.debug("Successfully exchanged HEMS access token")
                return self._hems_token
        except aiohttp.ClientError as err:
            raise EonApiError(f"Network error during HEMS token exchange: {err}") from err

    async def _get_auth_headers(self) -> dict[str, str]:
        """Get headers with valid bearer token."""
        if not self._hems_token or (self._b2c_token and time.time() >= self._token_expires_at):
            if self._refresh_token:
                await self.async_refresh_tokens()
            elif self._b2c_token:
                await self.async_exchange_hems_token()

        if not self._hems_token:
            raise EonAuthError("No valid HEMS token available")

        return {
            "Authorization": f"Bearer {self._hems_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "HomeAssistant-EonSmartCharging/1.0.1",
        }

    async def async_request(self, method: str, path: str, json: dict[str, Any] | None = None) -> Any:
        """Execute request against FEH API."""
        url = f"{self._base_url}{path}"
        headers = await self._get_auth_headers()

        try:
            async with self._session.request(method, url, json=json, headers=headers) as resp:
                if resp.status == 401 and (self._refresh_token or self._b2c_token):
                    _LOGGER.info("Received 401 Unauthorized, refreshing HEMS token...")
                    if self._refresh_token:
                        await self.async_refresh_tokens()
                    elif self._b2c_token:
                        await self.async_exchange_hems_token()
                    headers = await self._get_auth_headers()
                    async with self._session.request(method, url, json=json, headers=headers) as retry_resp:
                        if retry_resp.status not in (200, 201, 204):
                            text = await retry_resp.text()
                            raise EonApiError(f"API call {method} {path} failed ({retry_resp.status}): {text}")
                        if retry_resp.status == 204:
                            return None
                        try:
                            return await retry_resp.json()
                        except Exception:
                            return await retry_resp.text()

                if resp.status not in (200, 201, 204):
                    text = await resp.text()
                    raise EonApiError(f"API call {method} {path} failed ({resp.status}): {text}")

                if resp.status == 204:
                    return None
                try:
                    return await resp.json()
                except Exception:
                    return await resp.text()
        except aiohttp.ClientError as err:
            raise EonApiError(f"Network error during call to {path}: {err}") from err

    # Device Discovery
    async def async_list_electric_cars(self) -> list[dict[str, Any]]:
        """List paired electric cars."""
        res = await self.async_request("GET", "/api/v1/electric-car")
        return res if isinstance(res, list) else []

    async def async_list_wallboxes(self) -> list[dict[str, Any]]:
        """List paired wallboxes."""
        try:
            res = await self.async_request("GET", "/api/v2/wallboxes")
            return res if isinstance(res, list) else []
        except Exception:
            return []

    # Charging Status & Configuration
    async def async_get_charging_status(self, device_type: str, config_id: str) -> dict[str, Any]:
        """Fetch current charging modes and parameters."""
        if device_type == DEVICE_TYPE_CAR:
            return await self.async_request("GET", f"/api/v1/electric-car/{config_id}/smartCharging")
        else:
            return await self.async_request("GET", f"/api/v2/wallboxes/{config_id}/smartCharging")

    # Control Commands: Electric Car
    async def async_set_car_autopilot(
        self,
        config_id: str,
        active: bool,
        departure_time: str = "0700",
        target_soc: int = 80,
        minimum_soc: int = 20,
    ) -> None:
        """Activate or configure Smart Charging (Autopilot) for car."""
        clean_time = departure_time.replace(":", "")
        payload = {
            "active": active,
            "departureTime": clean_time,
            "targetSoc": target_soc,
            "minimumSoc": minimum_soc,
        }
        await self.async_request(
            "PUT",
            f"/api/v1/electric-car/{config_id}/smartCharging/autopilot",
            json=payload,
        )

    async def async_set_car_fast_charging(self, config_id: str, active: bool) -> None:
        """Activate or deactivate Fast / Normal Charging for car."""
        payload = {"active": active}
        await self.async_request(
            "PUT",
            f"/api/v1/electric-car/{config_id}/smartCharging/fastCharging",
            json=payload,
        )

    # Control Commands: Wallbox
    async def async_set_wallbox_gridx_smart_charge(
        self,
        config_id: str,
        active: bool,
        departure_time: str = "0700",
        departure_soc: int = 80,
        min_soc: int = 20,
        user_soc: int | None = None,
    ) -> None:
        """Activate or configure gridX Smart Charging for wallbox."""
        clean_time = departure_time.replace(":", "")
        payload: dict[str, Any] = {
            "active": active,
            "departureTimestamp": clean_time,
            "departureSoc": departure_soc,
            "minSoc": min_soc,
        }
        if user_soc is not None:
            payload["userSoc"] = user_soc

        await self.async_request(
            "PUT",
            f"/api/v2/wallboxes/{config_id}/smartCharging/gridxSmartCharge",
            json=payload,
        )

    async def async_set_wallbox_fast_charge(self, config_id: str, active: bool) -> None:
        """Activate or deactivate Fast / Normal Charging for wallbox."""
        payload = {"active": active}
        await self.async_request(
            "PUT",
            f"/api/v2/wallboxes/{config_id}/smartCharging/fastCharge",
            json=payload,
        )
