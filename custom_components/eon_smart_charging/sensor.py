"""Sensor platform for E.ON charging telemetry and status."""

from __future__ import annotations

import logging
from homeassistant.components.sensor import SensorEntity
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
    """Set up the E.ON sensor platform."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: EonDataUpdateCoordinator = data["coordinator"]

    async_add_entities([
        EonActiveModeSensor(coordinator, entry),
        EonConnectionStatusSensor(coordinator, entry),
    ])


class EonActiveModeSensor(EonEntity, SensorEntity):
    """Sensor reporting active charging mode."""

    def __init__(self, coordinator: EonDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "active_mode_status")
        self._attr_name = "Aktiver Modus Status"
        self._attr_icon = "mdi:information-outline"

    @property
    def native_value(self) -> str:
        """Return human-readable mode description."""
        data = self.coordinator.data or {}
        if self.coordinator.device_type == DEVICE_TYPE_CAR:
            auto = data.get("autopilot", {})
            fast = data.get("fastCharging", {})
            if auto.get("active"):
                dep = auto.get("departureTime", "0700")
                target = auto.get("targetSoc", 80)
                return f"Smart Laden aktiv (Ziel: {target}% um {dep[:2]}:{dep[2:]})"
            if fast.get("active"):
                return "Normales Sofortladen aktiv"
            return "Inaktiv / Aus"
        else:
            gridx = data.get("gridxSmartCharge", {})
            fast = data.get("fastCharge", {})
            if gridx.get("active"):
                return "gridX Smart Laden aktiv"
            if fast.get("active"):
                return "Schnellladen aktiv"
            return "Inaktiv / Aus"


class EonConnectionStatusSensor(EonEntity, SensorEntity):
    """Sensor reporting car plug status if available."""

    def __init__(self, coordinator: EonDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "connection_state")
        self._attr_name = "Kabelstatus"
        self._attr_icon = "mdi:power-plug"

    @property
    def native_value(self) -> str:
        """Return plug / connection status."""
        data = self.coordinator.data or {}
        # Checks if telemetry is in payload
        charge_state = data.get("chargeState", {})
        if "isPluggedIn" in charge_state:
            return "Angesteckt" if charge_state["isPluggedIn"] else "Nicht angesteckt"
        return "Unbekannt / Cloud"
