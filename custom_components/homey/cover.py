"""Support for Homey covers."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.cover import CoverEntity, CoverEntityFeature
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
    """Set up Homey covers from a config entry."""
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
        # Support windowcoverings_state, windowcoverings_set, and garagedoor_closed capabilities
        # Reference: https://apps.developer.homey.app/the-basics/devices/capabilities
        # Note: Some devices use windowcoverings_set instead of windowcoverings_state
        if any(cap in capabilities for cap in ["windowcoverings_state", "windowcoverings_set", "garagedoor_closed"]):
            entities.append(HomeyCover(coordinator, device_id, device, api, zones))

    async_add_entities(entities)


class HomeyCover(CoordinatorEntity, CoverEntity):
    """Representation of a Homey cover."""

    def __init__(
        self,
        coordinator: HomeyDataUpdateCoordinator,
        device_id: str,
        device: dict[str, Any],
        api,
        zones: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        """Initialize the cover."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._device = device
        self._api = api
        self._attr_name = device.get("name", "Unknown Cover")
        self._attr_unique_id = f"homey_{device_id}_cover"

        capabilities = device.get("capabilitiesObj", {})
        
        # Check if device uses windowcoverings_state, windowcoverings_set, or garagedoor_closed
        # Some devices use windowcoverings_set instead of windowcoverings_state
        self._has_windowcoverings = "windowcoverings_state" in capabilities or "windowcoverings_set" in capabilities
        self._has_garagedoor = "garagedoor_closed" in capabilities
        # Determine which capability to use (prefer windowcoverings_state, fallback to windowcoverings_set)
        self._windowcoverings_cap = "windowcoverings_state" if "windowcoverings_state" in capabilities else "windowcoverings_set"
        
        supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
        
        # Garage doors don't support position setting, only open/close
        if self._has_windowcoverings:
            supported_features |= CoverEntityFeature.SET_COVER_POSITION

        if "windowcoverings_tilt_up" in capabilities and "windowcoverings_tilt_down" in capabilities:
            supported_features |= CoverEntityFeature.SET_TILT_POSITION | CoverEntityFeature.OPEN_TILT | CoverEntityFeature.CLOSE_TILT

        self._attr_supported_features = supported_features

        self._attr_device_info = get_device_info(device_id, device, zones)

    @property
    def current_cover_position(self) -> int | None:
        """Return current position of cover."""
        device_data = self.coordinator.data.get(self._device_id, self._device)
        if not device_data:
            return None
        
        capabilities = device_data.get("capabilitiesObj", {})
        if not capabilities:
            return None
        
        # Handle windowcoverings_state, windowcoverings_set, and garagedoor_closed
        if self._has_windowcoverings:
            state_cap = capabilities.get(self._windowcoverings_cap)
            if not state_cap:
                return None
            
            state = state_cap.get("value")
            if state is None:
                return None
            
            try:
                # Convert state (0-1) to percentage (0-100)
                # Note: windowcoverings_set uses 0-1 range, windowcoverings_state also uses 0-1
                state_float = float(state)
                return int(state_float * 100)
            except (ValueError, TypeError):
                _LOGGER.warning("Invalid %s value for device %s: %s", self._windowcoverings_cap, self._device_id, state)
                return None
        elif self._has_garagedoor:
            # Garage door: closed = True means closed (position 0), False means open (position 100)
            garagedoor_cap = capabilities.get("garagedoor_closed")
            if not garagedoor_cap:
                return None
            
            is_closed = garagedoor_cap.get("value")
            if is_closed is None:
                return None
            
            # Convert boolean to position: True (closed) = 0%, False (open) = 100%
            return 0 if is_closed else 100
        
        return None

    @property
    def is_closed(self) -> bool | None:
        """Return if the cover is closed."""
        position = self.current_cover_position
        if position is None:
            return None
        return position == 0
    
    @property
    def available(self) -> bool:
        """Return if the cover is available."""
        # Entity is available if device exists in coordinator data
        # Position can be None initially, but device should still be available
        device_data = self.coordinator.data.get(self._device_id)
        if device_data is None:
            # Fall back to initial device data
            device_data = self._device
        
        if not device_data:
            return False
        
        # Check if device has cover capabilities
        capabilities = device_data.get("capabilitiesObj", {})
        return any(cap in capabilities for cap in ["windowcoverings_state", "windowcoverings_set", "garagedoor_closed"])

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        if self._has_windowcoverings:
            await self._api.set_capability_value(self._device_id, self._windowcoverings_cap, 1.0)
        elif self._has_garagedoor:
            await self._api.set_capability_value(self._device_id, "garagedoor_closed", False)
        # Immediately refresh this device's state for instant UI feedback
        await self.coordinator.async_refresh_device(self._device_id)

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        if self._has_windowcoverings:
            await self._api.set_capability_value(self._device_id, self._windowcoverings_cap, 0.0)
        elif self._has_garagedoor:
            await self._api.set_capability_value(self._device_id, "garagedoor_closed", True)
        # Immediately refresh this device's state for instant UI feedback
        await self.coordinator.async_refresh_device(self._device_id)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        # Get current position and set it again to stop
        position = self.current_cover_position
        if position is not None:
            await self._api.set_capability_value(
                self._device_id, "windowcoverings_state", position / 100.0
            )
        # Immediately refresh this device's state for instant UI feedback
        await self.coordinator.async_refresh_device(self._device_id)

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Move the cover to a specific position."""
        position = kwargs.get("position", 0)
        if self._has_windowcoverings:
            await self._api.set_capability_value(
                self._device_id, self._windowcoverings_cap, position / 100.0
            )
        elif self._has_garagedoor:
            # Garage doors are binary - convert position to boolean
            # Position > 50% = open (False), <= 50% = closed (True)
        await self._api.set_capability_value(
                self._device_id, "garagedoor_closed", position <= 50
        )
        # Immediately refresh this device's state for instant UI feedback
        await self.coordinator.async_refresh_device(self._device_id)

