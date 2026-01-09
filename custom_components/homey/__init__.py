"""The Homey integration."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import CONF_DEVICE_FILTER, DOMAIN
from .coordinator import HomeyDataUpdateCoordinator
from .homey_api import HomeyAPI

_LOGGER = logging.getLogger(__name__)

# Module loaded

def _check_installation_conflict() -> None:
    """Check for conflicting installation methods and warn if detected.
    
    This detects if there's a manual installation conflicting with HACS,
    or vice versa, and logs a warning to help users troubleshoot.
    """
    try:
        # Get the path to this integration's directory
        integration_dir = Path(__file__).parent.resolve()
        
        # Check for HACS metadata file (HACS creates .hacs.json in custom_components/)
        # Path structure: config/custom_components/homey/__init__.py
        # So custom_components is parent.parent
        custom_components_dir = integration_dir.parent
        hacs_json = custom_components_dir / ".hacs.json"
        hacs_installed = hacs_json.exists()
        
        # Check for git directory in custom_components (indicates manual git clone of entire repo)
        # Path: config/custom_components/.git
        git_dir = custom_components_dir / ".git"
        manual_git = git_dir.exists()
        
        # Check for git directory in integration folder itself (another manual install pattern)
        integration_git = integration_dir / ".git"
        integration_has_git = integration_git.exists()
        
        if hacs_installed and (manual_git or integration_has_git):
            _LOGGER.warning(
                "⚠️  Installation conflict detected: You appear to have both HACS and manual installation. "
                "This can cause update issues. Please remove the manual installation folder "
                "(%s) and restart Home Assistant, then update via HACS.",
                integration_dir
            )
        elif hacs_installed:
            _LOGGER.debug("HACS installation detected - updates should be managed via HACS")
        elif manual_git or integration_has_git:
            _LOGGER.debug("Manual installation detected - updates should be done manually")
    except Exception as err:
        # Don't let installation check break the integration
        _LOGGER.debug("Could not check installation method: %s", err)

# Run check on module load
_check_installation_conflict()


def filter_devices(devices: dict[str, dict[str, Any]], device_filter: list[str] | None) -> dict[str, dict[str, Any]]:
    """Filter devices based on device_filter configuration."""
    if device_filter:
        return {did: dev for did, dev in devices.items() if did in device_filter}
    return devices

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
    Platform.BUTTON,  # For Homey flows and device buttons
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SCENE,
]


async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: ConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    """Handle removal of a device from the device registry.
    
    This allows users to manually delete devices from the Devices page.
    When a device is deleted, we remove it from the device_filter.
    """
    device_registry = dr.async_get(hass)
    
    # Find the device_id from the device entry identifiers
    device_id = None
    for identifier in device_entry.identifiers:
        if identifier[0] == DOMAIN:
            device_id = identifier[1]
            break
    
    if not device_id:
        _LOGGER.warning("Could not find device_id for device %s", device_entry.id)
        return False
    
    # Get current device filter
    current_filter = config_entry.data.get(CONF_DEVICE_FILTER)
    
    # If device_filter is None, it means all devices are selected
    # In that case, we need to get all devices and create a filter excluding this one
    if current_filter is None:
        # Get all devices from coordinator or API
        if config_entry.entry_id in hass.data.get(DOMAIN, {}):
            coordinator = hass.data[DOMAIN][config_entry.entry_id].get("coordinator")
            api = hass.data[DOMAIN][config_entry.entry_id].get("api")
            
            # Try to get devices from coordinator first (most up-to-date)
            if coordinator and coordinator.data:
                all_device_ids = set(coordinator.data.keys())
            elif api:
                # Fallback to API if coordinator doesn't have data yet
                try:
                    devices = await api.get_devices()
                    all_device_ids = set(devices.keys())
                except Exception:
                    _LOGGER.warning("Could not fetch devices to update filter")
                    all_device_ids = set()
            else:
                all_device_ids = set()
            
            # Remove the device being deleted
            all_device_ids.discard(device_id)
            new_filter = list(all_device_ids) if all_device_ids else []
        else:
            # Integration not loaded - fetch devices from API directly
            try:
                api = HomeyAPI(
                    host=config_entry.data["host"],
                    token=config_entry.data["token"],
                    preferred_endpoint=config_entry.data.get("working_endpoint"),
                )
                await api.connect()
                devices = await api.get_devices()
                all_device_ids = set(devices.keys())
                all_device_ids.discard(device_id)
                new_filter = list(all_device_ids) if all_device_ids else []
                await api.disconnect()
            except Exception as err:
                _LOGGER.warning("Could not fetch devices to update filter: %s", err)
                # Can't determine all devices, create filter with just this device excluded
                # This will be corrected on next reload
                new_filter = []
    else:
        # Remove device_id from filter
        new_filter = [did for did in current_filter if did != device_id]
    
    # Update config entry with new filter
    new_data = {**config_entry.data}
    new_data[CONF_DEVICE_FILTER] = new_filter if new_filter else None
    
    hass.config_entries.async_update_entry(config_entry, data=new_data)
    
    _LOGGER.info("Removed device %s from device filter", device_id)
    
    # Return True to indicate we handled the removal
    # Home Assistant will then remove the device and entities
    return True


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
        _LOGGER.error("Failed to connect to Homey: %s", err, exc_info=True)
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

    # Refresh zones and assign areas to devices based on Homey zones (after entities are created)
    coordinator.zones = await api.get_zones() or {}
    await coordinator._assign_areas_to_devices()
    
    # Remove devices that are no longer in device_filter
    await coordinator._remove_unselected_devices(entry)

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
            flow_name_normalized = flow_name.strip().lower()
            available_flow_names = []
            
            for fid, flow in flows.items():
                flow_display_name = flow.get("name", "Unknown")
                available_flow_names.append(flow_display_name)
                
                # Try exact match first
                if flow_display_name == flow_name:
                    flow_id = fid
                    break
                
                # Try case-insensitive match
                if flow_display_name.strip().lower() == flow_name_normalized:
                    flow_id = fid
                    break
            
            if not flow_id:
                _LOGGER.error("Flow not found: '%s'. Available flows: %s", flow_name, ", ".join(available_flow_names[:10]))
                return
        
        success = await api_instance.trigger_flow(flow_id)
        if success:
            _LOGGER.info("Triggered Homey flow: %s", flow_id)
        else:
            _LOGGER.error("Failed to trigger Homey flow: %s", flow_id)

    hass.services.async_register(DOMAIN, "trigger_flow", async_trigger_flow)

    # Register service to enable flows
    async def async_enable_flow(call) -> None:
        """Service to enable a Homey flow."""
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
            flow_name_normalized = flow_name.strip().lower()
            
            for fid, flow in flows.items():
                flow_display_name = flow.get("name", "Unknown")
                if flow_display_name == flow_name or flow_display_name.strip().lower() == flow_name_normalized:
                    flow_id = fid
                    break
            
            if not flow_id:
                _LOGGER.error("Flow not found: '%s'", flow_name)
                return
        
        success = await api_instance.enable_flow(flow_id)
        if success:
            _LOGGER.info("Enabled Homey flow: %s", flow_id)
        else:
            _LOGGER.error("Failed to enable Homey flow: %s", flow_id)

    # Register service to disable flows
    async def async_disable_flow(call) -> None:
        """Service to disable a Homey flow."""
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
            flow_name_normalized = flow_name.strip().lower()
            
            for fid, flow in flows.items():
                flow_display_name = flow.get("name", "Unknown")
                if flow_display_name == flow_name or flow_display_name.strip().lower() == flow_name_normalized:
                    flow_id = fid
                    break
            
            if not flow_id:
                _LOGGER.error("Flow not found: '%s'", flow_name)
                return
        
        success = await api_instance.disable_flow(flow_id)
        if success:
            _LOGGER.info("Disabled Homey flow: %s", flow_id)
        else:
            _LOGGER.error("Failed to disable Homey flow: %s", flow_id)

    hass.services.async_register(DOMAIN, "enable_flow", async_enable_flow)
    hass.services.async_register(DOMAIN, "disable_flow", async_disable_flow)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        if data and "api" in data:
            await data["api"].disconnect()

    return unload_ok

