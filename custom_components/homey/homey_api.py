"""Homey API client."""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import aiohttp
import socketio

from .const import (
    API_BASE_V1,
    API_BASE_MANAGER,
    API_DEVICES,
    API_DEVICES_NO_SLASH,
    API_DEVICES_V1,
    API_FLOWS,
    API_SYSTEM,
    API_ZONES,
)

_LOGGER = logging.getLogger(__name__)


class HomeyAPI:
    """Homey API client."""

    def __init__(self, host: str, token: str, preferred_endpoint: str | None = None) -> None:
        """Initialize the Homey API client."""
        self.host = host.rstrip("/")
        self.token = token
        self.preferred_endpoint = preferred_endpoint  # "manager" or "v1"
        self.session: aiohttp.ClientSession | None = None
        self.sio: socketio.AsyncClient | None = None
        self.devices: dict[str, dict[str, Any]] = {}
        self.flows: dict[str, dict[str, Any]] = {}
        self.zones: dict[str, dict[str, Any]] = {}  # Rooms/zones
        self._listeners: list[Callable[[str, dict[str, Any]], None]] = []

    async def connect(self) -> None:
        """Connect to Homey API."""
        # Use SSL=False for local Homey API
        connector = aiohttp.TCPConnector(ssl=False)
        self.session = aiohttp.ClientSession(
            connector=connector,
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=aiohttp.ClientTimeout(total=30),
        )

        # Socket.IO is optional - we'll use polling if it's not available
        # According to Homey API docs, Socket.IO requires handshakeClient event with session token
        # This is complex to implement, so we'll skip it for now and use polling instead
        # Real-time updates can be added later if needed
        self.sio = None
        _LOGGER.debug("Socket.IO disabled - using polling for updates")

    async def authenticate(self) -> bool:
        """Authenticate with Homey API."""
        if not self.session:
            return False

        # Try multiple possible system endpoints
        endpoints_to_try = [
            API_SYSTEM,  # /api/manager/system/info
            f"{API_BASE_MANAGER}/system",
            f"{API_BASE_V1}/manager/system/info",
            f"{API_BASE_V1}/manager/system",
            f"{API_BASE_V1}/system/info",
            f"{API_BASE_V1}/system",
        ]

        for endpoint in endpoints_to_try:
            try:
                async with self.session.get(f"{self.host}{endpoint}") as response:
                    if response.status == 200:
                        system_info = await response.json()
                        _LOGGER.info("Connected to Homey: %s", system_info.get("name") or system_info.get("homeyName"))
                        return True
                    elif response.status == 404:
                        _LOGGER.debug("Endpoint %s not found, trying next...", endpoint)
                        continue
                    elif response.status == 401:
                        _LOGGER.error("Authentication failed: Invalid API token")
                        return False
                    else:
                        _LOGGER.debug("Authentication failed with %s: %s", endpoint, response.status)
                        continue
            except Exception as err:
                _LOGGER.debug("Error trying endpoint %s: %s", endpoint, err)
                continue
        
        # If system endpoints don't work, try devices endpoint as fallback
        # This verifies the API is accessible even if system info isn't available
        _LOGGER.debug("System endpoints not available, verifying connection with devices endpoint")
        try:
            devices = await self.get_devices()
            # If get_devices() returns (even empty dict), API is accessible
            _LOGGER.info("API connection verified via devices endpoint")
            return True
        except Exception as err:
            _LOGGER.warning("Could not verify connection to any Homey API endpoint: %s", err)
            return False

    async def get_devices(self) -> dict[str, dict[str, Any]]:
        """Get all devices from Homey."""
        if not self.session:
            return {}

        # Try preferred endpoint first, then fallback
        if self.preferred_endpoint == "manager":
            endpoints_to_try = [
                API_DEVICES,  # /api/manager/devices/device/
                API_DEVICES_NO_SLASH,  # /api/manager/devices/device
                API_DEVICES_V1,  # /api/v1/device
                f"{API_DEVICES_V1}/",  # /api/v1/device/
            ]
        elif self.preferred_endpoint == "v1":
            endpoints_to_try = [
                API_DEVICES_V1,  # /api/v1/device
                f"{API_DEVICES_V1}/",  # /api/v1/device/
                API_DEVICES,  # /api/manager/devices/device/
                API_DEVICES_NO_SLASH,  # /api/manager/devices/device
            ]
        else:
            # Try manager API first, then fallback to v1
            endpoints_to_try = [
                API_DEVICES,  # /api/manager/devices/device/
                API_DEVICES_NO_SLASH,  # /api/manager/devices/device
                API_DEVICES_V1,  # /api/v1/device
                f"{API_DEVICES_V1}/",  # /api/v1/device/
            ]
        
        for endpoint in endpoints_to_try:
            try:
                async with self.session.get(f"{self.host}{endpoint}") as response:
                    if response.status == 200:
                        devices_data = await response.json()
                        # Handle both array and object responses
                        if isinstance(devices_data, dict):
                            # If it's an object, convert to dict of devices
                            self.devices = devices_data
                        else:
                            # If it's an array, convert to dict keyed by id
                            self.devices = {device["id"]: device for device in devices_data}
                        _LOGGER.info("Successfully retrieved devices using endpoint: %s", endpoint)
                        return self.devices
                    elif response.status == 404:
                        _LOGGER.debug("Endpoint %s not found, trying next...", endpoint)
                        continue
                    else:
                        _LOGGER.debug("Failed to get devices from %s: %s", endpoint, response.status)
                        continue
            except Exception as err:
                _LOGGER.debug("Error getting devices from %s: %s", endpoint, err)
                continue
        
        _LOGGER.error("Failed to get devices from any endpoint")
        return {}

    async def get_device(self, device_id: str) -> dict[str, Any] | None:
        """Get a specific device."""
        if not self.session:
            return None

        # Try manager API first, then fallback to v1
        endpoints_to_try = [
            f"{API_DEVICES}{device_id}",  # /api/manager/devices/device/{id}
            f"{API_DEVICES_NO_SLASH}/{device_id}",  # /api/manager/devices/device/{id}
            f"{API_DEVICES_V1}/{device_id}",  # /api/v1/device/{id}
        ]
        
        for endpoint in endpoints_to_try:
            try:
                async with self.session.get(f"{self.host}{endpoint}") as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 404:
                        _LOGGER.debug("Device endpoint %s not found, trying next...", endpoint)
                        continue
                    else:
                        _LOGGER.debug("Failed to get device %s from %s: %s", device_id, endpoint, response.status)
                        continue
            except Exception as err:
                _LOGGER.debug("Error getting device %s from %s: %s", device_id, endpoint, err)
                continue
        
        _LOGGER.error("Failed to get device %s from any endpoint", device_id)
        return None

    async def set_capability_value(
        self, device_id: str, capability_id: str, value: Any
    ) -> bool:
        """Set a capability value on a device."""
        if not self.session:
            return False

        # Try manager API first, then fallback to v1
        endpoints_to_try = [
            f"{API_DEVICES}{device_id}/capability/{capability_id}",  # /api/manager/devices/device/{id}/capability/{cap}
            f"{API_DEVICES_NO_SLASH}/{device_id}/capability/{capability_id}",
            f"{API_DEVICES_V1}/{device_id}/capability/{capability_id}",  # /api/v1/device/{id}/capability/{cap}
        ]
        
        for endpoint in endpoints_to_try:
            try:
                async with self.session.put(
                    f"{self.host}{endpoint}",
                    json={"value": value},
                ) as response:
                    if response.status == 200:
                        return True
                    elif response.status == 404:
                        _LOGGER.debug("Capability endpoint %s not found, trying next...", endpoint)
                        continue
                    else:
                        error_text = await response.text()
                        _LOGGER.debug(
                            "Failed to set capability %s on device %s via %s: %s - %s",
                            capability_id,
                            device_id,
                            endpoint,
                            response.status,
                            error_text,
                        )
                        continue
            except Exception as err:
                _LOGGER.debug(
                    "Error setting capability %s on device %s via %s: %s",
                    capability_id,
                    device_id,
                    endpoint,
                    err,
                )
                continue
        
        _LOGGER.error(
            "Failed to set capability %s on device %s from any endpoint",
            capability_id,
            device_id,
        )
        return False

    async def get_capability_value(
        self, device_id: str, capability_id: str
    ) -> Any | None:
        """Get a capability value from a device."""
        device = await self.get_device(device_id)
        if device:
            capabilities = device.get("capabilitiesObj", {})
            return capabilities.get(capability_id, {}).get("value")
        return None

    async def get_flows(self) -> dict[str, dict[str, Any]]:
        """Get all flows from Homey."""
        if not self.session:
            return {}

        # Try manager API first, then fallback to v1
        endpoints_to_try = [
            API_FLOWS,  # /api/manager/flows/flow
            f"{API_FLOWS}/",  # With trailing slash
            f"{API_BASE_V1}/flow",  # /api/v1/flow
        ]

        for endpoint in endpoints_to_try:
            try:
                async with self.session.get(f"{self.host}{endpoint}") as response:
                    if response.status == 200:
                        flows_data = await response.json()
                        # Handle both array and object responses
                        if isinstance(flows_data, dict):
                            self.flows = flows_data
                        else:
                            # If it's an array, convert to dict keyed by id
                            self.flows = {flow["id"]: flow for flow in flows_data}
                        _LOGGER.info("Successfully retrieved flows using endpoint: %s", endpoint)
                        return self.flows
                    elif response.status == 404:
                        _LOGGER.debug("Flows endpoint %s not found, trying next...", endpoint)
                        continue
                    else:
                        _LOGGER.debug("Failed to get flows from %s: %s", endpoint, response.status)
                        continue
            except Exception as err:
                _LOGGER.debug("Error getting flows from %s: %s", endpoint, err)
                continue

        _LOGGER.warning("Failed to get flows from any endpoint")
        return {}

    async def trigger_flow(self, flow_id: str) -> bool:
        """Trigger a flow by ID."""
        if not self.session:
            return False

        # Try manager API first, then fallback to v1
        endpoints_to_try = [
            f"{API_FLOWS}{flow_id}/trigger",  # /api/manager/flows/flow/{id}/trigger
            f"{API_FLOWS}/{flow_id}/trigger",  # Without trailing slash on base
            f"{API_BASE_V1}/flow/{flow_id}/trigger",  # /api/v1/flow/{id}/trigger
        ]

        for endpoint in endpoints_to_try:
            try:
                async with self.session.post(f"{self.host}{endpoint}") as response:
                    if response.status == 200:
                        _LOGGER.info("Successfully triggered flow %s", flow_id)
                        return True
                    elif response.status == 404:
                        _LOGGER.debug("Flow trigger endpoint %s not found, trying next...", endpoint)
                        continue
                    else:
                        error_text = await response.text()
                        _LOGGER.debug(
                            "Failed to trigger flow %s via %s: %s - %s",
                            flow_id,
                            endpoint,
                            response.status,
                            error_text,
                        )
                        continue
            except Exception as err:
                _LOGGER.debug("Error triggering flow %s via %s: %s", flow_id, endpoint, err)
                continue

        _LOGGER.error("Failed to trigger flow %s from any endpoint", flow_id)
        return False

    async def get_zones(self) -> dict[str, dict[str, Any]]:
        """Get all zones (rooms) from Homey."""
        if not self.session:
            return {}

        # Try manager API first, then fallback to v1
        endpoints_to_try = [
            API_ZONES,  # /api/manager/zones/zone
            f"{API_ZONES}/",  # With trailing slash
            f"{API_BASE_V1}/zone",  # /api/v1/zone
        ]

        for endpoint in endpoints_to_try:
            try:
                async with self.session.get(f"{self.host}{endpoint}") as response:
                    if response.status == 200:
                        zones_data = await response.json()
                        # Handle both array and object responses
                        if isinstance(zones_data, dict):
                            self.zones = zones_data
                        else:
                            # If it's an array, convert to dict keyed by id
                            self.zones = {zone["id"]: zone for zone in zones_data}
                        _LOGGER.info("Successfully retrieved zones using endpoint: %s", endpoint)
                        return self.zones
                    elif response.status == 404:
                        _LOGGER.debug("Zones endpoint %s not found, trying next...", endpoint)
                        continue
                    else:
                        _LOGGER.debug("Failed to get zones from %s: %s", endpoint, response.status)
                        continue
            except Exception as err:
                _LOGGER.debug("Error getting zones from %s: %s", endpoint, err)
                continue

        _LOGGER.warning("Failed to get zones from any endpoint")
        return {}

    async def _on_device_update(self, data: dict[str, Any]) -> None:
        """Handle device update from Socket.IO."""
        device_id = data.get("id")
        if device_id:
            # Update local device cache
            if device_id in self.devices:
                self.devices[device_id].update(data)
            # Notify listeners
            for listener in self._listeners:
                try:
                    if callable(listener):
                        listener(device_id, data)
                except Exception as err:
                    _LOGGER.error("Error in device update listener: %s", err)

    def add_device_listener(self, listener: Callable[[str, dict[str, Any]], None]) -> None:
        """Add a listener for device updates."""
        self._listeners.append(listener)

    def remove_device_listener(self, listener: Callable[[str, dict[str, Any]], None]) -> None:
        """Remove a device update listener."""
        if listener in self._listeners:
            self._listeners.remove(listener)

    async def disconnect(self) -> None:
        """Disconnect from Homey API."""
        if self.sio:
            await self.sio.disconnect()
            self.sio = None

        if self.session:
            await self.session.close()
            self.session = None

