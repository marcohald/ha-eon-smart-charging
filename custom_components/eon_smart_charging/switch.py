"""Switch entities for E.ON charging modes."""

from __future__ import annotations

import logging
from typing import Any
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import EonDataUpdateCoordinator, EonEntity
from .const import DEVICE_TYPE_CAR, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the E.ON charging switches."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: EonDataUpdateCoordinator = data["coordinator"]

    async_add_entities([
        EonSmartChargingSwitch(coordinator, entry),
        EonFastChargingSwitch(coordinator, entry),
    ])


class EonSmartChargingSwitch(EonEntity, SwitchEntity):
    """Switch to toggle Smart Charging on/off."""

    def __init__(self, coordinator: EonDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "smart_charging_active")
        self._attr_name = "Smart Laden"
        self._attr_icon = "mdi:lightning-bolt-circle"

    @property
    def is_on(self) -> bool:
        """Return true if smart charging is active."""
        data = self.coordinator.data or {}
        if self.coordinator.device_type == DEVICE_TYPE_CAR:
            return bool(data.get("autopilot", {}).get("active"))
        return bool(data.get("gridxSmartCharge", {}).get("active"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on Smart Charging."""
        client = self.coordinator.client
        config_id = self.coordinator.config_id
        dev_type = self.coordinator.device_type
        data = self.coordinator.data or {}

        if dev_type == DEVICE_TYPE_CAR:
            auto = data.get("autopilot", {})
            # Deactivate fast first
            await client.async_set_car_fast_charging(config_id, False)
            await client.async_set_car_autopilot(
                config_id,
                active=True,
                departure_time=auto.get("departureTime", "0700"),
                target_soc=auto.get("targetSoc", 80),
                minimum_soc=auto.get("minimumSoc", 20),
            )
        else:
            gridx = data.get("gridxSmartCharge", {})
            await client.async_set_wallbox_fast_charge(config_id, False)
            await client.async_set_wallbox_gridx_smart_charge(
                config_id,
                active=True,
                departure_time=gridx.get("departureTimestamp", "0700"),
                departure_soc=gridx.get("departureSoc", 80),
                min_soc=gridx.get("minSoc", 20),
            )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off Smart Charging."""
        client = self.coordinator.client
        config_id = self.coordinator.config_id
        dev_type = self.coordinator.device_type
        data = self.coordinator.data or {}

        if dev_type == DEVICE_TYPE_CAR:
            auto = data.get("autopilot", {})
            await client.async_set_car_autopilot(
                config_id,
                active=False,
                departure_time=auto.get("departureTime", "0700"),
                target_soc=auto.get("targetSoc", 80),
                minimum_soc=auto.get("minimumSoc", 20),
            )
        else:
            gridx = data.get("gridxSmartCharge", {})
            await client.async_set_wallbox_gridx_smart_charge(
                config_id,
                active=False,
                departure_time=gridx.get("departureTimestamp", "0700"),
                departure_soc=gridx.get("departureSoc", 80),
                min_soc=gridx.get("minSoc", 20),
            )
        await self.coordinator.async_request_refresh()


class EonFastChargingSwitch(EonEntity, SwitchEntity):
    """Switch to toggle Normal / Fast Charging on/off."""

    def __init__(self, coordinator: EonDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "normal_charging_active")
        self._attr_name = "Normales Laden (Sofort)"
        self._attr_icon = "mdi:flash"

    @property
    def is_on(self) -> bool:
        """Return true if fast charging is active."""
        data = self.coordinator.data or {}
        fast = data.get("fastCharging", {}) or data.get("fastCharge", {})
        return bool(fast.get("active"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on Normal Charging."""
        client = self.coordinator.client
        config_id = self.coordinator.config_id
        dev_type = self.coordinator.device_type
        data = self.coordinator.data or {}

        # Deactivate smart mode first
        if dev_type == DEVICE_TYPE_CAR:
            auto = data.get("autopilot", {})
            await client.async_set_car_autopilot(
                config_id,
                active=False,
                departure_time=auto.get("departureTime", "0700"),
                target_soc=auto.get("targetSoc", 80),
                minimum_soc=auto.get("minimumSoc", 20),
            )
            await client.async_set_car_fast_charging(config_id, True)
        else:
            gridx = data.get("gridxSmartCharge", {})
            await client.async_set_wallbox_gridx_smart_charge(
                config_id,
                active=False,
                departure_time=gridx.get("departureTimestamp", "0700"),
                departure_soc=gridx.get("departureSoc", 80),
                min_soc=gridx.get("minSoc", 20),
            )
            await client.async_set_wallbox_fast_charge(config_id, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off Normal Charging."""
        client = self.coordinator.client
        config_id = self.coordinator.config_id
        if self.coordinator.device_type == DEVICE_TYPE_CAR:
            await client.async_set_car_fast_charging(config_id, False)
        else:
            await client.async_set_wallbox_fast_charge(config_id, False)
        await self.coordinator.async_request_refresh()
