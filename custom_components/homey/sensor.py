"""Support for Homey sensors."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfEnergy,
    UnitOfPower,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfFrequency,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HomeyDataUpdateCoordinator
from .device_info import get_device_info

_LOGGER = logging.getLogger(__name__)

# Mapping of Homey capabilities to HA sensor attributes
CAPABILITY_TO_SENSOR = {
    "measure_temperature": {
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTemperature.CELSIUS,
    },
    "measure_humidity": {
        "device_class": SensorDeviceClass.HUMIDITY,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "%",
    },
    "measure_pressure": {
        "device_class": SensorDeviceClass.PRESSURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPressure.HPA,
    },
    "measure_power": {
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.WATT,
    },
    "measure_voltage": {
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "V",  # Volts - UnitOfVoltage may not be available in all HA versions
    },
    "measure_current": {
        "device_class": SensorDeviceClass.CURRENT,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "A",
    },
    "measure_luminance": {
        "device_class": SensorDeviceClass.ILLUMINANCE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "lx",
    },
    "measure_co2": {
        "device_class": SensorDeviceClass.CO2,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "ppm",
    },
    "measure_co": {
        "device_class": SensorDeviceClass.CO,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "ppm",
    },
    # Additional sensor capabilities
    "measure_noise": {
        "device_class": SensorDeviceClass.SOUND_PRESSURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "dB",
    },
    "measure_rain": {
        "device_class": None,  # Generic sensor
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "mm",
    },
    "measure_wind_strength": {
        "device_class": None,  # Generic sensor
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "m/s",
    },
    "measure_wind_angle": {
        "device_class": None,  # Generic sensor
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "°",
    },
    "measure_ultraviolet": {
        "device_class": None,  # Generic sensor
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "UV index",
    },
    "measure_pm25": {
        "device_class": SensorDeviceClass.PM25,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "µg/m³",
    },
    "measure_pm10": {
        "device_class": SensorDeviceClass.PM10,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "µg/m³",
    },
    "measure_voc": {
        "device_class": None,  # Generic sensor
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "µg/m³",
    },
    "measure_aqi": {
        "device_class": None,  # Generic sensor
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "AQI",
    },
    "measure_frequency": {
        "device_class": None,  # Generic sensor
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfFrequency.HERTZ,
    },
    "measure_gas": {
        "device_class": None,  # Generic sensor
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "ppm",
    },
    "measure_soil_moisture": {
        "device_class": None,  # Generic sensor
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "%",
    },
    "measure_soil_temperature": {
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTemperature.CELSIUS,
    },
    "measure_energy": {
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,  # For energy consumption
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Homey sensors from a config entry."""
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
        for capability_id in CAPABILITY_TO_SENSOR:
            if capability_id in capabilities:
                entities.append(
                    HomeySensor(coordinator, device_id, device, capability_id, api, zones)
                )

    async_add_entities(entities)


class HomeySensor(CoordinatorEntity, SensorEntity):
    """Representation of a Homey sensor."""

    def __init__(
        self,
        coordinator: HomeyDataUpdateCoordinator,
        device_id: str,
        device: dict[str, Any],
        capability_id: str,
        api,
        zones: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._device = device
        self._capability_id = capability_id
        self._api = api

        sensor_config = CAPABILITY_TO_SENSOR[capability_id]
        self._attr_name = f"{device.get('name', 'Unknown')} {capability_id.replace('measure_', '').replace('_', ' ').title()}"
        self._attr_unique_id = f"homey_{device_id}_{capability_id}"
        self._attr_device_class = sensor_config.get("device_class")
        self._attr_state_class = sensor_config.get("state_class")
        self._attr_native_unit_of_measurement = sensor_config.get("unit")

        self._attr_device_info = get_device_info(device_id, device, zones)

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        device_data = self.coordinator.data.get(self._device_id, self._device)
        capabilities = device_data.get("capabilitiesObj", {})
        capability = capabilities.get(self._capability_id, {})
        value = capability.get("value")
        if value is None:
            return None
        
        try:
            value_float = float(value)
            
            # Check if this is a percentage sensor that might be normalized
            # measure_humidity and measure_soil_moisture might return normalized 0-1
            if self._capability_id in ("measure_humidity", "measure_soil_moisture"):
                # Check capability max to determine if normalized
                cap_max = capability.get("max", 100)
                if cap_max <= 1.0:
                    # Normalized value (0-1), convert to percentage (0-100)
                    value_float = value_float * 100.0
            
            return value_float
        except (ValueError, TypeError):
            return None

