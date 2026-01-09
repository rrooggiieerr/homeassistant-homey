"""Support for Homey flows and physical device buttons."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
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
    """Set up Homey flow buttons and physical device buttons from a config entry."""
    coordinator: HomeyDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    zones = hass.data[DOMAIN][entry.entry_id].get("zones", {})

    entities = []
    flow_buttons_count = 0
    device_buttons_count = 0
    
    # Add flow buttons
    flows = await api.get_flows()
    total_flows = len(flows)
    enabled_flows = 0
    disabled_flows = 0
    
    # Empty flows dict is OK - user just doesn't have flows configured or doesn't have permission
    # Permission errors are already logged by the API method
    if flows:
        _LOGGER.debug("Found %d flows from Homey", total_flows)
        for flow_id, flow in flows.items():
            flow_name = flow.get("name", "Unknown")
            flow_enabled = flow.get("enabled", False)
            if flow_enabled:
                enabled_flows += 1
                entities.append(HomeyFlowButton(coordinator, flow_id, flow, api))
                flow_buttons_count += 1
                _LOGGER.debug("Added flow button: %s (enabled)", flow_name)
            else:
                disabled_flows += 1
                _LOGGER.debug("Skipping flow: %s (disabled)", flow_name)
        
        if enabled_flows == 0 and total_flows > 0:
            _LOGGER.warning(
                "Found %d flows in Homey, but none are enabled. Enable flows in Homey to use them in Home Assistant.",
                total_flows
            )
    else:
        _LOGGER.debug("No flows found from Homey API")
    
    # Add physical device buttons
    devices = coordinator.data if coordinator.data else await api.get_devices()
    from . import filter_devices
    devices = filter_devices(devices, entry.data.get("device_filter"))
    
    for device_id, device in devices.items():
        capabilities = device.get("capabilitiesObj", {})
        # Check for button capabilities (button, button.1, button.2, etc.)
        # Exclude internal Homey capabilities that shouldn't be exposed as buttons
        for capability_id in capabilities:
            if capability_id == "button" or capability_id.startswith("button."):
                # Skip internal Homey capabilities (migration, reset, identify, etc.)
                capability_lower = capability_id.lower()
                if any(keyword in capability_lower for keyword in ["migrate", "reset", "identify"]):
                    _LOGGER.debug("Skipping internal Homey capability: %s", capability_id)
                    continue
                entities.append(HomeyDeviceButton(coordinator, device_id, device, capability_id, api, zones))
                device_buttons_count += 1

    if entities:
        _LOGGER.info(
            "Created %d Homey button entities (%d flow buttons from %d total flows, %d device buttons)",
            len(entities), flow_buttons_count, total_flows, device_buttons_count
        )
    else:
        _LOGGER.info("No Homey button entities created (flows: %d total, %d enabled; device buttons: %d)", 
                     total_flows, enabled_flows, device_buttons_count)
    
    async_add_entities(entities)


class HomeyFlowButton(CoordinatorEntity, ButtonEntity):
    """Representation of a Homey flow as a Home Assistant button."""

    def __init__(
        self,
        coordinator: HomeyDataUpdateCoordinator,
        flow_id: str,
        flow: dict[str, Any],
        api,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._flow_id = flow_id
        self._flow = flow
        self._api = api
        self._attr_name = flow.get("name", "Unknown Flow")
        self._attr_unique_id = f"homey_{flow_id}_flow"
        self._attr_icon = "mdi:play-circle-outline"

        self._attr_device_info = {
            "identifiers": {(DOMAIN, "flows")},
            "name": "Homey Flows",
            "manufacturer": "Athom",
            "model": "Homey",
        }

    async def async_press(self) -> None:
        """Handle the button press - trigger the Homey flow."""
        success = await self._api.trigger_flow(self._flow_id)
        if not success:
            _LOGGER.error("Failed to trigger Homey flow: %s", self._attr_name)


class HomeyDeviceButton(CoordinatorEntity, ButtonEntity):
    """Representation of a physical device button."""

    def __init__(
        self,
        coordinator: HomeyDataUpdateCoordinator,
        device_id: str,
        device: dict[str, Any],
        capability_id: str,
        api,
        zones: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        """Initialize the device button."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._device = device
        self._capability_id = capability_id
        self._api = api
        
        # Create button name
        device_name = device.get("name", "Unknown Device")
        if capability_id == "button":
            button_name = f"{device_name} Button"
        else:
            # Extract button number (e.g., "button.1" -> "1")
            button_num = capability_id.replace("button.", "")
            button_name = f"{device_name} Button {button_num}"
        
        self._attr_name = button_name
        self._attr_unique_id = f"homey_{device_id}_{capability_id}"
        self._attr_icon = "mdi:gesture-tap-button"
        
        self._attr_device_info = get_device_info(device_id, device, zones)

    async def async_press(self) -> None:
        """Handle the button press - trigger the button capability."""
        # Set button capability to True to trigger the button press
        success = await self._api.set_capability_value(self._device_id, self._capability_id, True)
        if not success:
            _LOGGER.error("Failed to trigger button %s on device %s", self._capability_id, self._device_id)
        else:
            # Immediately refresh device state
            await self.coordinator.async_refresh_device(self._device_id)

