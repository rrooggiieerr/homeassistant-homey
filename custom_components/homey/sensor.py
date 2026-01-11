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
    # Meter capabilities (energy/utility meters)
    # Reference: https://apps.developer.homey.app/the-basics/devices/capabilities
    "meter_power": {
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,  # Cumulative energy consumption
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
    },
    "meter_water": {
        "device_class": None,  # Generic sensor - water meter
        "state_class": SensorStateClass.TOTAL_INCREASING,  # Cumulative water consumption
        "unit": "m³",  # Cubic meters
    },
    "meter_gas": {
        "device_class": None,  # Generic sensor - gas meter
        "state_class": SensorStateClass.TOTAL_INCREASING,  # Cumulative gas consumption
        "unit": "m³",  # Cubic meters
    },
    # Additional measure_* capabilities that might exist
    "measure_battery": {
        "device_class": SensorDeviceClass.BATTERY,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "%",
    },
    "measure_wind_speed": {  # Alternative name for wind_strength
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "m/s",
    },
    "measure_wind_direction": {  # Alternative name for wind_angle
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "°",
    },
    "measure_light": {  # Alternative name for luminance
        "device_class": SensorDeviceClass.ILLUMINANCE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "lx",
    },
    "measure_illuminance": {  # Alternative name for luminance
        "device_class": SensorDeviceClass.ILLUMINANCE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "lx",
    },
    # Tibber price sensors
    "measure_price_level": {
        "device_class": None,  # Price level (low/normal/high)
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": None,  # Unitless - just a level indicator
    },
    "measure_price_info_level": {
        "device_class": None,  # Price info level
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": None,  # Unitless
    },
    "measure_price_lowest": {
        "device_class": None,  # Lowest price
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": None,  # Will be set from capability data (e.g., SEK/kWh)
    },
    "measure_price_highest": {
        "device_class": None,  # Highest price
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": None,  # Will be set from capability data (e.g., SEK/kWh)
    },
    "measure_price_total": {
        "device_class": None,  # Total price
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": None,  # Will be set from capability data (e.g., SEK/kWh)
    },
    # Tibber cost/energy sensors
    "accumulatedCost": {
        "device_class": None,  # Accumulated cost
        "state_class": SensorStateClass.TOTAL_INCREASING,  # Cumulative cost
        "unit": None,  # Will be set from capability data (e.g., SEK, ¤)
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
        
        # First, handle explicitly mapped capabilities
        for capability_id in CAPABILITY_TO_SENSOR:
            if capability_id in capabilities:
                entities.append(
                    HomeySensor(coordinator, device_id, device, capability_id, api, zones)
                )
        
        # Then, handle ALL measure_* and meter_* capabilities generically (including unknown ones)
        # This ensures we support new device types and capabilities automatically
        # Reference: https://apps.developer.homey.app/the-basics/devices/capabilities#sub-capabilities-using-the-same-capability-more-than-once
        for capability_id in capabilities:
            # Skip if already handled above
            if capability_id in CAPABILITY_TO_SENSOR:
                continue
            
            # Skip enum-type capabilities - they should be select entities, not sensors
            cap_data = capabilities.get(capability_id, {})
            if cap_data.get("type") == "enum":
                _LOGGER.debug("Skipping enum capability %s - should be handled by select platform", capability_id)
                continue
            
            # Check if this is a measure_* or meter_* capability (including sub-capabilities)
            is_measure = capability_id.startswith("measure_")
            is_meter = capability_id.startswith("meter_")
            is_accumulated_cost = capability_id == "accumulatedCost"
            
            if is_measure or is_meter or is_accumulated_cost:
                # Skip internal Homey maintenance buttons (same logic as button.py)
                capability_lower = capability_id.lower()
                if any(keyword in capability_lower for keyword in ["migrate", "reset", "identify"]):
                    _LOGGER.debug("Skipping internal Homey maintenance capability: %s", capability_id)
                    continue
                
                # Check if it's a sub-capability of a known capability
                if "." in capability_id:
                    base_capability = capability_id.split(".")[0]
                    # If base is known, use its config; otherwise create generic sensor
                    if base_capability in CAPABILITY_TO_SENSOR:
                        entities.append(
                            HomeySensor(coordinator, device_id, device, capability_id, api, zones)
                        )
                    else:
                        # Unknown base capability - create generic sensor
                        entities.append(
                            HomeySensor(coordinator, device_id, device, capability_id, api, zones)
                        )
                else:
                    # Unknown top-level capability - create generic sensor
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

        # Handle sub-capabilities (e.g., measure_temperature.inside, meter_power.imported)
        base_capability = capability_id.split(".")[0] if "." in capability_id else capability_id
        sensor_config = CAPABILITY_TO_SENSOR.get(base_capability)
        
        if not sensor_config:
            # Unknown capability - create generic sensor
            # This is expected behavior - we create sensors for all measure_* and meter_* capabilities
            _LOGGER.debug("Creating generic sensor for unknown capability: %s for device %s", capability_id, device_id)
            
            # Special handling for meter_* sub-capabilities (e.g., meter_power.imported, meter_power.exported)
            # These should be energy sensors for Energy dashboard compatibility
            if base_capability == "meter_power":
                sensor_config = {
                    "device_class": SensorDeviceClass.ENERGY,
                    "state_class": SensorStateClass.TOTAL_INCREASING,  # Cumulative energy
                    "unit": UnitOfEnergy.KILO_WATT_HOUR,
                }
            else:
                sensor_config = {
                    "device_class": None,
                    "state_class": SensorStateClass.MEASUREMENT,
                    "unit": None,
                }
        
        # Generate entity name - handle sub-capabilities
        if "." in capability_id:
            # Sub-capability: "measure_temperature.inside" -> "Inside Temperature"
            parts = capability_id.split(".")
            base_name = parts[0].replace("measure_", "").replace("meter_", "").replace("_", " ").title()
            sub_name = parts[1].replace("_", " ").title()
            self._attr_name = f"{device.get('name', 'Unknown')} {sub_name} {base_name}"
        else:
            # Regular capability
            self._attr_name = f"{device.get('name', 'Unknown')} {capability_id.replace('measure_', '').replace('meter_', '').replace('_', ' ').title()}"
        
        self._attr_unique_id = f"homey_{device_id}_{capability_id}"
        self._attr_device_class = sensor_config.get("device_class")
        self._attr_state_class = sensor_config.get("state_class")
        
        # Get unit from capability data if available (important for price sensors, etc.)
        # This ensures sensors like Tibber price sensors get their units (e.g., SEK/kWh) from Homey
        capabilities = device.get("capabilitiesObj", {})
        capability_data = capabilities.get(capability_id, {})
        unit_from_capability = capability_data.get("units")
        
        # Check if this is a price sensor that needs energy price format (currency/kWh)
        is_price_sensor = capability_id in ["measure_price_total", "measure_price_lowest", "measure_price_highest"]
        
        # Use unit from capability data if available, otherwise use configured unit
        if unit_from_capability:
            if is_price_sensor:
                # Convert currency symbol to currency code + /kWh format for Energy dashboard
                unit_normalized = self._normalize_price_unit(unit_from_capability)
                self._attr_native_unit_of_measurement = unit_normalized
            elif self._attr_device_class == SensorDeviceClass.ENERGY and base_capability == "meter_power":
                # For energy sensors (meter_power.*), ensure unit is kWh for Energy dashboard compatibility
                # If unit is already kWh or similar, use it; otherwise default to kWh
                unit_lower = unit_from_capability.lower()
                if "kwh" in unit_lower or "wh" in unit_lower:
                    self._attr_native_unit_of_measurement = unit_from_capability
                else:
                    # Default to kWh for Energy dashboard compatibility
                    self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
            else:
                self._attr_native_unit_of_measurement = unit_from_capability
        else:
            self._attr_native_unit_of_measurement = sensor_config.get("unit")

        self._attr_device_info = get_device_info(device_id, device, zones)
    
    def _normalize_price_unit(self, unit: str) -> str:
        """Normalize price sensor units to currency/kWh format for Home Assistant Energy dashboard.
        
        Converts currency symbols to currency codes and appends /kWh.
        Examples:
        - "¤" -> "SEK/kWh" (generic currency symbol, default to SEK)
        - "€" -> "EUR/kWh"
        - "$" -> "USD/kWh"
        - "kr" -> "SEK/kWh" (Swedish/Norwegian/Danish krone)
        - "SEK" -> "SEK/kWh" (already a code)
        - "SEK/kWh" -> "SEK/kWh" (already formatted)
        """
        if not unit:
            return "SEK/kWh"  # Default fallback
        
        unit = unit.strip()
        
        # If already in currency/kWh format, return as-is
        if "/kWh" in unit or "/Wh" in unit:
            return unit
        
        # Map currency symbols to currency codes
        currency_map = {
            "¤": "SEK",  # Generic currency symbol - default to SEK (common for Tibber users)
            "€": "EUR",
            "$": "USD",
            "£": "GBP",
            "¥": "JPY",
            "kr": "SEK",  # Swedish/Norwegian/Danish krone
            "SEK": "SEK",
            "EUR": "EUR",
            "USD": "USD",
            "GBP": "GBP",
            "NOK": "NOK",
            "DKK": "DKK",
        }
        
        # Convert symbol to code
        currency_code = currency_map.get(unit, unit.upper())
        
        # Append /kWh for Energy dashboard compatibility
        return f"{currency_code}/kWh"

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
            # measure_humidity, measure_soil_moisture, and measure_battery might return normalized 0-1
            base_capability = self._capability_id.split(".")[0] if "." in self._capability_id else self._capability_id
            if base_capability in ("measure_humidity", "measure_soil_moisture", "measure_battery"):
                # Check capability max to determine if normalized
                cap_max = capability.get("max", 100)
                if cap_max <= 1.0:
                    # Normalized value (0-1), convert to percentage (0-100)
                    value_float = value_float * 100.0
            
            return value_float
        except (ValueError, TypeError):
            return None

