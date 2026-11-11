"""Unit tests for E.ON Smart Charging integration."""

from __future__ import annotations

import asyncio
import base64
import datetime
import hashlib
import os
import sys
from typing import Any
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure repo root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class DummyEntity:
    def __init__(self, coordinator=None, *args, **kwargs):
        self.coordinator = coordinator
        self._attr_options = []

    @property
    def options(self):
        return getattr(self, "_attr_options", [])

    def __class_getitem__(cls, item):
        return cls


class DummyCoordinator:
    def __init__(self, *args, **kwargs):
        pass

    def __class_getitem__(cls, item):
        return cls


# Mock Home Assistant framework classes before importing custom components
for mod in [
    "homeassistant",
    "homeassistant.config_entries",
    "homeassistant.const",
    "homeassistant.core",
    "homeassistant.data_entry_flow",
    "homeassistant.helpers",
    "homeassistant.helpers.aiohttp_client",
    "homeassistant.helpers.device_registry",
    "homeassistant.helpers.entity_platform",
]:
    sys.modules.setdefault(mod, MagicMock())

coord_mod = MagicMock()
coord_mod.CoordinatorEntity = DummyEntity
coord_mod.DataUpdateCoordinator = DummyCoordinator
coord_mod.UpdateFailed = Exception
sys.modules["homeassistant.helpers.update_coordinator"] = coord_mod

for comp in ["select", "switch", "time", "number", "sensor"]:
    m = MagicMock()
    m.SelectEntity = DummyEntity
    m.SwitchEntity = DummyEntity
    m.TimeEntity = DummyEntity
    m.NumberEntity = DummyEntity
    m.NumberMode = MagicMock()
    m.SensorEntity = DummyEntity
    sys.modules[f"homeassistant.components.{comp}"] = m

from custom_components.eon_smart_charging.const import (
    CONF_CONFIG_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_TYPE,
    CONF_HEMS_TOKEN,
    CONF_REFRESH_TOKEN,
    DEVICE_TYPE_CAR,
    DEVICE_TYPE_WALLBOX,
    DOMAIN,
    MODE_NORMAL,
    MODE_OFF,
    MODE_SMART,
    MODES_CAR,
    MODES_WALLBOX,
    OAUTH_CLIENT_ID,
    OAUTH_REDIRECT_URI,
)
from custom_components.eon_smart_charging.api import (
    EonApiError,
    EonAuthError,
    EonSmartChargingApiClient,
    generate_pkce,
    get_oauth_authorization_url,
)
from custom_components.eon_smart_charging.config_flow import extract_code_from_callback
from custom_components.eon_smart_charging.select import EonChargingModeSelect
from custom_components.eon_smart_charging.switch import (
    EonFastChargingSwitch,
    EonSmartChargingSwitch,
)
from custom_components.eon_smart_charging.time import EonDepartureTimeEntity
from custom_components.eon_smart_charging.number import (
    EonMinimumSocNumber,
    EonTargetSocNumber,
)
from custom_components.eon_smart_charging.sensor import (
    EonActiveModeSensor,
    EonConnectionStatusSensor,
)


class MockResponse:
    """Mock aiohttp response context manager."""

    def __init__(self, status: int = 200, json_data: Any = None, text_data: str = ""):
        self.status = status
        self._json_data = json_data if json_data is not None else {}
        self._text_data = text_data

    async def json(self):
        return self._json_data

    async def text(self):
        return self._text_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


