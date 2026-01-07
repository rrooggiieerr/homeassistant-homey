"""Support for Homey lights."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
import homeassistant.util.color as color_util

from .const import DOMAIN
from .coordinator import HomeyDataUpdateCoordinator
from .device_info import get_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Homey lights from a config entry."""
    coordinator: HomeyDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    zones = hass.data[DOMAIN][entry.entry_id].get("zones", {})

    entities = []
    # Use coordinator data if available (more up-to-date), otherwise fetch fresh
    devices = coordinator.data if coordinator.data else await api.get_devices()

    for device_id, device in devices.items():
        capabilities = device.get("capabilitiesObj", {})
        # Check if device has light-related capabilities
        if "onoff" in capabilities and (
            "dim" in capabilities
            or "light_hue" in capabilities
            or "light_temperature" in capabilities
        ):
            entities.append(HomeyLight(coordinator, device_id, device, api, zones))

    async_add_entities(entities)


class HomeyLight(CoordinatorEntity, LightEntity):
    """Representation of a Homey light."""

    def __init__(
        self,
        coordinator: HomeyDataUpdateCoordinator,
        device_id: str,
        device: dict[str, Any],
        api,
        zones: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        """Initialize the light."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._device = device
        self._api = api
        self._attr_name = device.get("name", "Unknown Light")
        self._attr_unique_id = f"homey_{device_id}_light"

        capabilities = device.get("capabilitiesObj", {})
        # Determine supported color modes
        # Note: HS and COLOR_TEMP cannot be combined - if both are available, prefer HS
        color_modes = set()
        has_dim = "dim" in capabilities
        has_hs = "light_hue" in capabilities and "light_saturation" in capabilities
        has_temp = "light_temperature" in capabilities
        
        if has_hs:
            # If HS color is available, use it (can't combine with COLOR_TEMP)
            color_modes.add(ColorMode.HS)
            if has_dim:
                color_modes.add(ColorMode.BRIGHTNESS)
        elif has_temp:
            # If only color temp is available, use it
            color_modes.add(ColorMode.COLOR_TEMP)
            if has_dim:
                color_modes.add(ColorMode.BRIGHTNESS)
        elif has_dim:
            # Only dimming available
            color_modes.add(ColorMode.BRIGHTNESS)
        else:
            # Just on/off
            color_modes.add(ColorMode.ONOFF)

        self._attr_supported_color_modes = color_modes
        self._attr_color_mode = next(iter(color_modes)) if color_modes else ColorMode.ONOFF
        
        # Set color temperature range in Kelvin (required for COLOR_TEMP mode)
        if ColorMode.COLOR_TEMP in color_modes:
            temp_cap = capabilities.get("light_temperature", {})
            # Default range: 2000K (warm) to 6500K (cool)
            self._attr_min_color_temp_kelvin = temp_cap.get("min", 2000)
            self._attr_max_color_temp_kelvin = temp_cap.get("max", 6500)

        self._attr_device_info = get_device_info(device_id, device, zones)

    @property
    def is_on(self) -> bool:
        """Return true if light is on."""
        device_data = self.coordinator.data.get(self._device_id, self._device)
        capabilities = device_data.get("capabilitiesObj", {})
        return capabilities.get("onoff", {}).get("value", False)

    @property
    def brightness(self) -> int | None:
        """Return the brightness of the light."""
        device_data = self.coordinator.data.get(self._device_id, self._device)
        capabilities = device_data.get("capabilitiesObj", {})
        dim_value = capabilities.get("dim", {}).get("value", 0)
        if dim_value is not None:
            return int(dim_value * 255)
        return None

    @property
    def hs_color(self) -> tuple[float, float] | None:
        """Return the hue and saturation color value."""
        device_data = self.coordinator.data.get(self._device_id, self._device)
        capabilities = device_data.get("capabilitiesObj", {})
        hue = capabilities.get("light_hue", {}).get("value")
        saturation = capabilities.get("light_saturation", {}).get("value")
        if hue is not None and saturation is not None:
            return (hue, saturation)
        return None

    @property
    def color_temp_kelvin(self) -> int | None:
        """Return the color temperature in Kelvin."""
        device_data = self.coordinator.data.get(self._device_id, self._device)
        capabilities = device_data.get("capabilitiesObj", {})
        temp = capabilities.get("light_temperature", {}).get("value")
        if temp is not None:
            return int(temp)
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        capabilities_to_set = {}

        if ATTR_BRIGHTNESS in kwargs:
            brightness = kwargs[ATTR_BRIGHTNESS]
            capabilities_to_set["dim"] = brightness / 255.0

        if ATTR_HS_COLOR in kwargs:
            hs_color = kwargs[ATTR_HS_COLOR]
            capabilities_to_set["light_hue"] = hs_color[0]
            capabilities_to_set["light_saturation"] = hs_color[1]

        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
            capabilities_to_set["light_temperature"] = kelvin

        # Always turn on if not already on
        if not self.is_on:
            await self._api.set_capability_value(self._device_id, "onoff", True)

        # Set other capabilities
        for capability, value in capabilities_to_set.items():
            await self._api.set_capability_value(self._device_id, capability, value)

        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        await self._api.set_capability_value(self._device_id, "onoff", False)
        await self.coordinator.async_request_refresh()

