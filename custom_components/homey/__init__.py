"""The Homey integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import HomeyDataUpdateCoordinator
from .homey_api import HomeyAPI

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.LIGHT,
    Platform.SWITCH,
    Platform.COVER,
    Platform.CLIMATE,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.FAN,
    Platform.LOCK,
    Platform.MEDIA_PLAYER,
    Platform.BUTTON,  # For Homey flows
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Homey from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Initialize Homey API client
    api = HomeyAPI(
        host=entry.data["host"],
        token=entry.data["token"],
        preferred_endpoint=entry.data.get("working_endpoint"),  # Use endpoint that worked in config flow
    )

    try:
        await api.connect()
        # Authentication already validated in config flow, but verify we can get devices
        # If system endpoint fails, try devices endpoint as fallback
        auth_result = await api.authenticate()
        if not auth_result:
            _LOGGER.warning("System endpoint authentication failed, but continuing since config flow validated connection")
            # Try to get devices to verify connection works
            devices = await api.get_devices()
            if not devices:
                _LOGGER.error("Cannot access Homey API - no devices endpoint accessible")
                return False
    except Exception as err:
        _LOGGER.error("Failed to connect to Homey: %s", err)
        return False

    # Fetch zones (rooms) for device organization
    zones = await api.get_zones()
    
    # Create coordinator (pass zones so it can update device registry)
    coordinator = HomeyDataUpdateCoordinator(hass, api, zones)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
        "zones": coordinator.zones,  # Use zones from coordinator (will be updated periodically)
    }

    # Forward the setup to the platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register service to trigger flows
    async def async_trigger_flow(call) -> None:
        """Service to trigger a Homey flow."""
        # Get API from the entry data
        entry_data = hass.data[DOMAIN].get(entry.entry_id)
        if not entry_data or "api" not in entry_data:
            _LOGGER.error("Homey API not available")
            return
        
        api_instance = entry_data["api"]
        flow_id = call.data.get("flow_id")
        flow_name = call.data.get("flow_name")
        
        if not flow_id and not flow_name:
            _LOGGER.error("Either flow_id or flow_name must be provided")
            return
        
        # If flow_name provided, find flow_id
        if flow_name and not flow_id:
            flows = await api_instance.get_flows()
            for fid, flow in flows.items():
                if flow.get("name") == flow_name:
                    flow_id = fid
                    break
            
            if not flow_id:
                _LOGGER.error("Flow not found: %s", flow_name)
                return
        
        success = await api_instance.trigger_flow(flow_id)
        if success:
            _LOGGER.info("Triggered Homey flow: %s", flow_id)
        else:
            _LOGGER.error("Failed to trigger Homey flow: %s", flow_id)

    hass.services.async_register(DOMAIN, "trigger_flow", async_trigger_flow)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        if data and "api" in data:
            await data["api"].disconnect()

    return unload_ok

