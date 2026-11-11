"""Select entity for E.ON charging mode."""

from __future__ import annotations

import logging
from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import EonDataUpdateCoordinator, EonEntity
from .const import (
    DEVICE_TYPE_CAR,
    DOMAIN,
    MODE_NORMAL,
    MODE_OFF,
    MODE_SMART,
    MODES_CAR,
    MODES_WALLBOX,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the E.ON charging mode select platform."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: EonDataUpdateCoordinator = data["coordinator"]

    async_add_entities([EonChargingModeSelect(coordinator, entry)])


class EonChargingModeSelect(EonEntity, SelectEntity):
    """Select entity to choose charging mode."""

    def __init__(self, coordinator: EonDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "charging_mode")
        self._attr_name = "Lademodus"
        self._attr_icon = "mdi:ev-station"
        if coordinator.device_type == DEVICE_TYPE_CAR:
            self._attr_options = MODES_CAR
        else:
            self._attr_options = MODES_WALLBOX

    @property
    def current_option(self) -> str | None:
        """Return the current active mode."""
        data = self.coordinator.data or {}
        # Car payload check
        autopilot = data.get("autopilot", {})
        fast = data.get("fastCharging", {}) or data.get("fastCharge", {})
        gridx = data.get("gridxSmartCharge", {})

        if autopilot.get("active") or gridx.get("active"):
            return MODE_SMART
        if fast.get("active"):
            return MODE_NORMAL
        return MODE_OFF

    async def async_select_option(self, option: str) -> None:
        """Change the charging mode."""
        client = self.coordinator.client
        config_id = self.coordinator.config_id
        dev_type = self.coordinator.device_type
        data = self.coordinator.data or {}

        if dev_type == DEVICE_TYPE_CAR:
            auto = data.get("autopilot", {})
            dep_time = auto.get("departureTime", "0700")
            target_soc = auto.get("targetSoc", 80)
            min_soc = auto.get("minimumSoc", 20)

            if option == MODE_SMART:
                # Deactivate fast first, then activate autopilot
                await client.async_set_car_fast_charging(config_id, False)
                await client.async_set_car_autopilot(
                    config_id,
                    active=True,
                    departure_time=dep_time,
                    target_soc=target_soc,
                    minimum_soc=min_soc,
                )
            elif option == MODE_NORMAL:
                # Deactivate autopilot, activate fast
                await client.async_set_car_autopilot(
                    config_id,
                    active=False,
                    departure_time=dep_time,
                    target_soc=target_soc,
                    minimum_soc=min_soc,
                )
                await client.async_set_car_fast_charging(config_id, True)
            else:  # MODE_OFF
                await client.async_set_car_autopilot(
                    config_id,
                    active=False,
                    departure_time=dep_time,
                    target_soc=target_soc,
                    minimum_soc=min_soc,
                )
                await client.async_set_car_fast_charging(config_id, False)

        else:  # Wallbox
            gridx = data.get("gridxSmartCharge", {})
            dep_time = gridx.get("departureTimestamp", "0700")
            dep_soc = gridx.get("departureSoc", 80)
            min_soc = gridx.get("minSoc", 20)

            if option == MODE_SMART:
                await client.async_set_wallbox_fast_charge(config_id, False)
                await client.async_set_wallbox_gridx_smart_charge(
                    config_id,
                    active=True,
                    departure_time=dep_time,
                    departure_soc=dep_soc,
                    min_soc=min_soc,
                )
            elif option == MODE_NORMAL:
                await client.async_set_wallbox_gridx_smart_charge(
                    config_id,
                    active=False,
                    departure_time=dep_time,
                    departure_soc=dep_soc,
                    min_soc=min_soc,
                )
                await client.async_set_wallbox_fast_charge(config_id, True)
            else:
                await client.async_set_wallbox_gridx_smart_charge(
                    config_id,
                    active=False,
                    departure_time=dep_time,
                    departure_soc=dep_soc,
                    min_soc=min_soc,
                )
                await client.async_set_wallbox_fast_charge(config_id, False)

        await self.coordinator.async_request_refresh()
