"""Support for Homey switches."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
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
    """Set up Homey switches from a config entry."""
    coordinator: HomeyDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    zones = hass.data[DOMAIN][entry.entry_id].get("zones", {})

    entities = []
    # Use coordinator data if available (more up-to-date), otherwise fetch fresh
    devices = coordinator.data if coordinator.data else await api.get_devices()
    
    # Filter devices if device_filter is configured
    from . import filter_devices
    devices = filter_devices(devices, entry.data.get("device_filter"))

    _LOGGER.info("Checking %d devices for switch capabilities", len(devices))

    for device_id, device in devices.items():
        capabilities = device.get("capabilitiesObj", {})
        driver_uri = device.get("driverUri")
        driver_id = device.get("driverId", "")
        device_class = device.get("class")
        device_name = device.get("name", "Unknown")
        
        # Check if this is a devicegroups group
        is_devicegroups_group = driver_id.startswith("homey:app:com.swttt.devicegroups:")
        if is_devicegroups_group:
            _LOGGER.debug(
                "Found devicegroups group in switch platform: %s (id: %s, class: %s, driverId: %s)",
                device_name,
                device_id,
                device_class,
                driver_id
            )
        
        # Check for onoff capabilities (both regular and sub-capabilities like onoff.output1)
        # Multi-channel devices (e.g., Shelly Plus 2 PM, Fibaro Double Switch) use sub-capabilities
        onoff_capabilities = []
        
        # Check for regular onoff capability
        if "onoff" in capabilities:
            onoff_capabilities.append("onoff")
        
        # Check for sub-capabilities (onoff.output1, onoff.output2, etc.)
        for cap_id in capabilities:
            if cap_id.startswith("onoff."):
                onoff_capabilities.append(cap_id)
        
        # Skip if no onoff capabilities found
        if not onoff_capabilities:
            continue
        
        # Skip if this device should be a light
        has_light_capabilities = (
            "dim" in capabilities
            or "light_hue" in capabilities
            or "light_temperature" in capabilities
        )
        # Skip if this device should be a fan
        has_fan_capabilities = "fan_speed" in capabilities
        # Skip if this device should be a cover
        has_cover_capabilities = any(
            cap in capabilities for cap in ["windowcoverings_state", "windowcoverings_set", "garagedoor_closed"]
        )
        # Skip if this device should be a media player
        has_media_capabilities = any(
            cap in capabilities
            for cap in ["volume_set", "speaker_playing", "speaker_next"]
        )
        
        # Special handling for devicegroups groups: respect their class
        # If a group has class "socket" or "switch", treat it as a switch
        is_devicegroups_switch = (
            is_devicegroups_group 
            and device_class in ["socket", "switch"]
        )
            
            # Only create switch if it's not a specialized device type
        # Note: Having sensor capabilities (like measure_power) does NOT exclude switch creation
        # Devices can have both switch and sensor entities
        # Exception: devicegroups groups with class "socket" or "switch" should always be switches
        if is_devicegroups_switch or not (
                has_light_capabilities
                or has_fan_capabilities
                or has_cover_capabilities
                or has_media_capabilities
            ):
            # Create switch entity for each onoff capability
            # For multi-channel devices, this creates multiple switch entities
            for onoff_cap in onoff_capabilities:
                entities.append(HomeySwitch(coordinator, device_id, device, api, zones, onoff_cap))
                _LOGGER.info(
                    "Created switch entity for device %s (%s) - capability: %s, driver: %s, class: %s",
                    device_id,
                    device.get("name", "Unknown"),
                    onoff_cap,
                    driver_uri or "unknown",
                    device_class or "unknown"
                )
        else:
            _LOGGER.debug(
                "Skipping switch entity for device %s (%s) - has specialized capabilities (light=%s, fan=%s, cover=%s, media=%s)",
                device_id,
                device.get("name", "Unknown"),
                has_light_capabilities,
                has_fan_capabilities,
                has_cover_capabilities,
                has_media_capabilities
            )
    
    _LOGGER.info("Created %d switch entities", len(entities))

    async_add_entities(entities)


class HomeySwitch(CoordinatorEntity, SwitchEntity):
    """Representation of a Homey switch."""

    def __init__(
        self,
        coordinator: HomeyDataUpdateCoordinator,
        device_id: str,
        device: dict[str, Any],
        api,
        zones: dict[str, dict[str, Any]] | None = None,
        onoff_capability: str = "onoff",
    ) -> None:
        """Initialize the switch.
        
        Args:
            coordinator: Data update coordinator
            device_id: Homey device ID
            device: Device data dictionary
            api: Homey API instance
            zones: Zones dictionary (optional)
            onoff_capability: The onoff capability ID (default: "onoff", can be "onoff.output1", etc.)
        """
        super().__init__(coordinator)
        self._device_id = device_id
        self._device = device
        self._api = api
        self._onoff_capability = onoff_capability
        
        # Create entity name based on capability
        device_name = device.get("name", "Unknown Switch")
        if onoff_capability == "onoff":
            self._attr_name = device_name
        else:
            # Extract channel name from capability (e.g., "onoff.output1" -> "Output 1")
            channel = onoff_capability.replace("onoff.", "").replace("_", " ").title()
            self._attr_name = f"{device_name} {channel}"
        
        # Create unique ID based on capability
        if onoff_capability == "onoff":
            self._attr_unique_id = f"homey_{device_id}_onoff"
        else:
            # Use capability ID in unique_id (e.g., "homey_{device_id}_onoff.output1")
            self._attr_unique_id = f"homey_{device_id}_{onoff_capability}"
        
        self._attr_device_info = get_device_info(device_id, device, zones)

    @property
    def is_on(self) -> bool | None:
        """Return true if switch is on."""
        device_data = self.coordinator.data.get(self._device_id, self._device)
        if not device_data:
            return None
        
        capabilities = device_data.get("capabilitiesObj", {})
        onoff_cap = capabilities.get(self._onoff_capability)
        if not onoff_cap:
            return None
        
        return onoff_cap.get("value", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._api.set_capability_value(self._device_id, self._onoff_capability, True)
        # Immediately refresh this device's state for instant UI feedback
        await self.coordinator.async_refresh_device(self._device_id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._api.set_capability_value(self._device_id, self._onoff_capability, False)
        # Immediately refresh this device's state for instant UI feedback
        await self.coordinator.async_refresh_device(self._device_id)

    @property
    def available(self) -> bool:
        """Return if the switch is available."""
        device_data = self.coordinator.data.get(self._device_id)
        if device_data is None:
            device_data = self._device
        
        if not device_data:
            return False
        
        capabilities = device_data.get("capabilitiesObj", {})
        return self._onoff_capability in capabilities
