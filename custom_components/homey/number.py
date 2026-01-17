"""Support for Homey number entities."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HomeyDataUpdateCoordinator
from .device_info import get_device_info

_LOGGER = logging.getLogger(__name__)

# Capabilities that should be exposed as number entities
# These are numeric settings that users can control, not measurements
NUMBER_CAPABILITIES = [
    # Add capabilities here that need numeric input but aren't sensors
    # Example: "dim" could be here, but it's already handled by light platform
    # "some_setting": {"min": 0, "max": 100, "step": 1, "unit": "%"},
]

# Patterns for capabilities that should be number entities
# These are sub-capabilities that need numeric control but aren't the main capability
NUMBER_CAPABILITY_PATTERNS = [
    "target_temperature.",  # target_temperature.normal, target_temperature.comfort, etc.
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Homey number entities from a config entry."""
    coordinator: HomeyDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    zones = hass.data[DOMAIN][entry.entry_id].get("zones", {})
    homey_id = hass.data[DOMAIN][entry.entry_id].get("homey_id")

    entities = []
    devices = coordinator.data if coordinator.data else await api.get_devices()
    
    # Filter devices if device_filter is configured
    from . import filter_devices
    devices = filter_devices(devices, entry.data.get("device_filter"))

    for device_id, device in devices.items():
        capabilities = device.get("capabilitiesObj", {})
        
        # Check explicitly listed number capabilities
        for capability_id in NUMBER_CAPABILITIES:
            if capability_id in capabilities:
                cap_data = capabilities[capability_id]
                # Only add if settable (user can control it)
                if cap_data.get("setable"):
                    entities.append(
                        HomeyNumber(coordinator, device_id, device, capability_id, cap_data, api, zones, homey_id)
                    )
        
        # Check for pattern-based number capabilities (sub-capabilities)
        for capability_id, cap_data in capabilities.items():
            # Skip if already handled above
            if capability_id in NUMBER_CAPABILITIES:
                continue
            
            # Skip if not settable (can't control it)
            if not cap_data.get("setable"):
                continue
            
            # Skip if it's the base capability handled by another platform
            # (e.g., target_temperature is handled by climate platform)
            if capability_id == "target_temperature":
                continue
            
            # Check if this matches a pattern for number entities
            is_number_pattern = any(
                capability_id.startswith(pattern) for pattern in NUMBER_CAPABILITY_PATTERNS
            )
            
            # Also check if it's a numeric type capability that's settable
            # and not already handled by another platform
            is_numeric_settable = (
                cap_data.get("type") == "number" and
                cap_data.get("setable") and
                "." in capability_id  # Sub-capability (e.g., target_temperature.normal)
            )
            
            if is_number_pattern or is_numeric_settable:
                entities.append(
                    HomeyNumber(coordinator, device_id, device, capability_id, cap_data, api, zones, homey_id)
                )

    async_add_entities(entities)


class HomeyNumber(CoordinatorEntity, NumberEntity):
    """Representation of a Homey number entity."""

    def __init__(
        self,
        coordinator: HomeyDataUpdateCoordinator,
        device_id: str,
        device: dict[str, Any],
        capability_id: str,
        capability_data: dict[str, Any],
        api,
        zones: dict[str, dict[str, Any]] | None = None,
        homey_id: str | None = None,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._device = device
        self._capability_id = capability_id
        self._capability_data = capability_data
        self._api = api
        self._homey_id = homey_id
        
        device_name = device.get("name", "Unknown Device")
        self._attr_name = f"{device_name} {capability_id.replace('_', ' ').title()}"
        self._attr_unique_id = f"homey_{device_id}_{capability_id}"
        
        # Get min/max/step from capability data
        self._attr_native_min_value = capability_data.get("min", 0)
        self._attr_native_max_value = capability_data.get("max", 100)
        self._attr_native_step = capability_data.get("step", 1)
        
        # Get unit if available
        unit = capability_data.get("unit")
        if unit:
            self._attr_native_unit_of_measurement = unit
        
        self._attr_device_info = get_device_info(self._homey_id, device_id, device, zones)

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        device_data = self.coordinator.data.get(self._device_id, self._device)
        capabilities = device_data.get("capabilitiesObj", {})
        value = capabilities.get(self._capability_id, {}).get("value")
        if value is not None:
            try:
                return float(value)
            except (ValueError, TypeError):
                return None
        return None

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        success = await self._api.set_capability_value(self._device_id, self._capability_id, value)
        if success:
            _LOGGER.debug("Successfully set %s to %s for device %s", self._capability_id, value, self._device_id)
            await self.coordinator.async_refresh_device(self._device_id)
        else:
            _LOGGER.error("Failed to set %s to %s for device %s", self._capability_id, value, self._device_id)
