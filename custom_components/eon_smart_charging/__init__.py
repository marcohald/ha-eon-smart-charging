"""The E.ON Smart Charging Home Assistant integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import EonApiError, EonSmartChargingApiClient
from .const import (
    CONF_B2C_TOKEN,
    CONF_CONFIG_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_TYPE,
    CONF_HEMS_TOKEN,
    CONF_REFRESH_TOKEN,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DEVICE_TYPE_CAR,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SELECT,
    Platform.SWITCH,
    Platform.TIME,
    Platform.NUMBER,
    Platform.SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up E.ON Smart Charging from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    session = async_get_clientsession(hass)
    client = EonSmartChargingApiClient(
        session=session,
        hems_token=entry.data.get(CONF_HEMS_TOKEN),
        b2c_token=entry.data.get(CONF_B2C_TOKEN),
        refresh_token=entry.data.get(CONF_REFRESH_TOKEN),
    )

    device_type = entry.data.get(CONF_DEVICE_TYPE, DEVICE_TYPE_CAR)
    config_id = entry.data[CONF_CONFIG_ID]

    coordinator = EonDataUpdateCoordinator(
        hass=hass,
        client=client,
        device_type=device_type,
        config_id=config_id,
        name=entry.data.get(CONF_DEVICE_NAME, "E.ON Smart Charging"),
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
        "device_type": device_type,
        "config_id": config_id,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


class EonDataUpdateCoordinator(DataUpdateCoordinator[dict]):
    """Coordinator for fetching E.ON charging data."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: EonSmartChargingApiClient,
        device_type: str,
        config_id: str,
        name: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL_SECONDS),
        )
        self.client = client
        self.device_type = device_type
        self.config_id = config_id

    async def _async_update_data(self) -> dict:
        """Fetch latest charging data from FEH API."""
        try:
            return await self.client.async_get_charging_status(self.device_type, self.config_id)
        except EonApiError as err:
            raise UpdateFailed(f"Error communicating with E.ON FEH API: {err}") from err


class EonEntity(CoordinatorEntity[EonDataUpdateCoordinator]):
    """Base class for E.ON Smart Charging entities."""

    def __init__(self, coordinator: EonDataUpdateCoordinator, entry: ConfigEntry, key: str) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self._key = key
        self._attr_has_entity_name = True
        self._attr_unique_id = f"{entry.data[CONF_CONFIG_ID]}_{key}"

    @property
    def device_info(self) -> dict:
        """Return information about the device."""
        device_name = self.entry.data.get(CONF_DEVICE_NAME, "E.ON Smart Charging")
        config_id = self.entry.data[CONF_CONFIG_ID]
        return {
            "identifiers": {(DOMAIN, config_id)},
            "name": device_name,
            "manufacturer": "E.ON",
            "model": "HEMS Smart Charging (" + self.coordinator.device_type + ")",
        }
