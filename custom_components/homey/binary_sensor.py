"""Support for Homey binary sensors."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HomeyDataUpdateCoordinator
from .device_info import get_device_info

_LOGGER = logging.getLogger(__name__)

# Mapping of Homey alarm capabilities to HA binary sensor device classes
CAPABILITY_TO_DEVICE_CLASS = {
    "alarm_motion": BinarySensorDeviceClass.MOTION,
    "alarm_contact": BinarySensorDeviceClass.DOOR,
    "alarm_tamper": BinarySensorDeviceClass.TAMPER,
    "alarm_smoke": BinarySensorDeviceClass.SMOKE,
    "alarm_co": BinarySensorDeviceClass.CO,
    "alarm_co2": None,  # CO2 device class not available in all HA versions
    "alarm_water": BinarySensorDeviceClass.MOISTURE,
    "alarm_battery": BinarySensorDeviceClass.BATTERY,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Homey binary sensors from a config entry."""
    coordinator: HomeyDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    zones = hass.data[DOMAIN][entry.entry_id].get("zones", {})

    entities = []
    # Use coordinator data if available (more up-to-date), otherwise fetch fresh
    devices = coordinator.data if coordinator.data else await api.get_devices()
    
    # Filter devices if device_filter is configured
    from . import filter_devices
    devices = filter_devices(devices, entry.data.get("device_filter"))

    for device_id, device in devices.items():
        capabilities = device.get("capabilitiesObj", {})
        for capability_id in CAPABILITY_TO_DEVICE_CLASS:
            if capability_id in capabilities:
                entities.append(
                    HomeyBinarySensor(coordinator, device_id, device, capability_id, api, zones)
                )

    async_add_entities(entities)


class HomeyBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of a Homey binary sensor."""

    def __init__(
        self,
        coordinator: HomeyDataUpdateCoordinator,
        device_id: str,
        device: dict[str, Any],
        capability_id: str,
        api,
        zones: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._device = device
        self._capability_id = capability_id
        self._api = api

        self._attr_name = f"{device.get('name', 'Unknown')} {capability_id.replace('alarm_', '').replace('_', ' ').title()}"
        self._attr_unique_id = f"homey_{device_id}_{capability_id}"
        self._attr_device_class = CAPABILITY_TO_DEVICE_CLASS.get(capability_id)

        self._attr_device_info = get_device_info(device_id, device, zones)

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        device_data = self.coordinator.data.get(self._device_id, self._device)
        if not device_data:
            return False
        
        capabilities = device_data.get("capabilitiesObj", {})
        if not capabilities:
            return False
        
        capability = capabilities.get(self._capability_id)
        if not capability:
            return False
        
        value = capability.get("value")
        
        # Handle different value formats
        if value is None:
            return False
        
        # Handle boolean values
        if isinstance(value, bool):
            return value
        
        # Handle string values ("true", "false", "1", "0")
        if isinstance(value, str):
            value_lower = value.lower().strip()
            if value_lower in ("true", "1", "on", "yes"):
                return True
            if value_lower in ("false", "0", "off", "no", ""):
                return False
            # Try to parse as number
            try:
                return bool(int(value))
            except (ValueError, TypeError):
                _LOGGER.warning("Unknown binary sensor value format for %s.%s: %s", self._device_id, self._capability_id, value)
                return False
        
        # Handle numeric values (0/1)
        try:
            return bool(int(value))
        except (ValueError, TypeError):
            return bool(value)

