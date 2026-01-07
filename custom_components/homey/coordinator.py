"""Data update coordinator for Homey."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
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
            update_interval = timedelta(seconds=30)
        
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
            
            # Update device area if room changed
            area_id = None
            if room_name:
                # Find or create area
                from homeassistant.helpers import area_registry as ar
                area_registry = ar.async_get(self.hass)
                area = area_registry.async_get_area_by_name(room_name)
                if area:
                    area_id = area.id
                else:
                    # Create new area
                    area = area_registry.async_create(room_name)
                    area_id = area.id
            
            if device_entry.area_id != area_id:
                device_registry.async_update_device(
                    device_entry.id,
                    area_id=area_id,
                )
                _LOGGER.debug("Updated device area: %s -> %s", device_entry.area_id, area_id)

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
                entities = entity_registry.async_entries_for_device(device_entry.id)
                for entity_entry in entities:
                    entity_registry.async_remove(entity_entry.entity_id)
                
                # Remove the device
                device_registry.async_remove_device(device_entry.id)
                _LOGGER.info("Removed deleted device: %s", device_id)

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