class TestEonPkceAndAuth(unittest.TestCase):
    """Test PKCE generation and URL helpers."""

    def test_generate_pkce(self):
        verifier, challenge = generate_pkce()
        self.assertTrue(len(verifier) >= 43)
        self.assertTrue(len(challenge) >= 43)
        expected_digest = hashlib.sha256(verifier.encode("utf-8")).digest()
        expected_challenge = base64.urlsafe_b64encode(expected_digest).decode("utf-8").rstrip("=")
        self.assertEqual(challenge, expected_challenge)

    def test_get_oauth_authorization_url(self):
        challenge = "test_challenge_12345"
        url = get_oauth_authorization_url(challenge)
        self.assertIn("https://crm.eon.de/services/oauth2/authorize", url)
        self.assertIn(f"client_id={OAUTH_CLIENT_ID}", url)
        self.assertIn(challenge, url)
        self.assertIn("code_challenge_method=S256", url)
        self.assertIn("response_type=code", url)


class TestCallbackParsing(unittest.TestCase):
    """Test extract_code_from_callback with various redirect formats."""

    def test_extract_code_from_query(self):
        cb = "meineonandroid://auth/success/auth0?code=sample_auth_code_123"
        self.assertEqual(extract_code_from_callback(cb), "sample_auth_code_123")

    def test_extract_code_with_multiple_params(self):
        cb = "meineonandroid://auth/success/auth0?code=code_abc&state=xyz123"
        self.assertEqual(extract_code_from_callback(cb), "code_abc")

    def test_extract_code_from_fragment(self):
        cb = "meineonandroid://auth/success/auth0#code=frag_code_999"
        self.assertEqual(extract_code_from_callback(cb), "frag_code_999")

    def test_extract_token_from_fragment(self):
        cb = "meineonandroid://auth/success/auth0#access_token=eyJhbGciOi..."
        self.assertEqual(extract_code_from_callback(cb), "eyJhbGciOi...")

    def test_extract_from_code_prefix(self):
        cb = "code=my_prefix_code&other=1"
        self.assertEqual(extract_code_from_callback(cb), "my_prefix_code")

    def test_extract_raw_string(self):
        cb = "raw_code_value_direct"
        self.assertEqual(extract_code_from_callback(cb), "raw_code_value_direct")

    def test_extract_empty_or_whitespace(self):
        self.assertIsNone(extract_code_from_callback(""))
        self.assertIsNone(extract_code_from_callback("   "))


