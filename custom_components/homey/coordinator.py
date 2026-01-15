"""Data update coordinator for Homey."""
from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
import time
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
            # Polling interval: 5-10 seconds is a good balance between responsiveness and system load
            # Socket.IO provides instant updates for supported devices, but Homey may not send Socket.IO events
            # for device changes (affects all device types, not just Zigbee)
            # With 141 devices, polling every 1 second overwhelms the WebSocket API
            # Default to 5 seconds, but will adjust to 5-10 seconds when Socket.IO fails
            update_interval = timedelta(seconds=5)  # 5 seconds - reasonable for UI updates without overwhelming the system
            # Note: Socket.IO real-time updates are enabled if available
            # If Socket.IO fails or doesn't send events, polling will be used (5-10 seconds)
            # Changes made via Homey app will appear within 5-10 seconds via polling (or instantly via Socket.IO if supported)
        
        # Create a logger filter to suppress the "Finished fetching" DEBUG messages
        # The base DataUpdateCoordinator logs these every update, which is too verbose
        import logging
        
        class SuppressFinishedFetchingFilter(logging.Filter):
            """Filter to suppress 'Finished fetching' DEBUG messages."""
            def filter(self, record):
                return "Finished fetching" not in record.getMessage()
        
        # Get the logger and add filter
        coordinator_logger = logging.getLogger(__name__)
        coordinator_logger.addFilter(SuppressFinishedFetchingFilter())
        
        super().__init__(
            hass,
            coordinator_logger,
            name="Homey",
            update_interval=update_interval,
        )
        self.api = api
        self.hass = hass
        self.zones = zones or {}
        self._previous_device_ids: set[str] = set()
        self._last_recovery_attempt: float = 0.0
        self._recovery_cooldown: int = 300  # seconds
        
        # Conditional batching: only batch when multiple updates arrive rapidly
        # Single updates process immediately for instant UI response
        self._pending_sio_updates: dict[str, dict[str, Any]] = {}
        self._sio_update_task: Any = None
        self._sio_batch_delay = 0.015  # 15ms delay for batched updates (only when multiple updates)

        # Register for real-time updates
        self.api.add_device_listener(self._on_device_update)

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Fetch data from Homey.
        
        Note: This method always uses polling. If Socket.IO is connected, it will
        provide real-time updates via the listener system, but polling continues
        as a fallback to ensure data consistency.
        """
        update_start = time.time()
        try:
            # Refresh zones periodically (every 20 updates = ~100 seconds / ~1.7 minutes)
            if not hasattr(self, "_zone_update_count"):
                self._zone_update_count = 0
            
            self._zone_update_count += 1
            if self._zone_update_count >= 20:
                self.zones = await self.api.get_zones() or {}
                self._zone_update_count = 0
                _LOGGER.debug("Refreshed zones from Homey")
            
            # Periodically check Socket.IO status and adjust polling interval accordingly
            # When Socket.IO is connected, reduce polling frequency (use as safety net only)
            # When Socket.IO is disconnected, use normal polling frequency (5-10 seconds)
            if hasattr(self.api, '_sio_connected'):
                if not self.api._sio_connected:
                    # Socket.IO disconnected - use fallback polling interval (5-10 seconds)
                    # Use 10 seconds as fallback to reduce API load while still being responsive
                    if self.update_interval != timedelta(seconds=10):
                        _LOGGER.debug("Socket.IO disconnected - switching to fallback polling (10 second interval)")
                        self.update_interval = timedelta(seconds=10)
                    # Log status check only once per session (not every poll)
                    if not hasattr(self, "_sio_status_logged"):
                        _LOGGER.debug("Socket.IO status: DISCONNECTED - using fallback polling (10 second interval)")
                        _LOGGER.debug("Reconnection attempts will continue in background")
                        self._sio_status_logged = True
                    # Trigger reconnection attempt (will happen in background)
                    self.api._start_sio_reconnect_task()
                else:
                    # Socket.IO is connected - reduce polling to safety net interval (60 seconds)
                    if self.update_interval != timedelta(seconds=60):
                        _LOGGER.debug("Socket.IO connected - reducing polling to safety net (60 second interval)")
                        self.update_interval = timedelta(seconds=60)
                        # Reset status logged flag so we log again if it disconnects
                        if hasattr(self, "_sio_status_logged"):
                            delattr(self, "_sio_status_logged")
                    # Socket.IO is connected - check if we've received any events
                    # Note: This is just informational - Socket.IO stays connected regardless
                    if not hasattr(self.api, "_sio_first_event_logged"):
                        # Connected but no events received yet - log this once after a longer delay
                        # Give user time to test (30 seconds = 6 polls at 5s interval, or 30s at 60s interval)
                        if not hasattr(self, "_sio_no_events_logged"):
                            # Wait a bit before logging (give it time to receive events and for user to test)
                            if not hasattr(self, "_sio_check_count"):
                                self._sio_check_count = 0
                            self._sio_check_count += 1
                            # Log after 30 seconds if still no events (informational only - Socket.IO stays connected)
                            # This is just to help diagnose if Homey isn't sending events
                            check_threshold = 6 if self.update_interval == timedelta(seconds=5) else 1  # 6 polls at 5s = 30s, or 1 poll at 60s = 60s
                            if self._sio_check_count >= check_threshold:
                                _LOGGER.debug("Socket.IO connected but no events received yet (this is normal - events arrive when devices change)")
                                _LOGGER.debug("To test: Change a device in Homey app and watch for events in logs")
                                _LOGGER.debug("Socket.IO connection remains active - polling continues as safety net")
                                self._sio_no_events_logged = True
                    else:
                        # Events are arriving - reset counters
                        if hasattr(self, "_sio_no_events_logged"):
                            delattr(self, "_sio_no_events_logged")
                        if hasattr(self, "_sio_check_count"):
                            delattr(self, "_sio_check_count")
                    # Reset status log flag if reconnected
                    if hasattr(self, "_sio_status_logged"):
                        self._sio_status_logged = False
            
            devices = await self.api.get_devices()
            
            # If we suddenly get no devices after previously having data,
            # try a one-time recovery (Homey reboot/network blip).
            if not devices and self._previous_device_ids:
                if self._should_attempt_recovery():
                    _LOGGER.warning(
                        "No devices returned from Homey API - attempting automatic reconnect"
                    )
                    await self._attempt_api_recovery()
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
            
            update_duration = time.time() - update_start
            # Only log debug info on errors or if update takes unusually long (>1 second)
            if update_duration > 1.0:
                _LOGGER.debug("Device update took %.2f seconds, fetched %d devices", update_duration, len(devices))
            
            return devices
        except Exception as err:
            if self._should_attempt_recovery():
                _LOGGER.warning(
                    "Polling error from Homey API - attempting automatic reconnect: %s",
                    err,
                )
                await self._attempt_api_recovery()
            _LOGGER.error("Polling failed - error communicating with Homey: %s", err)
            raise UpdateFailed(f"Error communicating with Homey: {err}") from err

    def _should_attempt_recovery(self) -> bool:
        """Check if enough time has passed to attempt API recovery."""
        now = time.time()
        if now - self._last_recovery_attempt < self._recovery_cooldown:
            return False
        self._last_recovery_attempt = now
        return True

    async def _attempt_api_recovery(self) -> None:
        """Attempt to re-establish API connection after errors."""
        try:
            await self.api.disconnect()
        except Exception as err:
            _LOGGER.debug("Failed to disconnect Homey API cleanly: %s", err)
        try:
            await self.api.connect()
            await self.api.authenticate()
        except Exception as err:
            _LOGGER.debug("Homey API recovery attempt failed: %s", err)

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
        """Handle device update from Socket.IO.
        
        This is called from Socket.IO callbacks which may run in a different thread.
        Uses conditional batching: single updates process immediately, multiple rapid updates are batched.
        Matches async_refresh_device behavior by using async tasks instead of synchronous callbacks.
        """
        if not self.hass.is_running:
            # Fallback: if HA isn't running yet, just update synchronously
            if self.data:
                if device_id in self.data:
                    self.data[device_id].update(data)
                else:
                    self.data[device_id] = data
                self.async_update_listeners()
            return
        
        # Store the latest update for this device (thread-safe dict access)
        self._pending_sio_updates[device_id] = data
        
        # Schedule task creation in the event loop thread (thread-safe)
        def schedule_update_task():
            """Schedule async task in the event loop thread."""
            # Check if there's already a pending batch task
            if self._sio_update_task and not self._sio_update_task.done():
                # Multiple updates arriving rapidly - cancel and reschedule with batching
                self._sio_update_task.cancel()
                self._sio_update_task = self.hass.async_create_task(
                    self._async_process_batched_sio_updates()
                )
            else:
                # Single update or first update - process immediately using async task
                # This matches async_refresh_device behavior (async context)
                if len(self._pending_sio_updates) == 1:
                    # Only one update, process immediately in async context
                    self._sio_update_task = self.hass.async_create_task(
                        self._async_process_sio_update_immediate()
                    )
                else:
                    # Multiple updates queued, batch them
                    self._sio_update_task = self.hass.async_create_task(
                        self._async_process_batched_sio_updates()
                    )
        
        # Schedule task creation in the event loop thread (thread-safe)
        self.hass.loop.call_soon_threadsafe(schedule_update_task)
    
    async def _async_process_sio_update_immediate(self) -> None:
        """Process Socket.IO update immediately in async context (matches async_refresh_device)."""
        if not self._pending_sio_updates or not self.data:
            return
        
        # Log Socket.IO update for debugging
        import time
        update_start = time.time()
        device_ids = list(self._pending_sio_updates.keys())
        
        # Update coordinator data with pending update
        # This matches exactly what async_refresh_device does
        for update_device_id, update_data in self._pending_sio_updates.items():
            if update_device_id in self.data:
                self.data[update_device_id].update(update_data)
            else:
                self.data[update_device_id] = update_data
        
        # Clear pending updates
        self._pending_sio_updates.clear()
        
        # Notify listeners immediately (same as async_refresh_device)
        # Being in async context ensures callbacks execute immediately
        self.async_update_listeners()
        
        # Log Socket.IO update timing
        update_duration = time.time() - update_start
        _LOGGER.debug(
            "Socket.IO update processed for device(s) %s in %.3f seconds - UI should update immediately",
            ", ".join(device_ids[:3]) + ("..." if len(device_ids) > 3 else ""),
            update_duration
        )
    
    async def _async_process_batched_sio_updates(self) -> None:
        """Process batched Socket.IO updates after a short delay (for rapid successive updates)."""
        try:
            # Wait a short delay to batch rapid updates
            await asyncio.sleep(self._sio_batch_delay)
            
            # Process all pending updates (same as immediate processing)
            if not self._pending_sio_updates or not self.data:
                return
            
            # Update coordinator data with all pending updates
            for update_device_id, update_data in self._pending_sio_updates.items():
                if update_device_id in self.data:
                    self.data[update_device_id].update(update_data)
                else:
                    self.data[update_device_id] = update_data
            
            # Clear pending updates
            self._pending_sio_updates.clear()
            
            # Notify listeners (in async context, callbacks execute immediately)
            self.async_update_listeners()
        except asyncio.CancelledError:
            # Task was cancelled - this is expected when new updates arrive
            # The next scheduled task will process the pending updates
            pass
    
    async def async_refresh_device(self, device_id: str) -> None:
        """Immediately refresh a specific device's state from Homey API.
        
        This is called after setting a capability value to get immediate feedback
        instead of waiting for the next polling interval.
        
        Note: This only works for changes made via Home Assistant. Changes made via
        the Homey app will only be detected during the next polling cycle (every 5 seconds).
        """
        refresh_start = time.time()
        try:
            device_data = await self.api.get_device(device_id)
            if device_data and self.data:
                # Update the device data in coordinator
                self.data[device_id] = device_data
                # Notify listeners immediately
                self.async_update_listeners()
                refresh_duration = time.time() - refresh_start
                _LOGGER.debug("Immediately refreshed device %s in %.2f seconds", device_id, refresh_duration)
        except Exception as err:
            _LOGGER.debug("Error refreshing device %s: %s", device_id, err)
            # Fall back to regular refresh request
            await self.async_request_refresh()

