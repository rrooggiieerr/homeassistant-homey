"""Constants for the Homey integration."""
from __future__ import annotations

DOMAIN = "homey"

CONF_HOST = "host"
CONF_TOKEN = "token"
CONF_DEVICE_FILTER = "device_filter"
CONF_WORKING_ENDPOINT = "working_endpoint"  # Store which endpoint structure worked

DEFAULT_NAME = "Homey"

# Homey API endpoints
# Try manager API structure first (based on Homey API documentation)
API_BASE_V1 = "/api/v1"
API_BASE_MANAGER = "/api/manager"
API_SYSTEM = f"{API_BASE_MANAGER}/system/info"  # Manager API structure
API_DEVICES = f"{API_BASE_MANAGER}/devices/device/"  # Manager API structure with trailing slash
API_DEVICES_NO_SLASH = f"{API_BASE_MANAGER}/devices/device"  # Without trailing slash
API_DEVICES_V1 = f"{API_BASE_V1}/device"  # Fallback v1 structure
API_CAPABILITIES = f"{API_BASE_MANAGER}/capabilities/capability"
API_FLOWS = f"{API_BASE_MANAGER}/flow/flow"  # Standard flows: singular "flow" not "flows"
API_ADVANCED_FLOWS = f"{API_BASE_MANAGER}/flow/advancedflow"  # Advanced flows endpoint
API_ZONES = f"{API_BASE_MANAGER}/zones/zone"  # Rooms/zones in Homey

# Device capability mappings to HA platforms
CAPABILITY_TO_PLATFORM = {
    "onoff": "switch",
    "dim": "light",
    "light_hue": "light",
    "light_saturation": "light",
    "light_temperature": "light",
    "windowcoverings_state": "cover",
    "windowcoverings_tilt_up": "cover",
    "windowcoverings_tilt_down": "cover",
    "target_temperature": "climate",
    "measure_temperature": "sensor",
    "measure_humidity": "sensor",
    "measure_pressure": "sensor",
    "measure_power": "sensor",
    "measure_voltage": "sensor",
    "measure_current": "sensor",
    "measure_luminance": "sensor",
    "measure_co2": "sensor",
    "measure_co": "sensor",
    "alarm_motion": "binary_sensor",
    "alarm_contact": "binary_sensor",
    "alarm_tamper": "binary_sensor",
    "alarm_smoke": "binary_sensor",
    "alarm_co": "binary_sensor",
    "alarm_co2": "binary_sensor",
    "alarm_water": "binary_sensor",
    "alarm_battery": "binary_sensor",
    "fan_speed": "fan",
    "locked": "lock",
    "volume_set": "media_player",
    "volume_mute": "media_player",
    "speaker_playing": "media_player",
    "speaker_next": "media_player",
    "speaker_prev": "media_player",
}