class TestEonApiClient(unittest.IsolatedAsyncioTestCase):
    """Test EonSmartChargingApiClient operations."""

    async def test_oauth_code_exchange(self):
        session = MagicMock()
        mock_oauth_resp = MockResponse(
            status=200,
            json_data={
                "id_token": "mock_id_token",
                "access_token": "mock_oauth_access_token",
                "refresh_token": "mock_refresh_token",
            },
        )
        mock_hems_resp = MockResponse(
            status=200,
            json_data={
                "access_token": "mock_hems_token_123",
                "expires_in": 3600,
            },
        )

        session.post.side_effect = [mock_oauth_resp, mock_hems_resp]
        client = EonSmartChargingApiClient(session=session)

        tokens = await client.async_exchange_oauth_code("code_xyz", "verifier_abc")
        self.assertEqual(tokens["refresh_token"], "mock_refresh_token")
        self.assertEqual(client.b2c_token, "mock_id_token")
        self.assertEqual(client.hems_token, "mock_hems_token_123")
        self.assertEqual(client.refresh_token, "mock_refresh_token")

    async def test_api_request_headers(self):
        session = MagicMock()
        client = EonSmartChargingApiClient(
            session=session,
            hems_token="valid_hems_token",
        )
        mock_resp = MockResponse(status=200, json_data=[{"id": "car1", "name": "Spring"}])
        session.request.return_value = mock_resp

        cars = await client.async_list_electric_cars()
        self.assertEqual(len(cars), 1)
        self.assertEqual(cars[0]["name"], "Spring")

        call_args = session.request.call_args
        method, url = call_args[0]
        headers = call_args[1]["headers"]
        self.assertEqual(method, "GET")
        self.assertTrue(url.endswith("/api/v1/electric-car"))
        self.assertEqual(headers["Authorization"], "Bearer valid_hems_token")
        self.assertEqual(headers["User-Agent"], "HomeAssistant-EonSmartCharging/1.0.1")

    async def test_set_car_autopilot(self):
        session = MagicMock()
        client = EonSmartChargingApiClient(session=session, hems_token="hems_tok")
        mock_resp = MockResponse(status=204)
        session.request.return_value = mock_resp

        await client.async_set_car_autopilot(
            config_id="config_car_1",
            active=True,
            departure_time="07:30",
            target_soc=85,
            minimum_soc=25,
        )

        call_args = session.request.call_args
        method, url = call_args[0]
        json_body = call_args[1]["json"]

        self.assertEqual(method, "PUT")
        self.assertIn("/api/v1/electric-car/config_car_1/smartCharging/autopilot", url)
        self.assertEqual(
            json_body,
            {
                "active": True,
                "departureTime": "0730",
                "targetSoc": 85,
                "minimumSoc": 25,
            },
        )

    async def test_set_wallbox_gridx_smart_charge(self):
        session = MagicMock()
        client = EonSmartChargingApiClient(session=session, hems_token="hems_tok")
        mock_resp = MockResponse(status=204)
        session.request.return_value = mock_resp

        await client.async_set_wallbox_gridx_smart_charge(
            config_id="wb_1",
            active=True,
            departure_time="08:00",
            departure_soc=90,
            min_soc=30,
        )

        call_args = session.request.call_args
        method, url = call_args[0]
        json_body = call_args[1]["json"]

        self.assertEqual(method, "PUT")
        self.assertIn("/api/v2/wallboxes/wb_1/smartCharging/gridxSmartCharge", url)
        self.assertEqual(
            json_body,
            {
                "active": True,
                "departureTimestamp": "0800",
                "departureSoc": 90,
                "minSoc": 30,
            },
        )

    async def test_api_401_refresh_retry(self):
        session = MagicMock()
        client = EonSmartChargingApiClient(
            session=session,
            b2c_token="old_b2c_token",
            hems_token="expired_hems_token",
            refresh_token="valid_refresh_token",
        )

        mock_401 = MockResponse(status=401, text_data="Unauthorized")
        mock_oauth_refresh = MockResponse(
            status=200,
            json_data={"access_token": "new_b2c_token", "refresh_token": "new_refresh"},
        )
        mock_hems_token = MockResponse(
            status=200,
            json_data={"access_token": "new_hems_token", "expires_in": 3600},
        )
        mock_retry_200 = MockResponse(status=200, json_data={"status": "ok"})

        session.request.side_effect = [mock_401, mock_retry_200]
        session.post.side_effect = [mock_oauth_refresh, mock_hems_token]

        result = await client.async_request("GET", "/api/v1/test")
        self.assertEqual(result, {"status": "ok"})
        self.assertEqual(client.hems_token, "new_hems_token")


