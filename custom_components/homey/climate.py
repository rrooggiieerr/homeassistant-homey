"""Support for Homey climate devices."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
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
    """Set up Homey climate devices from a config entry."""
    coordinator: HomeyDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    zones = hass.data[DOMAIN][entry.entry_id].get("zones", {})

    entities = []
    # Use coordinator data if available (more up-to-date), otherwise fetch fresh
    devices = coordinator.data if coordinator.data else await api.get_devices()

    for device_id, device in devices.items():
        capabilities = device.get("capabilitiesObj", {})
        if "target_temperature" in capabilities:
            entities.append(HomeyClimate(coordinator, device_id, device, api, zones))

    async_add_entities(entities)


class HomeyClimate(CoordinatorEntity, ClimateEntity):
    """Representation of a Homey climate device."""

    def __init__(
        self,
        coordinator: HomeyDataUpdateCoordinator,
        device_id: str,
        device: dict[str, Any],
        api,
        zones: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        """Initialize the climate device."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._device = device
        self._api = api
        self._attr_name = device.get("name", "Unknown Climate")
        self._attr_unique_id = f"homey_{device_id}_climate"
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE

        capabilities = device.get("capabilitiesObj", {})
        # Determine HVAC modes based on available capabilities
        hvac_modes = [HVACMode.HEAT_COOL]
        if "onoff" in capabilities:
            hvac_modes.append(HVACMode.OFF)
        self._attr_hvac_modes = hvac_modes
        self._attr_hvac_mode = HVACMode.HEAT_COOL

        # Get temperature range from capability
        target_temp_cap = capabilities.get("target_temperature", {})
        if "min" in target_temp_cap:
            self._attr_min_temp = target_temp_cap["min"]
        if "max" in target_temp_cap:
            self._attr_max_temp = target_temp_cap["max"]

        self._attr_device_info = get_device_info(device_id, device, zones)

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        device_data = self.coordinator.data.get(self._device_id, self._device)
        capabilities = device_data.get("capabilitiesObj", {})
        temp = capabilities.get("measure_temperature", {}).get("value")
        return float(temp) if temp is not None else None

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        device_data = self.coordinator.data.get(self._device_id, self._device)
        capabilities = device_data.get("capabilitiesObj", {})
        temp = capabilities.get("target_temperature", {}).get("value")
        return float(temp) if temp is not None else None

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        if "temperature" in kwargs:
            await self._api.set_capability_value(
                self._device_id, "target_temperature", kwargs["temperature"]
            )
            await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        if hvac_mode == HVACMode.OFF:
            device_data = self.coordinator.data.get(self._device_id, self._device)
            capabilities = device_data.get("capabilitiesObj", {})
            if "onoff" in capabilities:
                await self._api.set_capability_value(self._device_id, "onoff", False)
        else:
            device_data = self.coordinator.data.get(self._device_id, self._device)
            capabilities = device_data.get("capabilitiesObj", {})
            if "onoff" in capabilities:
                await self._api.set_capability_value(self._device_id, "onoff", True)
        await self.coordinator.async_request_refresh()

