"""Helper functions for device info."""
from __future__ import annotations

from typing import Any

from .const import DOMAIN


def get_device_type(capabilities: dict[str, Any]) -> str:
    """Determine device type based on capabilities."""
    caps = set(capabilities.keys())
    
    # Check for specific device types
    if any(cap in caps for cap in ["light_hue", "light_saturation", "light_temperature", "dim"]):
        return "light"
    if "windowcoverings_state" in caps:
        return "cover"
    if "target_temperature" in caps:
        return "climate"
    if "fan_speed" in caps:
        return "fan"
    if "locked" in caps:
        return "lock"
    if any(cap in caps for cap in ["volume_set", "speaker_playing", "speaker_next"]):
        return "media_player"
    if any(cap.startswith("alarm_") for cap in caps):
        return "sensor"
    if any(cap.startswith("measure_") for cap in caps):
        return "sensor"
    if "onoff" in caps:
        return "switch"
    
    return "device"


def get_device_info(
    device_id: str,
    device: dict[str, Any],
    zones: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Get device info with room and type information.
    
    All entities from the same device MUST use identical device_info
    to ensure they're grouped under one device in Home Assistant.
    """
    capabilities = device.get("capabilitiesObj", {})
    device_type = get_device_type(capabilities)
    
    # Get room/zone information
    zone_id = device.get("zone")
    room_name = None
    if zone_id and zones:
        zone = zones.get(zone_id)
        if zone:
            room_name = zone.get("name")
    
    # Extract manufacturer and model from driverUri
    driver_uri = device.get("driverUri", "")
    manufacturer = "Unknown"
    model = "Unknown"
    if driver_uri:
        parts = driver_uri.split(".")
        if len(parts) >= 2:
            manufacturer = parts[0] or "Unknown"
            model = parts[-1] or "Unknown"
    
    # Build device info - MUST be identical for all entities from same device
    # The identifiers tuple is the key that Home Assistant uses to group entities
    device_info: dict[str, Any] = {
        "identifiers": {(DOMAIN, device_id)},  # This MUST be identical for all entities from same device
        "name": device.get("name") or "Unknown Device",  # Use consistent None handling
        "manufacturer": manufacturer,
        "model": model,
        "suggested_area": room_name,  # This will create/use areas in Home Assistant
    }
    
    # Ensure all fields are consistent (no None values that could cause issues)
    if not device_info["name"]:
        device_info["name"] = "Unknown Device"
    
    return device_info


def get_entity_name_with_type(device: dict[str, Any], entity_type: str) -> str:
    """Get entity name with device type prefix for better searchability."""
    device_name = device.get("name", "Unknown")
    capabilities = device.get("capabilitiesObj", {})
    device_type = get_device_type(capabilities)
    
    # Add type prefix if it's helpful
    type_labels = {
        "light": "💡",
        "switch": "🔌",
        "sensor": "📊",
        "climate": "🌡️",
        "fan": "🌀",
        "cover": "🪟",
        "lock": "🔒",
        "media_player": "🔊",
    }
    
    # For now, just return the device name - Home Assistant's area organization will help
    return device_name

