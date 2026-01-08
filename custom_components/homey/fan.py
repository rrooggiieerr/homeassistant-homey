"""Support for Homey fans."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HomeyDataUpdateCoordinator
from .device_info import get_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Homey fans from a config entry."""
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
        # Only create fan entities for devices with fan_speed capability
        # Devices with just onoff should be switches, not fans
        if "fan_speed" in capabilities:
            entities.append(HomeyFan(coordinator, device_id, device, api, zones))

    async_add_entities(entities)


class HomeyFan(CoordinatorEntity, FanEntity):
    """Representation of a Homey fan."""

    def __init__(
        self,
        coordinator: HomeyDataUpdateCoordinator,
        device_id: str,
        device: dict[str, Any],
        api,
        zones: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        """Initialize the fan."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._device = device
        self._api = api
        self._attr_name = device.get("name", "Unknown Fan")
        self._attr_unique_id = f"homey_{device_id}_fan"

        capabilities = device.get("capabilitiesObj", {})
        supported_features = FanEntityFeature.SET_SPEED if "fan_speed" in capabilities else 0
        # Note: Fans don't have ON_OFF feature - they're always on/off by default
        # The onoff capability is handled via is_on property and turn_on/turn_off methods

        self._attr_supported_features = supported_features

        self._attr_device_info = get_device_info(device_id, device, zones)

    @property
    def is_on(self) -> bool:
        """Return true if fan is on."""
        device_data = self.coordinator.data.get(self._device_id, self._device)
        capabilities = device_data.get("capabilitiesObj", {})
        if "onoff" in capabilities:
            return capabilities.get("onoff", {}).get("value", False)
        # If no onoff capability, check if speed > 0
        speed = capabilities.get("fan_speed", {}).get("value", 0)
        return speed > 0

    @property
    def percentage(self) -> int | None:
        """Return the current speed percentage."""
        device_data = self.coordinator.data.get(self._device_id, self._device)
        capabilities = device_data.get("capabilitiesObj", {})
        speed = capabilities.get("fan_speed", {}).get("value")
        if speed is not None:
            # Convert speed (0-1) to percentage (0-100)
            return int(speed * 100)
        return None

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Turn on the fan."""
        if "onoff" in self._device.get("capabilitiesObj", {}):
            await self._api.set_capability_value(self._device_id, "onoff", True)

        if percentage is not None and "fan_speed" in self._device.get("capabilitiesObj", {}):
            await self._api.set_capability_value(
                self._device_id, "fan_speed", percentage / 100.0
            )

        # Immediately refresh this device's state for instant UI feedback
        await self.coordinator.async_refresh_device(self._device_id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the fan."""
        if "onoff" in self._device.get("capabilitiesObj", {}):
            await self._api.set_capability_value(self._device_id, "onoff", False)
        elif "fan_speed" in self._device.get("capabilitiesObj", {}):
            await self._api.set_capability_value(self._device_id, "fan_speed", 0.0)

        # Immediately refresh this device's state for instant UI feedback
        await self.coordinator.async_refresh_device(self._device_id)

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the speed percentage of the fan."""
        if "fan_speed" in self._device.get("capabilitiesObj", {}):
            await self._api.set_capability_value(
                self._device_id, "fan_speed", percentage / 100.0
            )
            # Immediately refresh this device's state for instant UI feedback
            await self.coordinator.async_refresh_device(self._device_id)

