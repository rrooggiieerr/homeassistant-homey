"""Data update coordinator for Homey."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_DEVICE_FILTER, DOMAIN
from .homey_api import HomeyAPI

_LOGGER = logging.getLogger(__name__)


class HomeyDataUpdateCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Class to manage fetching Homey data."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: HomeyAPI,
        zones: dict[str, dict[str, Any]] | None = None,
        update_interval: timedelta | None = None,
    ) -> None:
        """Initialize the coordinator."""
        if update_interval is None:
            update_interval = timedelta(seconds=10)  # Reduced from 30s to 10s for better responsiveness
        
        super().__init__(
            hass,
            _LOGGER,
            name="Homey",
            update_interval=update_interval,
        )
        self.api = api
        self.hass = hass
        self.zones = zones or {}
        self._previous_device_ids: set[str] = set()

        # Register for real-time updates
        self.api.add_device_listener(self._on_device_update)

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Fetch data from Homey."""
        try:
            # Refresh zones periodically (every 10 updates = ~5 minutes)
            if not hasattr(self, "_zone_update_count"):
                self._zone_update_count = 0
            
            self._zone_update_count += 1
            if self._zone_update_count >= 10:
                self.zones = await self.api.get_zones() or {}
                self._zone_update_count = 0
                _LOGGER.debug("Refreshed zones from Homey")
            
            devices = await self.api.get_devices()
            
            # Update device registry for name/room changes
            await self._update_device_registry(devices)
            
            # Track current device IDs for deletion detection
            current_device_ids = set(devices.keys())
            deleted_device_ids = self._previous_device_ids - current_device_ids
            
            # Remove deleted devices from registry
            if deleted_device_ids:
                await self._remove_deleted_devices(deleted_device_ids)
            
            self._previous_device_ids = current_device_ids
            
            return devices
        except Exception as err:
            raise UpdateFailed(f"Error communicating with Homey: {err}") from err

    async def _assign_areas_to_devices(self) -> None:
        """Assign areas to devices based on Homey zones during initial setup."""
        if not self.data:
            return
        
        device_registry = dr.async_get(self.hass)
        from homeassistant.helpers import area_registry as ar
        area_registry = ar.async_get(self.hass)
        
        for device_id, device in self.data.items():
            device_entry = device_registry.async_get_device(
                identifiers={(DOMAIN, device_id)}, connections=set()
            )
            
            if not device_entry:
                continue
            
            # Get zone/room information
            zone_id = device.get("zone")
            room_name = None
            if zone_id and self.zones:
                zone = self.zones.get(zone_id)
                if zone:
                    room_name = zone.get("name")
            
            # Assign area if room exists
            if room_name:
                # Find or create area
                area = area_registry.async_get_area_by_name(room_name)
                if area:
                    area_id = area.id
                else:
                    # Create new area
                    area = area_registry.async_create(room_name)
                    area_id = area.id
                
                # Assign area to device if not already assigned
                if device_entry.area_id != area_id:
                    device_registry.async_update_device(
                        device_entry.id,
                        area_id=area_id,
                    )
                    _LOGGER.debug("Assigned device %s to area: %s", device_entry.name, room_name)

    async def _update_device_registry(self, devices: dict[str, dict[str, Any]]) -> None:
        """Update device registry when device names or rooms change."""
        device_registry = dr.async_get(self.hass)
        
        for device_id, device in devices.items():
            device_entry = device_registry.async_get_device(
                identifiers={(DOMAIN, device_id)}, connections=set()
            )
            
            if not device_entry:
                continue
            
            # Get updated device info
            device_name = device.get("name") or "Unknown Device"
            zone_id = device.get("zone")
            room_name = None
            if zone_id and self.zones:
                zone = self.zones.get(zone_id)
                if zone:
                    room_name = zone.get("name")
            
            # Update device name if changed
            if device_entry.name != device_name:
                device_registry.async_update_device(
                    device_entry.id,
                    name=device_name,
                )
                _LOGGER.debug("Updated device name: %s -> %s", device_entry.name, device_name)
            
            # Update device area ONLY if:
            # 1. Device has no area assigned (area_id is None), OR
            # 2. Current area name matches the Homey zone name (was set by integration, not manually changed)
            # This prevents overwriting user-assigned areas
            from homeassistant.helpers import area_registry as ar
            area_registry = ar.async_get(self.hass)
            
            current_area_id = device_entry.area_id
            current_area_name = None
            if current_area_id:
                current_area = area_registry.async_get_area(current_area_id)
                if current_area:
                    current_area_name = current_area.name
            
            # Only update area if device has no area OR current area matches Homey zone
            # This allows the integration to update areas when Homey zones change,
            # but preserves user manual area assignments
            should_update_area = False
            new_area_id = None
            
            if room_name:
                # Find or create area for Homey zone
                area = area_registry.async_get_area_by_name(room_name)
                if area:
                    new_area_id = area.id
                else:
                    # Create new area if it doesn't exist
                    area = area_registry.async_create(room_name)
                    new_area_id = area.id
                
                # Only update if:
                # - Device has no area assigned, OR
                # - Current area name matches the Homey zone name (integration-set area)
                if current_area_id is None:
                    should_update_area = True
                    _LOGGER.debug("Assigning initial area %s to device %s", room_name, device_entry.name)
                elif current_area_name == room_name:
                    # Area matches Homey zone - safe to update if zone changed
                    # (This handles zone renames in Homey)
                    if current_area_id != new_area_id:
                        should_update_area = True
                        _LOGGER.debug("Updating area for device %s: zone name matches, updating area ID", device_entry.name)
                else:
                    # Current area doesn't match Homey zone - user manually changed it
                    # Don't overwrite user's manual assignment
                    _LOGGER.debug(
                        "Skipping area update for device %s: current area '%s' doesn't match Homey zone '%s' (user-managed)",
                        device_entry.name, current_area_name, room_name
                    )
            elif current_area_id is not None:
                # Device has an area but Homey zone is None/empty
                # Don't remove user-assigned areas - only remove if it was integration-set
                # We can't reliably detect this, so we'll leave it as-is
                _LOGGER.debug(
                    "Device %s has area '%s' but no Homey zone - preserving user assignment",
                    device_entry.name, current_area_name
                )
            
            if should_update_area and new_area_id and current_area_id != new_area_id:
                device_registry.async_update_device(
                    device_entry.id,
                    area_id=new_area_id,
                )
                _LOGGER.debug("Updated device area: %s -> %s", current_area_id, new_area_id)

    async def _remove_deleted_devices(self, deleted_device_ids: set[str]) -> None:
        """Remove deleted devices from device registry."""
        device_registry = dr.async_get(self.hass)
        from homeassistant.helpers import entity_registry as er
        entity_registry = er.async_get(self.hass)
        
        for device_id in deleted_device_ids:
            device_entry = device_registry.async_get_device(
                identifiers={(DOMAIN, device_id)}, connections=set()
            )
            
            if device_entry:
                # Remove all entities for this device
                entities = [
                    entry
                    for entry in entity_registry.entities.values()
                    if entry.device_id == device_entry.id
                ]
                for entity_entry in entities:
                    entity_registry.async_remove(entity_entry.entity_id)
                
                # Remove the device
                device_registry.async_remove_device(device_entry.id)
                _LOGGER.info("Removed deleted device: %s", device_id)
    
    async def _remove_unselected_devices(self, entry: Any) -> None:
        """Remove devices that are no longer in device_filter from device registry.
        
        This is called during setup to clean up devices that were removed from
        the device_filter via the options flow or manual deletion.
        """
        from homeassistant.config_entries import ConfigEntry
        
        if not isinstance(entry, ConfigEntry):
            return
        
        device_filter = entry.data.get(CONF_DEVICE_FILTER)
        
        # If device_filter is None, all devices are selected, so nothing to remove
        if device_filter is None:
            return
        
        device_filter_set = set(device_filter)
        device_registry = dr.async_get(self.hass)
        from homeassistant.helpers import entity_registry as er
        entity_registry = er.async_get(self.hass)
        
        # Get all devices for this integration
        # We need to check devices that belong to this config entry
        devices_to_remove = []
        
        # Virtual devices that should never be removed (not real devices from Homey)
        virtual_devices = {"flows"}  # "flows" is a virtual device for flow buttons
        
        # Get all devices and check which ones belong to our integration
        for device_entry in device_registry.devices.values():
            # Check if this device belongs to our integration and this config entry
            for identifier in device_entry.identifiers:
                if identifier[0] == DOMAIN:
                    device_id = identifier[1]
                    
                    # Skip virtual devices - they should never be removed
                    if device_id in virtual_devices:
                        break
                    
                    # Check if this device is associated with our config entry
                    # and if it's not in the filter
                    if device_id not in device_filter_set:
                        # Verify this device belongs to our config entry
                        # by checking if it's in the coordinator data or was previously tracked
                        if device_id not in (self.data or {}):
                            # Device not in current data, might be stale
                            # But only remove if it's definitely not in filter
                            devices_to_remove.append((device_entry.id, device_id))
                    break
        
        # Remove devices and their entities
        for device_entry_id, device_id in devices_to_remove:
            device_entry = device_registry.async_get(device_entry_id)
            if device_entry:
                # Verify this device still belongs to our integration
                still_ours = False
                for identifier in device_entry.identifiers:
                    if identifier[0] == DOMAIN and identifier[1] == device_id:
                        still_ours = True
                        break
                
                if still_ours:
                    # Remove all entities for this device
                    entities = [
                        entry
                        for entry in entity_registry.entities.values()
                        if entry.device_id == device_entry_id
                    ]
                    for entity_entry in entities:
                        entity_registry.async_remove(entity_entry.entity_id)
                    
                    # Remove the device
                    device_registry.async_remove_device(device_entry_id)
                    _LOGGER.info("Removed unselected device from registry: %s", device_id)

    def _on_device_update(self, device_id: str, data: dict[str, Any]) -> None:
        """Handle device update from Socket.IO."""
        # Update the coordinator data immediately
        if self.data:
            if device_id in self.data:
                self.data[device_id].update(data)
            else:
                self.data[device_id] = data
            # Notify listeners
            self.async_update_listeners()
    
    async def async_refresh_device(self, device_id: str) -> None:
        """Immediately refresh a specific device's state from Homey API.
        
        This is called after setting a capability value to get immediate feedback
        instead of waiting for the next polling interval.
        """
        try:
            device_data = await self.api.get_device(device_id)
            if device_data and self.data:
                # Update the device data in coordinator
                self.data[device_id] = device_data
                # Notify listeners immediately
                self.async_update_listeners()
                _LOGGER.debug("Immediately refreshed device %s", device_id)
        except Exception as err:
            _LOGGER.debug("Error refreshing device %s: %s", device_id, err)
            # Fall back to regular refresh request
            await self.async_request_refresh()

