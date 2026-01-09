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
    
    # Filter devices if device_filter is configured
    from . import filter_devices
    devices = filter_devices(devices, entry.data.get("device_filter"))

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
        capabilities = device.get("capabilitiesObj", {})
        supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
        
        # Add humidity support if available
        if "target_humidity" in capabilities:
            supported_features |= ClimateEntityFeature.TARGET_HUMIDITY
        
        self._attr_supported_features = supported_features
        hvac_modes = []
        
        # Check for thermostat mode capabilities
        has_mode_off = "thermostat_mode_off" in capabilities
        has_mode_heat = "thermostat_mode_heat" in capabilities
        has_mode_cool = "thermostat_mode_cool" in capabilities
        has_mode_auto = "thermostat_mode_auto" in capabilities
        has_mode = "thermostat_mode" in capabilities
        
        # If we have specific mode capabilities, use them
        if has_mode_off or has_mode_heat or has_mode_cool or has_mode_auto or has_mode:
            if has_mode_off or has_mode:
                hvac_modes.append(HVACMode.OFF)
            if has_mode_heat or has_mode:
                hvac_modes.append(HVACMode.HEAT)
            if has_mode_cool or has_mode:
                hvac_modes.append(HVACMode.COOL)
            if has_mode_auto or has_mode:
                hvac_modes.append(HVACMode.AUTO)
            # If we have multiple modes but not AUTO, add HEAT_COOL as fallback
            if not has_mode_auto and (has_mode_heat and has_mode_cool):
                hvac_modes.append(HVACMode.HEAT_COOL)
        else:
            # Fallback to original behavior: HEAT_COOL mode
            hvac_modes = [HVACMode.HEAT_COOL]
            if "onoff" in capabilities:
                hvac_modes.append(HVACMode.OFF)
        
        # Ensure we have at least one mode
        if not hvac_modes:
            hvac_modes = [HVACMode.HEAT_COOL]
        
        self._attr_hvac_modes = hvac_modes
        # Set initial mode - prefer AUTO if available, otherwise HEAT_COOL, otherwise first mode
        if HVACMode.AUTO in hvac_modes:
            self._attr_hvac_mode = HVACMode.AUTO
        elif HVACMode.HEAT_COOL in hvac_modes:
            self._attr_hvac_mode = HVACMode.HEAT_COOL
        else:
            self._attr_hvac_mode = hvac_modes[0]

        # Get temperature range from capability
        # Home Assistant requires min/max temp to show temperature controls
        target_temp_cap = capabilities.get("target_temperature", {})
        if "min" in target_temp_cap:
            self._attr_min_temp = target_temp_cap["min"]
        else:
            # Default to reasonable range if not provided by Homey
            self._attr_min_temp = 5.0  # 5°C minimum
        
        if "max" in target_temp_cap:
            self._attr_max_temp = target_temp_cap["max"]
        else:
            # Default to reasonable range if not provided by Homey
            self._attr_max_temp = 35.0  # 35°C maximum
        
        # Also set temperature step if available (for slider precision)
        if "step" in target_temp_cap:
            self._attr_target_temperature_step = target_temp_cap["step"]
        else:
            # Default to 0.5°C steps
            self._attr_target_temperature_step = 0.5

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

    @property
    def current_humidity(self) -> int | None:
        """Return the current humidity."""
        device_data = self.coordinator.data.get(self._device_id, self._device)
        capabilities = device_data.get("capabilitiesObj", {})
        humidity_cap = capabilities.get("measure_humidity", {})
        humidity = humidity_cap.get("value")
        if humidity is not None:
            try:
                humidity_float = float(humidity)
                # Check capability max to determine if normalized (0-1) or percentage (0-100)
                # If max <= 1, it's normalized and needs conversion
                cap_max = humidity_cap.get("max", 100)
                if cap_max <= 1.0:
                    # Normalized value (0-1), convert to percentage (0-100)
                    humidity_float = humidity_float * 100.0
                return int(humidity_float)
            except (ValueError, TypeError):
                return None
        return None

    @property
    def target_humidity(self) -> int | None:
        """Return the target humidity."""
        device_data = self.coordinator.data.get(self._device_id, self._device)
        capabilities = device_data.get("capabilitiesObj", {})
        humidity_cap = capabilities.get("target_humidity", {})
        humidity = humidity_cap.get("value")
        if humidity is not None:
            try:
                humidity_float = float(humidity)
                # Check capability max to determine if normalized (0-1) or percentage (0-100)
                # If max <= 1, it's normalized and needs conversion
                cap_max = humidity_cap.get("max", 100)
                if cap_max <= 1.0:
                    # Normalized value (0-1), convert to percentage (0-100)
                    humidity_float = humidity_float * 100.0
                return int(humidity_float)
            except (ValueError, TypeError):
                return None
        return None

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temperature = None
        
        # Handle different temperature parameter formats
        if "temperature" in kwargs:
            temperature = kwargs["temperature"]
        elif "target_temperature_high" in kwargs and "target_temperature_low" in kwargs:
            # For HEAT_COOL mode, Home Assistant may pass high/low values
            # Use the high value (or average) since Homey typically uses a single target
            high = kwargs.get("target_temperature_high")
            low = kwargs.get("target_temperature_low")
            if high is not None and low is not None:
                # Use average for HEAT_COOL mode, or just high if that makes more sense
                temperature = (float(high) + float(low)) / 2.0
                _LOGGER.debug(
                    "HEAT_COOL mode: using average of high=%s and low=%s -> %s for device %s",
                    high, low, temperature, self._device_id
                )
        elif "target_temperature_high" in kwargs:
            temperature = kwargs["target_temperature_high"]
        elif "target_temperature_low" in kwargs:
            temperature = kwargs["target_temperature_low"]
        
        if temperature is None:
            _LOGGER.warning(
                "No temperature parameter found in kwargs: %s for device %s",
                list(kwargs.keys()), self._device_id
            )
            return
        
        # Ensure temperature is numeric
        try:
            if not isinstance(temperature, (int, float)):
                temperature = float(temperature)
        except (ValueError, TypeError):
            _LOGGER.error(
                "Invalid temperature value: %s for device %s",
                temperature, self._device_id
            )
            return
        
        _LOGGER.debug(
            "Setting target temperature to %s for device %s (%s)",
            temperature, self._device_id, self._attr_name
        )
        
        # Set the capability value and check if it succeeded
        success = await self._api.set_capability_value(
            self._device_id, "target_temperature", temperature
        )
        
        if success:
            _LOGGER.info(
                "Successfully set target temperature to %s°C for device %s (%s)",
                temperature, self._device_id, self._attr_name
            )
            # Immediately refresh this device's state for instant UI feedback
            await self.coordinator.async_refresh_device(self._device_id)
        else:
            _LOGGER.error(
                "Failed to set target temperature to %s°C for device %s (%s). "
                "Check API permissions (homey.device.control) and device capabilities.",
                temperature,
                self._device_id,
                self._attr_name,
            )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        device_data = self.coordinator.data.get(self._device_id, self._device)
        capabilities = device_data.get("capabilitiesObj", {})
        
        # Check if device has thermostat_mode capability
        if "thermostat_mode" in capabilities:
            # Map HVACMode to Homey thermostat mode values
            mode_mapping = {
                HVACMode.OFF: "off",
                HVACMode.HEAT: "heat",
                HVACMode.COOL: "cool",
                HVACMode.AUTO: "auto",
                HVACMode.HEAT_COOL: "auto",  # Fallback to auto if HEAT_COOL not supported
            }
            mode_value = mode_mapping.get(hvac_mode)
            if mode_value:
                await self._api.set_capability_value(self._device_id, "thermostat_mode", mode_value)
        elif hvac_mode == HVACMode.OFF:
            # Fallback to onoff capability if thermostat_mode not available
            if "onoff" in capabilities:
                await self._api.set_capability_value(self._device_id, "onoff", False)
        else:
            # Turn on if not OFF mode
            if "onoff" in capabilities:
                await self._api.set_capability_value(self._device_id, "onoff", True)
        
        # Immediately refresh this device's state for instant UI feedback
        await self.coordinator.async_refresh_device(self._device_id)

    async def async_set_humidity(self, humidity: int) -> None:
        """Set new target humidity."""
        capabilities = self._device.get("capabilitiesObj", {})
        humidity_cap = capabilities.get("target_humidity", {})
        if humidity_cap:
            try:
                # Check capability max to determine if normalized (0-1) or percentage (0-100)
                # If max <= 1, it's normalized and needs conversion
                cap_max = humidity_cap.get("max", 100)
                if cap_max <= 1.0:
                    # Homey uses normalized 0-1, convert from percentage (0-100)
                    humidity_value = float(humidity) / 100.0
                else:
                    # Homey uses percentage 0-100, use as-is
                    humidity_value = float(humidity)
                
                success = await self._api.set_capability_value(
                    self._device_id, "target_humidity", humidity_value
                )
                if success:
                    _LOGGER.debug("Successfully set target humidity to %s for device %s", humidity, self._device_id)
                    await self.coordinator.async_refresh_device(self._device_id)
                else:
                    _LOGGER.error(
                        "Failed to set target humidity to %s for device %s. Check API permissions and device capabilities.",
                        humidity,
                        self._device_id,
                    )
            except (ValueError, TypeError) as err:
                _LOGGER.error("Invalid humidity value: %s (%s)", humidity, err)