class TestEntities(unittest.IsolatedAsyncioTestCase):
    """Test entity state calculation and commands."""

    def setUp(self):
        self.mock_client = AsyncMock()
        self.mock_coordinator = MagicMock()
        self.mock_coordinator.client = self.mock_client
        self.mock_coordinator.config_id = "car_123"
        self.mock_coordinator.device_type = DEVICE_TYPE_CAR
        self.mock_coordinator.async_request_refresh = AsyncMock()

        self.mock_entry = MagicMock()
        self.mock_entry.data = {
            CONF_CONFIG_ID: "car_123",
            CONF_DEVICE_NAME: "Dacia Spring",
            CONF_DEVICE_TYPE: DEVICE_TYPE_CAR,
        }

    async def test_select_entity(self):
        select = EonChargingModeSelect(self.mock_coordinator, self.mock_entry)
        self.assertEqual(select.options, MODES_CAR)

        # Autopilot active -> MODE_SMART
        self.mock_coordinator.data = {"autopilot": {"active": True}}
        self.assertEqual(select.current_option, MODE_SMART)

        # Fast active -> MODE_NORMAL
        self.mock_coordinator.data = {"fastCharging": {"active": True}}
        self.assertEqual(select.current_option, MODE_NORMAL)

        # Inactive -> MODE_OFF
        self.mock_coordinator.data = {}
        self.assertEqual(select.current_option, MODE_OFF)

        # Select smart mode
        await select.async_select_option(MODE_SMART)
        self.mock_client.async_set_car_fast_charging.assert_called_with("car_123", False)
        self.mock_client.async_set_car_autopilot.assert_called()

        # Select off mode
        await select.async_select_option(MODE_OFF)
        self.mock_client.async_set_car_autopilot.assert_called_with(
            "car_123", active=False, departure_time="0700", target_soc=80, minimum_soc=20
        )

    async def test_switch_entities(self):
        smart_switch = EonSmartChargingSwitch(self.mock_coordinator, self.mock_entry)
        fast_switch = EonFastChargingSwitch(self.mock_coordinator, self.mock_entry)

        self.mock_coordinator.data = {
            "autopilot": {"active": True},
            "fastCharging": {"active": False},
        }
        self.assertTrue(smart_switch.is_on)
        self.assertFalse(fast_switch.is_on)

        await smart_switch.async_turn_off()
        self.mock_client.async_set_car_autopilot.assert_called()

        await fast_switch.async_turn_on()
        self.mock_client.async_set_car_fast_charging.assert_called_with("car_123", True)

    async def test_time_entity(self):
        time_entity = EonDepartureTimeEntity(self.mock_coordinator, self.mock_entry)
        self.mock_coordinator.data = {"autopilot": {"departureTime": "0645"}}
        self.assertEqual(time_entity.native_value, datetime.time(6, 45))

        await time_entity.async_set_value(datetime.time(8, 15))
        self.mock_client.async_set_car_autopilot.assert_called_with(
            "car_123", active=False, departure_time="0815", target_soc=80, minimum_soc=20
        )

    async def test_number_entities(self):
        target_soc = EonTargetSocNumber(self.mock_coordinator, self.mock_entry)
        min_soc = EonMinimumSocNumber(self.mock_coordinator, self.mock_entry)

        self.mock_coordinator.data = {
            "autopilot": {"targetSoc": 90, "minimumSoc": 30}
        }
        self.assertEqual(target_soc.native_value, 90.0)
        self.assertEqual(min_soc.native_value, 30.0)

        await target_soc.async_set_native_value(85.0)
        self.mock_client.async_set_car_autopilot.assert_called_with(
            "car_123", active=False, departure_time="0700", target_soc=85, minimum_soc=30
        )

    async def test_sensor_entities(self):
        mode_sensor = EonActiveModeSensor(self.mock_coordinator, self.mock_entry)
        cable_sensor = EonConnectionStatusSensor(self.mock_coordinator, self.mock_entry)

        self.mock_coordinator.data = {
            "autopilot": {"active": True, "departureTime": "0700", "targetSoc": 80},
            "chargeState": {"isPluggedIn": True},
        }
        self.assertIn("Smart Laden aktiv", mode_sensor.native_value)
        self.assertEqual(cable_sensor.native_value, "Angesteckt")

        self.mock_coordinator.data = {
            "fastCharging": {"active": True},
            "chargeState": {"isPluggedIn": False},
        }
        self.assertEqual(mode_sensor.native_value, "Normales Sofortladen aktiv")
        self.assertEqual(cable_sensor.native_value, "Nicht angesteckt")


class TestConstants(unittest.TestCase):
    """Test modes and constants."""

    def test_modes_consistency(self):
        self.assertIn(MODE_OFF, MODES_CAR)
        self.assertIn(MODE_SMART, MODES_CAR)
        self.assertIn(MODE_NORMAL, MODES_CAR)
        self.assertEqual(MODES_CAR, MODES_WALLBOX)


if __name__ == "__main__":
    unittest.main()
