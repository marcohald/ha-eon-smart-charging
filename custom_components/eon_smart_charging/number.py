"""Number entities for E.ON charging parameters (Target SoC, Minimum SoC)."""

from __future__ import annotations

import logging
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
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
    """Set up the E.ON number platform."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: EonDataUpdateCoordinator = data["coordinator"]

    async_add_entities([
        EonTargetSocNumber(coordinator, entry),
        EonMinimumSocNumber(coordinator, entry),
    ])


class EonTargetSocNumber(EonEntity, NumberEntity):
    """Number entity to set Target SoC (Ladeziel)."""

    def __init__(self, coordinator: EonDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "target_soc")
        self._attr_name = "Ladeziel (Ziel-SoC)"
        self._attr_icon = "mdi:battery-charging-high"
        self._attr_native_min_value = 50.0
        self._attr_native_max_value = 100.0
        self._attr_native_step = 5.0
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_mode = NumberMode.SLIDER

    @property
    def native_value(self) -> float | None:
        """Return current target SoC."""
        data = self.coordinator.data or {}
        if self.coordinator.device_type == DEVICE_TYPE_CAR:
            return float(data.get("autopilot", {}).get("targetSoc", 80))
        return float(data.get("gridxSmartCharge", {}).get("departureSoc", 80))

    async def async_set_native_value(self, value: float) -> None:
        """Update target SoC."""
        client = self.coordinator.client
        config_id = self.coordinator.config_id
        dev_type = self.coordinator.device_type
        data = self.coordinator.data or {}

        val_int = int(value)

        if dev_type == DEVICE_TYPE_CAR:
            auto = data.get("autopilot", {})
            await client.async_set_car_autopilot(
                config_id,
                active=auto.get("active", False),
                departure_time=auto.get("departureTime", "0700"),
                target_soc=val_int,
                minimum_soc=auto.get("minimumSoc", 20),
            )
        else:
            gridx = data.get("gridxSmartCharge", {})
            await client.async_set_wallbox_gridx_smart_charge(
                config_id,
                active=gridx.get("active", False),
                departure_time=gridx.get("departureTimestamp", "0700"),
                departure_soc=val_int,
                min_soc=gridx.get("minSoc", 20),
            )
        await self.coordinator.async_request_refresh()


class EonMinimumSocNumber(EonEntity, NumberEntity):
    """Number entity to set Minimum SoC (Mindestladestand)."""

    def __init__(self, coordinator: EonDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "minimum_soc")
        self._attr_name = "Mindestladestand (Min-SoC)"
        self._attr_icon = "mdi:battery-charging-low"
        self._attr_native_min_value = 10.0
        self._attr_native_max_value = 50.0
        self._attr_native_step = 5.0
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_mode = NumberMode.SLIDER

    @property
    def native_value(self) -> float | None:
        """Return current minimum SoC."""
        data = self.coordinator.data or {}
        if self.coordinator.device_type == DEVICE_TYPE_CAR:
            return float(data.get("autopilot", {}).get("minimumSoc", 20))
        return float(data.get("gridxSmartCharge", {}).get("minSoc", 20))

    async def async_set_native_value(self, value: float) -> None:
        """Update minimum SoC."""
        client = self.coordinator.client
        config_id = self.coordinator.config_id
        dev_type = self.coordinator.device_type
        data = self.coordinator.data or {}

        val_int = int(value)

        if dev_type == DEVICE_TYPE_CAR:
            auto = data.get("autopilot", {})
            await client.async_set_car_autopilot(
                config_id,
                active=auto.get("active", False),
                departure_time=auto.get("departureTime", "0700"),
                target_soc=auto.get("targetSoc", 80),
                minimum_soc=val_int,
            )
        else:
            gridx = data.get("gridxSmartCharge", {})
            await client.async_set_wallbox_gridx_smart_charge(
                config_id,
                active=gridx.get("active", False),
                departure_time=gridx.get("departureTimestamp", "0700"),
                departure_soc=gridx.get("departureSoc", 80),
                min_soc=val_int,
            )
        await self.coordinator.async_request_refresh()
