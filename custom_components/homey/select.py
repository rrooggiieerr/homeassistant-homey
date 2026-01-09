"""Support for Homey select entities."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HomeyDataUpdateCoordinator
from .device_info import get_device_info

_LOGGER = logging.getLogger(__name__)

# Capabilities that should be exposed as select entities
# These are mode/option selections
SELECT_CAPABILITIES = [
    # Add capabilities here that have options/modes
    # Example: "thermostat_mode" is handled by climate platform
    # "some_mode": {"options": ["option1", "option2", "option3"]},
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Homey select entities from a config entry."""
    coordinator: HomeyDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    zones = hass.data[DOMAIN][entry.entry_id].get("zones", {})

    entities = []
    devices = coordinator.data if coordinator.data else await api.get_devices()
    
    # Filter devices if device_filter is configured
    from . import filter_devices
    devices = filter_devices(devices, entry.data.get("device_filter"))

    for device_id, device in devices.items():
        capabilities = device.get("capabilitiesObj", {})
        # Check for capabilities that should be select entities
        # For now, this is a placeholder - add specific capabilities as needed
        for capability_id in SELECT_CAPABILITIES:
            if capability_id in capabilities:
                cap_data = capabilities[capability_id]
                # Check if capability has options
                if "values" in cap_data or "options" in cap_data:
                    entities.append(
                        HomeySelect(coordinator, device_id, device, capability_id, cap_data, api, zones)
                    )

    async_add_entities(entities)


class HomeySelect(CoordinatorEntity, SelectEntity):
    """Representation of a Homey select entity."""

    def __init__(
        self,
        coordinator: HomeyDataUpdateCoordinator,
        device_id: str,
        device: dict[str, Any],
        capability_id: str,
        capability_data: dict[str, Any],
        api,
        zones: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._device = device
        self._capability_id = capability_id
        self._capability_data = capability_data
        self._api = api
        
        device_name = device.get("name", "Unknown Device")
        self._attr_name = f"{device_name} {capability_id.replace('_', ' ').title()}"
        self._attr_unique_id = f"homey_{device_id}_{capability_id}"
        
        # Get options from capability data
        options = capability_data.get("values") or capability_data.get("options", [])
        if isinstance(options, list):
            self._attr_options = [str(opt) for opt in options]
        elif isinstance(options, dict):
            # If it's a dict, use the keys or values
            self._attr_options = [str(opt) for opt in options.keys()]
        else:
            self._attr_options = []
        
        self._attr_device_info = get_device_info(device_id, device, zones)

    @property
    def current_option(self) -> str | None:
        """Return the currently selected option."""
        device_data = self.coordinator.data.get(self._device_id, self._device)
        capabilities = device_data.get("capabilitiesObj", {})
        value = capabilities.get(self._capability_id, {}).get("value")
        if value is not None:
            return str(value)
        return None

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        success = await self._api.set_capability_value(self._device_id, self._capability_id, option)
        if success:
            _LOGGER.debug("Successfully set %s to %s for device %s", self._capability_id, option, self._device_id)
            await self.coordinator.async_refresh_device(self._device_id)
        else:
            _LOGGER.error("Failed to set %s to %s for device %s", self._capability_id, option, self._device_id)
