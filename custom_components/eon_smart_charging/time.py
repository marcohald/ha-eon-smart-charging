"""Time entity for E.ON departure time."""

from __future__ import annotations

import datetime
import logging
from homeassistant.components.time import TimeEntity
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
    """Set up the E.ON departure time platform."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: EonDataUpdateCoordinator = data["coordinator"]

    async_add_entities([EonDepartureTimeEntity(coordinator, entry)])


class EonDepartureTimeEntity(EonEntity, TimeEntity):
    """Time entity to configure desired departure time for smart charging."""

    def __init__(self, coordinator: EonDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "departure_time")
        self._attr_name = "Abfahrtszeit"
        self._attr_icon = "mdi:clock-outline"

    @property
    def native_value(self) -> datetime.time | None:
        """Return the current configured departure time."""
        data = self.coordinator.data or {}
        time_str = None
        if self.coordinator.device_type == DEVICE_TYPE_CAR:
            time_str = data.get("autopilot", {}).get("departureTime")
        else:
            time_str = data.get("gridxSmartCharge", {}).get("departureTimestamp")

        if not time_str:
            return datetime.time(7, 0)

        # time_str could be "0700" or "07:00"
        clean = time_str.replace(":", "")
        try:
            if len(clean) == 4:
                hour = int(clean[:2])
                minute = int(clean[2:])
                return datetime.time(hour, minute)
        except ValueError:
            pass
        return datetime.time(7, 0)

    async def async_set_value(self, value: datetime.time) -> None:
        """Update departure time."""
        client = self.coordinator.client
        config_id = self.coordinator.config_id
        dev_type = self.coordinator.device_type
        data = self.coordinator.data or {}

        time_formatted = f"{value.hour:02d}{value.minute:02d}"

        if dev_type == DEVICE_TYPE_CAR:
            auto = data.get("autopilot", {})
            await client.async_set_car_autopilot(
                config_id,
                active=auto.get("active", False),
                departure_time=time_formatted,
                target_soc=auto.get("targetSoc", 80),
                minimum_soc=auto.get("minimumSoc", 20),
            )
        else:
            gridx = data.get("gridxSmartCharge", {})
            await client.async_set_wallbox_gridx_smart_charge(
                config_id,
                active=gridx.get("active", False),
                departure_time=time_formatted,
                departure_soc=gridx.get("departureSoc", 80),
                min_soc=gridx.get("minSoc", 20),
            )

        await self.coordinator.async_request_refresh()
