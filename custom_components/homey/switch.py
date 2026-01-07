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

    for device_id, device in devices.items():
        capabilities = device.get("capabilitiesObj", {})
        # Only create switch entities for devices with onoff that are NOT lights
        # (lights should be handled by the light platform)
        if "onoff" in capabilities:
            # Skip if this device should be a light
            has_light_capabilities = (
                "dim" in capabilities
                or "light_hue" in capabilities
                or "light_temperature" in capabilities
            )
            # Skip if this device should be a fan
            has_fan_capabilities = "fan_speed" in capabilities
            # Skip if this device should be a cover
            has_cover_capabilities = "windowcoverings_state" in capabilities
            # Skip if this device should be a media player
            has_media_capabilities = any(
                cap in capabilities
                for cap in ["volume_set", "speaker_playing", "speaker_next"]
            )
            
            # Only create switch if it's not a specialized device type
            if not (
                has_light_capabilities
                or has_fan_capabilities
                or has_cover_capabilities
                or has_media_capabilities
            ):
                entities.append(HomeySwitch(coordinator, device_id, device, api, zones))

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
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._device = device
        self._api = api
        self._attr_name = device.get("name", "Unknown Switch")
        self._attr_unique_id = f"homey_{device_id}_onoff"
        self._attr_device_info = get_device_info(device_id, device, zones)

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        device_data = self.coordinator.data.get(self._device_id, self._device)
        capabilities = device_data.get("capabilitiesObj", {})
        return capabilities.get("onoff", {}).get("value", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._api.set_capability_value(self._device_id, "onoff", True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._api.set_capability_value(self._device_id, "onoff", False)
        await self.coordinator.async_request_refresh()

