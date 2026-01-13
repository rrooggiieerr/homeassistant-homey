"""Homey API client."""
from __future__ import annotations

import asyncio
import logging
import ssl
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
    API_ADVANCED_FLOWS,
    API_SYSTEM,
    API_ZONES,
    API_SCENES,
    API_MOODS,
)
from .permissions import PermissionChecker

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
        self.homey_id: str | None = None  # Homey device ID for Socket.IO authentication
        self.sio_namespace: str | None = None  # Namespace received from handshakeClient
        self.devices: dict[str, dict[str, Any]] = {}
        self.flows: dict[str, dict[str, Any]] = {}
        self.zones: dict[str, dict[str, Any]] = {}  # Rooms/zones
        self.scenes: dict[str, dict[str, Any]] = {}  # Scenes
        self.moods: dict[str, dict[str, Any]] = {}  # Moods
        self._listeners: list[Callable[[str, dict[str, Any]], None]] = []
        self._sio_connected: bool = False
        self._sio_reconnect_task: asyncio.Task | None = None
        self._sio_reconnect_interval: int = 60  # Try to reconnect every 60 seconds
        self._sio_last_reconnect_attempt: float = 0

    async def connect(self) -> None:
        """Connect to Homey API."""
        # Detect if using HTTPS for SSL handling
        # For HTTPS connections (self-hosted servers), we need SSL but disable verification for self-signed certs
        # For HTTP connections (local Homey), disable SSL entirely
        use_https = self.host.startswith("https://")
        if use_https:
            # For HTTPS: create SSL context that doesn't verify certificates (for self-signed certs)
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            connector = aiohttp.TCPConnector(ssl=ssl_context)
        else:
            # For HTTP: disable SSL entirely
            connector = aiohttp.TCPConnector(ssl=False)
        self.session = aiohttp.ClientSession(
            connector=connector,
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=aiohttp.ClientTimeout(total=30),
        )

        # Socket.IO connection will be established after authentication
        # We need homeyId from system info first, so Socket.IO is initialized later
        self.sio = None
        self._sio_connected = False

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
                        # Store homeyId for Socket.IO authentication
                        # Try multiple possible fields: cloudId (from system.getInfo()), id, homeyId
                        self.homey_id = (
                            system_info.get("cloudId") or 
                            system_info.get("id") or 
                            system_info.get("homeyId")
                        )
                        _LOGGER.info("Connected to Homey: %s (ID: %s)", 
                                   system_info.get("name") or system_info.get("homeyName") or system_info.get("hostname", "").split(".")[0],
                                   self.homey_id or "unknown")
                        # Attempt Socket.IO connection after successful authentication
                        # This is non-blocking - if it fails, we'll use polling
                        try:
                            await self._connect_socketio()
                        except Exception as err:
                            _LOGGER.debug("Socket.IO connection attempt failed: %s - will use polling", err)
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

        # Validate and convert value to appropriate type
        # Handle cases where Home Assistant might pass strings instead of numbers
        converted_value = self._convert_capability_value(capability_id, value)
        
        if converted_value is None:
            _LOGGER.error(
                "Invalid value for capability %s on device %s: %s (type: %s)",
                capability_id,
                device_id,
                value,
                type(value).__name__,
            )
            return False

        # Try multiple endpoint patterns and HTTP methods
        # Use preferred_endpoint if available, otherwise try all
        if self.preferred_endpoint == "manager":
            base_endpoints = [
                (API_DEVICES, "manager"),
                (API_DEVICES_NO_SLASH, "manager"),
            ]
        elif self.preferred_endpoint == "v1":
            base_endpoints = [
                (API_DEVICES_V1, "v1"),
            ]
        else:
            base_endpoints = [
                (API_DEVICES, "manager"),
                (API_DEVICES_NO_SLASH, "manager"),
                (API_DEVICES_V1, "v1"),
            ]
        
        endpoints_to_try = []
        for base_endpoint, _ in base_endpoints:
            # Try different endpoint formats
            # Format 1: /api/manager/devices/device/{id}/capability/{cap}
            endpoints_to_try.append((f"{base_endpoint}{device_id}/capability/{capability_id}", "PUT"))
            # Format 2: /api/manager/devices/device/{id}/capability/{cap}/ (with trailing slash)
            endpoints_to_try.append((f"{base_endpoint}{device_id}/capability/{capability_id}/", "PUT"))
            # Format 3: /api/manager/devices/device/{id}/capability/{cap} (without trailing slash on base)
            if base_endpoint.endswith("/"):
                endpoints_to_try.append((f"{base_endpoint[:-1]}/{device_id}/capability/{capability_id}", "PUT"))
            # Try POST as well
            endpoints_to_try.append((f"{base_endpoint}{device_id}/capability/{capability_id}", "POST"))
            endpoints_to_try.append((f"{base_endpoint}{device_id}/capability/{capability_id}/", "POST"))
            if base_endpoint.endswith("/"):
                endpoints_to_try.append((f"{base_endpoint[:-1]}/{device_id}/capability/{capability_id}", "POST"))
        
        for endpoint, method in endpoints_to_try:
            try:
                if method == "PUT":
                    async with self.session.put(
                        f"{self.host}{endpoint}",
                        json={"value": converted_value},
                    ) as response:
                        if response.status == 200 or response.status == 204:
                            _LOGGER.debug("Successfully set capability %s=%s on device %s via %s", capability_id, converted_value, device_id, endpoint)
                            return True
                        elif response.status == 404:
                            _LOGGER.debug("Capability endpoint %s not found, trying next...", endpoint)
                            continue
                        elif response.status in (401, 403):
                            PermissionChecker.check_permission(
                                response.status, "devices", "write", f"set_capability({capability_id})"
                            )
                            continue
                        else:
                            error_text = await response.text()
                            _LOGGER.info(
                                "Failed to set capability %s=%s on device %s via %s (%s): %s - %s",
                                capability_id,
                                converted_value,
                                device_id,
                                endpoint,
                                method,
                                response.status,
                                error_text[:200] if error_text else "No error text",
                            )
                            continue
                else:  # POST
                    async with self.session.post(
                        f"{self.host}{endpoint}",
                        json={"value": converted_value},
                    ) as response:
                        if response.status == 200 or response.status == 204:
                            _LOGGER.debug("Successfully set capability %s=%s on device %s via %s", capability_id, converted_value, device_id, endpoint)
                            return True
                        elif response.status == 404:
                            _LOGGER.debug("Capability endpoint %s not found, trying next...", endpoint)
                            continue
                        elif response.status in (401, 403):
                            PermissionChecker.check_permission(
                                response.status, "devices", "write", f"set_capability({capability_id})"
                            )
                            continue
                        else:
                            error_text = await response.text()
                            _LOGGER.debug(
                                "Failed to set capability %s=%s on device %s via %s (%s): %s - %s",
                                capability_id,
                                converted_value,
                                device_id,
                                endpoint,
                                method,
                                response.status,
                                error_text[:200] if error_text else "No error text",
                            )
                            continue
            except Exception as err:
                _LOGGER.debug(
                    "Exception setting capability %s=%s on device %s via %s (%s): %s",
                    capability_id,
                    converted_value,
                    device_id,
                    endpoint,
                    method,
                    err,
                )
                continue
        
        # Log all endpoints we tried for debugging
        _LOGGER.error(
            "Failed to set capability %s=%s on device %s from any endpoint. Tried %d endpoints: %s",
            capability_id,
            converted_value,
            device_id,
            len(endpoints_to_try),
            [f"{endpoint} ({method})" for endpoint, method in endpoints_to_try[:5]],  # Show first 5
        )
        return False

    def _convert_capability_value(self, capability_id: str, value: Any) -> Any:
        """Convert value to appropriate type and format for the capability.
        
        Homey API uses normalized values (0-1) for many capabilities, while
        Home Assistant uses different ranges. This function handles the conversion.
        
        Format conversions:
        - light_hue: HA 0-360 → Homey 0-1 (handled in light.py before calling this)
        - light_saturation: HA 0-100 → Homey 0-1 (handled in light.py before calling this)
        - dim: HA 0-255 → Homey 0-1 (handled in light.py before calling this)
        - fan_speed: HA 0-100 → Homey 0-1 (handled in fan.py before calling this)
        - windowcoverings_state: HA 0-100 → Homey 0-1 (handled in cover.py before calling this)
        - volume_set: HA 0.0-1.0 → Homey 0-1 (no conversion needed, both normalized)
        - light_temperature: Both use Kelvin, no conversion needed
        - target_temperature: Both use Celsius, no conversion needed
        """
        # Handle None values
        if value is None:
            return None
        
        # Handle boolean capabilities
        if capability_id == "onoff" or capability_id == "locked" or capability_id == "volume_mute":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                value_lower = value.lower().strip()
                if value_lower in ("true", "1", "on", "yes"):
                    return True
                if value_lower in ("false", "0", "off", "no"):
                    return False
            # Try to convert to bool
            try:
                return bool(int(value))
            except (ValueError, TypeError):
                _LOGGER.warning("Cannot convert %s to boolean for capability %s", value, capability_id)
                return None
        
        # Handle windowcoverings_state specially - can be enum ("up", "idle", "down") or numeric (0-1)
        if capability_id == "windowcoverings_state":
            # Check if it's an enum string value first
            if isinstance(value, str):
                value_stripped = value.strip().lower()
                # Valid enum values for windowcoverings_state
                if value_stripped in ("up", "idle", "down"):
                    return value_stripped  # Return the enum string as-is
            
            # If not an enum string, treat as numeric (for numeric windowcoverings_state devices)
            if isinstance(value, (int, float)):
                return float(value)
            
            if isinstance(value, str):
                value_stripped = value.strip()
                # Try to convert to float for numeric windowcoverings_state
                if value_stripped.replace(".", "").replace("-", "").isdigit():
                    try:
                        return float(value_stripped)
                    except (ValueError, TypeError):
                        pass
            
            # If we get here, it's neither a valid enum nor a valid number
            _LOGGER.warning(
                "Invalid value for capability %s: %s (must be 'up', 'idle', 'down', or a number)",
                capability_id,
                value[:50] if len(str(value)) > 50 else value,
            )
            return None
        
        # Handle numeric capabilities - reject non-numeric strings
        numeric_capabilities = [
            "dim", "light_hue", "light_saturation", "light_temperature",
            "target_temperature", "measure_temperature", "fan_speed",
            "volume_set",
        ]
        
        if capability_id in numeric_capabilities:
            # If it's already a number, return it
            # Note: Format conversions (e.g., 0-360 → 0-1) are handled in platform files
            # before calling this function, so we just need to ensure it's a float
            if isinstance(value, (int, float)):
                return float(value)
            
            # If it's a string, try to convert it
            if isinstance(value, str):
                value_stripped = value.strip()
                # Reject strings that look like errors (e.g., "idleidleidle...")
                if not value_stripped or not value_stripped.replace(".", "").replace("-", "").isdigit():
                    _LOGGER.warning(
                        "Invalid numeric value for capability %s: %s (appears to be a string, not a number)",
                        capability_id,
                        value[:50] if len(str(value)) > 50 else value,
                    )
                    return None
                try:
                    return float(value_stripped)
                except (ValueError, TypeError):
                    _LOGGER.warning("Cannot convert %s to float for capability %s", value, capability_id)
                    return None
            
            # For other types, try to convert
            try:
                return float(value)
            except (ValueError, TypeError):
                _LOGGER.warning("Cannot convert %s to float for capability %s", value, capability_id)
                return None
        
        # For other capabilities, return as-is but log if it's an unexpected string
        if isinstance(value, str) and len(value) > 50:
            _LOGGER.debug("Long string value for capability %s: %s...", capability_id, value[:50])
        
        return value

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
        """Get all flows from Homey (both Standard and Advanced Flows)."""
        if not self.session:
            return {}

        self.flows = {}
        
        # First, get Standard Flows from /api/manager/flow/flow
        endpoints_to_try = [
            API_FLOWS,  # /api/manager/flow/flow (correct endpoint per API docs)
            f"{API_FLOWS}/",  # With trailing slash
            # Fallback variations (in case API structure varies)
            f"{API_BASE_MANAGER}/flows/flow",  # /api/manager/flows/flow (plural - old/incorrect)
            f"{API_BASE_MANAGER}/flows/flow/",  # With trailing slash
            f"{API_BASE_V1}/flow",  # /api/v1/flow
            f"{API_BASE_V1}/flow/",  # With trailing slash
        ]

        auth_error_count = 0
        standard_flows_found = False
        
        for endpoint in endpoints_to_try:
            try:
                async with self.session.get(f"{self.host}{endpoint}") as response:
                    if response.status == 200:
                        flows_data = await response.json()
                        # Handle both array and object responses
                        if isinstance(flows_data, dict):
                            standard_flows = flows_data
                        else:
                            # If it's an array, convert to dict keyed by id
                            standard_flows = {flow["id"]: flow for flow in flows_data}
                        
                        # Mark as standard flows and add to collection
                        for fid, flow in standard_flows.items():
                            flow["_flow_type"] = "standard"  # Mark as standard flow
                            self.flows[fid] = flow
                        
                        standard_flows_found = True
                        break
                    elif response.status == 401:
                        auth_error_count += 1
                        _LOGGER.warning("Authentication failed (401) for flows endpoint %s - check homey.flow.readonly permission", endpoint)
                        continue
                    elif response.status == 403:
                        auth_error_count += 1
                        _LOGGER.warning("Forbidden (403) for flows endpoint %s - check homey.flow.readonly permission", endpoint)
                        continue
                    elif response.status == 404:
                        continue
                    else:
                        continue
            except Exception as err:
                continue
        
        # Now get Advanced Flows from /api/manager/flow/advancedflow
        advanced_endpoints_to_try = [
            API_ADVANCED_FLOWS,  # /api/manager/flow/advancedflow
            f"{API_ADVANCED_FLOWS}/",  # With trailing slash
        ]
        
        advanced_flows_found = False
        for endpoint in advanced_endpoints_to_try:
            try:
                async with self.session.get(f"{self.host}{endpoint}") as response:
                    if response.status == 200:
                        flows_data = await response.json()
                        # Handle both array and object responses
                        if isinstance(flows_data, dict):
                            advanced_flows = flows_data
                        else:
                            # If it's an array, convert to dict keyed by id
                            advanced_flows = {flow["id"]: flow for flow in flows_data}
                        
                        # Mark as advanced flows and add to collection
                        for fid, flow in advanced_flows.items():
                            flow["_flow_type"] = "advanced"  # Mark as advanced flow
                            self.flows[fid] = flow
                        
                        advanced_flows_found = True
                        break
                    elif response.status == 401:
                        auth_error_count += 1
                        _LOGGER.warning("Authentication failed (401) for advanced flows endpoint %s - check flow:read permission", endpoint)
                        continue
                    elif response.status == 403:
                        auth_error_count += 1
                        _LOGGER.warning("Forbidden (403) for advanced flows endpoint %s - check flow:read permission", endpoint)
                        continue
                    elif response.status == 404:
                        continue
                    else:
                        continue
            except Exception as err:
                continue
        
        if self.flows:
            return self.flows
        
        # If all endpoints returned 401/403, it's a permission issue
        total_endpoints = len(endpoints_to_try) + len(advanced_endpoints_to_try)
        if auth_error_count > 0 and auth_error_count == total_endpoints:
            _LOGGER.error("All flows endpoints returned authentication errors (401/403). Please check that your API key has 'homey.flow.readonly' permission enabled in Homey Settings → API Keys.")
        elif auth_error_count > 0:
            _LOGGER.warning("Some flows endpoints returned authentication errors. Please check that your API key has 'homey.flow.readonly' permission enabled in Homey Settings → API Keys.")
        else:
            # No auth errors but no flows - user just doesn't have flows configured or feature not available
            _LOGGER.debug("No flows found - this is normal if you don't have any flows configured in Homey")
        return {}

    async def trigger_flow(self, flow_id: str) -> bool:
        """Trigger a flow by ID (supports both Standard and Advanced Flows)."""
        if not self.session:
            return False

        # Check if this is an Advanced Flow by looking it up in our flows cache
        flow_type = None
        if flow_id in self.flows:
            flow_type = self.flows[flow_id].get("_flow_type")
        
        # Build endpoints to try based on flow type
        endpoints_to_try = []
        
        if flow_type == "advanced":
            # Advanced Flows use: POST /api/manager/flow/advancedflow/:id/trigger
            endpoints_to_try = [
                (f"{API_ADVANCED_FLOWS}/{flow_id}/trigger", "POST"),  # /api/manager/flow/advancedflow/{id}/trigger
                (f"{API_ADVANCED_FLOWS}/{flow_id}/trigger/", "POST"),  # With trailing slash
            ]
        elif flow_type == "standard":
            # Standard Flows use: POST /api/manager/flow/flow/:id/trigger
            endpoints_to_try = [
                (f"{API_FLOWS}/{flow_id}/trigger", "POST"),  # /api/manager/flow/flow/{id}/trigger
                (f"{API_FLOWS}/{flow_id}/trigger/", "POST"),  # With trailing slash
            ]
        else:
            # Unknown type - try both endpoints
            endpoints_to_try = [
                (f"{API_FLOWS}/{flow_id}/trigger", "POST"),  # Standard flow endpoint
                (f"{API_FLOWS}/{flow_id}/trigger/", "POST"),  # With trailing slash
                (f"{API_ADVANCED_FLOWS}/{flow_id}/trigger", "POST"),  # Advanced flow endpoint
                (f"{API_ADVANCED_FLOWS}/{flow_id}/trigger/", "POST"),  # With trailing slash
                # Fallback variations
                (f"{API_BASE_MANAGER}/flows/flow/{flow_id}/trigger", "POST"),  # Old/incorrect
                (f"{API_FLOWS}/{flow_id}/run", "PUT"),  # Alternative trigger method
                (f"{API_FLOWS}/{flow_id}/run", "POST"),  # POST to /run
                (f"{API_BASE_V1}/flow/{flow_id}/trigger", "POST"),  # V1 endpoint
                (f"{API_BASE_V1}/flow/{flow_id}/run", "PUT"),  # V1 run endpoint
            ]

        for endpoint, method in endpoints_to_try:
            try:
                url = f"{self.host}{endpoint}"
                
                if method == "POST":
                    async with self.session.post(url) as response:
                        status = response.status
                        if status == 200 or status == 204:
                            return True
                        elif status == 404:
                            continue
                        else:
                            continue
                else:  # PUT
                    async with self.session.put(url) as response:
                        status = response.status
                        if status == 200 or status == 204:
                            return True
                        elif status == 404:
                            continue
                        else:
                            continue
            except Exception as err:
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

        auth_error_count = 0
        for endpoint in endpoints_to_try:
            try:
                async with self.session.get(f"{self.host}{endpoint}") as response:
                    if response.status == 200:
                        zones_data = await response.json()
                        # Handle both array and object responses
                        if isinstance(zones_data, dict):
                            self.zones = zones_data
                        elif isinstance(zones_data, list):
                            # If it's an array, convert to dict keyed by id
                            self.zones = {zone["id"]: zone for zone in zones_data}
                        else:
                            # Empty or unexpected response
                            self.zones = {}
                        
                        # If we got a successful response but no zones, that's OK - user just doesn't have zones
                        if not self.zones:
                            _LOGGER.debug("Zones endpoint returned empty result - no zones/rooms configured in Homey")
                        else:
                            _LOGGER.info("Successfully retrieved %d zones using endpoint: %s", len(self.zones), endpoint)
                        return self.zones
                    elif response.status == 404:
                        _LOGGER.debug("Zones endpoint %s not found, trying next...", endpoint)
                        continue
                    elif response.status in (401, 403):
                        auth_error_count += 1
                        PermissionChecker.check_permission(response.status, "zones", "read", "get_zones")
                        continue
                    else:
                        _LOGGER.debug("Failed to get zones from %s: %s", endpoint, response.status)
                        continue
            except Exception as err:
                _LOGGER.debug("Error getting zones from %s: %s", endpoint, err)
                continue

        # Only log permission warning if we got auth errors, not if endpoints just don't exist
        if auth_error_count > 0:
            _LOGGER.warning("Failed to get zones from any endpoint - permission issue")
            PermissionChecker.log_missing_permission(
                "zones",
                "read",
                "Devices will not be organized by Homey rooms/areas. They will appear without room grouping.",
            )
        else:
            _LOGGER.debug("Zones endpoint not available - zones may not be supported or configured on this Homey")
        return {}

    async def get_scenes(self) -> dict[str, dict[str, Any]]:
        """Get all scenes from Homey."""
        if not self.session:
            return {}

        endpoints_to_try = [
            API_SCENES,  # /api/manager/scene/scene
            f"{API_SCENES}/",  # With trailing slash
            f"{API_BASE_MANAGER}/scenes/scene",  # Plural variation
            f"{API_BASE_MANAGER}/scenes/scene/",  # With trailing slash
            f"{API_BASE_V1}/scene",  # V1 endpoint
            f"{API_BASE_V1}/scene/",  # With trailing slash
        ]

        auth_error_count = 0
        for endpoint in endpoints_to_try:
            try:
                async with self.session.get(f"{self.host}{endpoint}") as response:
                    if response.status == 200:
                        scenes_data = await response.json()
                        # Handle both array and object responses
                        if isinstance(scenes_data, dict):
                            self.scenes = scenes_data
                        elif isinstance(scenes_data, list):
                            # If it's an array, convert to dict keyed by id
                            self.scenes = {scene["id"]: scene for scene in scenes_data}
                        else:
                            # Empty or unexpected response - feature may not be available
                            self.scenes = {}
                        
                        # If we got a successful response but no scenes, that's OK - user just doesn't have scenes
                        if not self.scenes:
                            _LOGGER.debug("Scenes endpoint returned empty result - no scenes configured in Homey")
                        else:
                            _LOGGER.info("Successfully retrieved %d scenes using endpoint: %s", len(self.scenes), endpoint)
                        return self.scenes
                    elif response.status == 404:
                        _LOGGER.debug("Scenes endpoint %s not found, trying next...", endpoint)
                        continue
                    elif response.status in (401, 403):
                        auth_error_count += 1
                        PermissionChecker.check_permission(response.status, "scenes", "read", "get_scenes")
                        continue
                    else:
                        _LOGGER.debug("Failed to get scenes from %s: %s", endpoint, response.status)
                        continue
            except Exception as err:
                _LOGGER.debug("Error getting scenes from %s: %s", endpoint, err)
                continue

        # Only log permission warning if we got auth errors, not if endpoints just don't exist
        if auth_error_count > 0:
            _LOGGER.warning("Failed to get scenes from any endpoint - permission issue")
            PermissionChecker.log_missing_permission(
                "scenes",
                "read",
                "Scene entities will not be created. You won't be able to activate Homey scenes from Home Assistant.",
            )
        else:
            _LOGGER.debug("Scenes endpoint not available - scenes may not be supported or configured on this Homey")
        return {}

    async def trigger_scene(self, scene_id: str) -> bool:
        """Trigger a scene by ID."""
        if not self.session:
            return False

        endpoints_to_try = [
            f"{API_SCENES}/{scene_id}/trigger",  # /api/manager/scene/scene/{id}/trigger
            f"{API_SCENES}/{scene_id}/trigger/",  # With trailing slash
            f"{API_BASE_MANAGER}/scenes/scene/{scene_id}/trigger",  # Plural variation
            f"{API_BASE_V1}/scene/{scene_id}/trigger",  # V1 endpoint
            f"{API_SCENES}/{scene_id}/run",  # Alternative trigger method
            f"{API_SCENES}/{scene_id}/activate",  # Alternative activate method
        ]

        for endpoint in endpoints_to_try:
            try:
                async with self.session.post(f"{self.host}{endpoint}") as response:
                    if response.status == 200 or response.status == 204:
                        _LOGGER.debug("Successfully triggered scene %s via %s", scene_id, endpoint)
                        return True
                    elif response.status == 404:
                        continue
                    elif response.status in (401, 403):
                        PermissionChecker.check_permission(response.status, "scenes", "write", f"trigger_scene({scene_id})")
                        continue
                    else:
                        continue
            except Exception as err:
                _LOGGER.debug("Error triggering scene %s via %s: %s", scene_id, endpoint, err)
                continue

        _LOGGER.error("Failed to trigger scene %s from any endpoint", scene_id)
        return False

    async def get_moods(self) -> dict[str, dict[str, Any]]:
        """Get all moods from Homey."""
        if not self.session:
            return {}

        endpoints_to_try = [
            API_MOODS,  # /api/manager/moods/mood (correct per API v3)
            f"{API_MOODS}/",  # With trailing slash
            f"{API_BASE_MANAGER}/mood/mood",  # Singular variation (fallback)
            f"{API_BASE_MANAGER}/mood/mood/",  # With trailing slash
            f"{API_BASE_V1}/mood",  # V1 endpoint
            f"{API_BASE_V1}/mood/",  # With trailing slash
        ]

        auth_error_count = 0
        for endpoint in endpoints_to_try:
            try:
                async with self.session.get(f"{self.host}{endpoint}") as response:
                    if response.status == 200:
                        moods_data = await response.json()
                        # Handle both array and object responses
                        if isinstance(moods_data, dict):
                            self.moods = moods_data
                        elif isinstance(moods_data, list):
                            # If it's an array, convert to dict keyed by id
                            self.moods = {mood["id"]: mood for mood in moods_data}
                        else:
                            # Empty or unexpected response - feature may not be available
                            self.moods = {}
                        
                        # If we got a successful response but no moods, that's OK - user just doesn't have moods
                        if not self.moods:
                            _LOGGER.debug("Moods endpoint returned empty result - no moods configured in Homey")
                        else:
                            _LOGGER.info("Successfully retrieved %d moods using endpoint: %s", len(self.moods), endpoint)
                        return self.moods
                    elif response.status == 404:
                        _LOGGER.debug("Moods endpoint %s not found, trying next...", endpoint)
                        continue
                    elif response.status in (401, 403):
                        auth_error_count += 1
                        PermissionChecker.check_permission(response.status, "moods", "read", "get_moods")
                        continue
                    else:
                        _LOGGER.debug("Failed to get moods from %s: %s", endpoint, response.status)
                        continue
            except Exception as err:
                _LOGGER.debug("Error getting moods from %s: %s", endpoint, err)
                continue

        # Only log permission warning if we got auth errors, not if endpoints just don't exist or feature isn't configured
        if auth_error_count > 0:
            _LOGGER.warning("Failed to get moods from any endpoint - permission issue")
            PermissionChecker.log_missing_permission(
                "moods",
                "read",
                "Mood entities will not be created. You won't be able to activate Homey moods from Home Assistant.",
            )
        else:
            _LOGGER.debug("Moods endpoint not available - moods may not be supported or configured on this Homey")
        return {}

    async def trigger_mood(self, mood_id: str) -> bool:
        """Trigger a mood by ID."""
        if not self.session:
            return False

        endpoints_to_try = [
            f"{API_MOODS}/{mood_id}/set",  # /api/manager/moods/mood/{id}/set (correct per API v3)
            f"{API_MOODS}/{mood_id}/set/",  # With trailing slash
            f"{API_BASE_MANAGER}/mood/mood/{mood_id}/set",  # Singular variation (fallback)
            f"{API_BASE_MANAGER}/mood/mood/{mood_id}/set/",  # With trailing slash
            f"{API_MOODS}/{mood_id}/trigger",  # Alternative trigger method
            f"{API_MOODS}/{mood_id}/trigger/",  # With trailing slash
            f"{API_BASE_V1}/mood/{mood_id}/set",  # V1 endpoint with /set
            f"{API_BASE_V1}/mood/{mood_id}/trigger",  # V1 endpoint
            f"{API_MOODS}/{mood_id}/run",  # Alternative trigger method
            f"{API_MOODS}/{mood_id}/activate",  # Alternative activate method
        ]

        for endpoint in endpoints_to_try:
            try:
                async with self.session.post(f"{self.host}{endpoint}") as response:
                    if response.status == 200 or response.status == 204:
                        _LOGGER.debug("Successfully triggered mood %s via %s", mood_id, endpoint)
                        return True
                    elif response.status == 404:
                        _LOGGER.debug("Mood trigger endpoint %s not found (404), trying next...", endpoint)
                        continue
                    elif response.status in (401, 403):
                        _LOGGER.debug("Mood trigger endpoint %s returned %s (permission denied)", endpoint, response.status)
                        PermissionChecker.check_permission(response.status, "moods", "write", f"trigger_mood({mood_id})")
                        continue
                    else:
                        # Log other status codes to help debug
                        try:
                            error_text = await response.text()
                            _LOGGER.debug("Mood trigger endpoint %s returned status %s: %s", endpoint, response.status, error_text[:200])
                        except:
                            _LOGGER.debug("Mood trigger endpoint %s returned status %s", endpoint, response.status)
                        continue
            except Exception as err:
                _LOGGER.debug("Error triggering mood %s via %s: %s", mood_id, endpoint, err)
                continue

        _LOGGER.error("Failed to trigger mood %s from any endpoint", mood_id)
        return False

    async def enable_flow(self, flow_id: str) -> bool:
        """Enable a flow by ID."""
        if not self.session:
            return False

        # Try to enable flow via PUT/PATCH to flow endpoint
        endpoints_to_try = [
            (f"{API_FLOWS}/{flow_id}", "PATCH"),  # Standard flow
            (f"{API_FLOWS}/{flow_id}/", "PATCH"),  # With trailing slash
            (f"{API_ADVANCED_FLOWS}/{flow_id}", "PATCH"),  # Advanced flow
            (f"{API_ADVANCED_FLOWS}/{flow_id}/", "PATCH"),  # With trailing slash
            (f"{API_FLOWS}/{flow_id}", "PUT"),  # PUT method
            (f"{API_ADVANCED_FLOWS}/{flow_id}", "PUT"),  # PUT method
        ]

        for endpoint, method in endpoints_to_try:
            try:
                url = f"{self.host}{endpoint}"
                data = {"enabled": True}
                
                if method == "PATCH":
                    async with self.session.patch(url, json=data) as response:
                        if response.status in (200, 204):
                            _LOGGER.debug("Successfully enabled flow %s", flow_id)
                            return True
                        elif response.status in (401, 403):
                            PermissionChecker.check_permission(response.status, "flows", "write", f"enable_flow({flow_id})")
                            continue
                else:  # PUT
                    async with self.session.put(url, json=data) as response:
                        if response.status in (200, 204):
                            _LOGGER.debug("Successfully enabled flow %s", flow_id)
                            return True
                        elif response.status in (401, 403):
                            PermissionChecker.check_permission(response.status, "flows", "write", f"enable_flow({flow_id})")
                            continue
            except Exception as err:
                _LOGGER.debug("Error enabling flow %s via %s: %s", flow_id, endpoint, err)
                continue

        _LOGGER.error("Failed to enable flow %s", flow_id)
        return False

    async def disable_flow(self, flow_id: str) -> bool:
        """Disable a flow by ID."""
        if not self.session:
            return False

        # Try to disable flow via PUT/PATCH to flow endpoint
        endpoints_to_try = [
            (f"{API_FLOWS}/{flow_id}", "PATCH"),  # Standard flow
            (f"{API_FLOWS}/{flow_id}/", "PATCH"),  # With trailing slash
            (f"{API_ADVANCED_FLOWS}/{flow_id}", "PATCH"),  # Advanced flow
            (f"{API_ADVANCED_FLOWS}/{flow_id}/", "PATCH"),  # With trailing slash
            (f"{API_FLOWS}/{flow_id}", "PUT"),  # PUT method
            (f"{API_ADVANCED_FLOWS}/{flow_id}", "PUT"),  # PUT method
        ]

        for endpoint, method in endpoints_to_try:
            try:
                url = f"{self.host}{endpoint}"
                data = {"enabled": False}
                
                if method == "PATCH":
                    async with self.session.patch(url, json=data) as response:
                        if response.status in (200, 204):
                            _LOGGER.debug("Successfully disabled flow %s", flow_id)
                            return True
                        elif response.status in (401, 403):
                            PermissionChecker.check_permission(response.status, "flows", "write", f"disable_flow({flow_id})")
                            continue
                else:  # PUT
                    async with self.session.put(url, json=data) as response:
                        if response.status in (200, 204):
                            _LOGGER.debug("Successfully disabled flow %s", flow_id)
                            return True
                        elif response.status in (401, 403):
                            PermissionChecker.check_permission(response.status, "flows", "write", f"disable_flow({flow_id})")
                            continue
            except Exception as err:
                _LOGGER.debug("Error disabling flow %s via %s: %s", flow_id, endpoint, err)
                continue

        _LOGGER.error("Failed to disable flow %s", flow_id)
        return False

    def _on_device_update(self, device_id: str, data: dict[str, Any]) -> None:
        """Handle device update from Socket.IO or polling.
        
        Args:
            device_id: Device ID
            data: Device data dictionary
        """
        if device_id:
            # Update local device cache
            if device_id in self.devices:
                self.devices[device_id].update(data)
            else:
                self.devices[device_id] = data
            # Notify listeners
            for listener in self._listeners:
                try:
                    if callable(listener):
                        listener(device_id, data)
                except Exception as err:
                    _LOGGER.error("Error in device update listener: %s", err)

    async def _connect_socketio(self) -> bool:
        """Connect to Homey Socket.IO server for real-time updates.
        
        Returns True if Socket.IO connection is established, False otherwise.
        Falls back to polling if Socket.IO fails.
        """
        # Note: homeyId might not be available for Local API (API Key) authentication
        # We'll try to connect anyway - some Homey versions might accept just the token
        
        if self._sio_connected and self.sio:
            return True
        
        try:
            # Determine Socket.IO URL (same host as REST API)
            # Socket.IO endpoint is typically /socket.io/ on the same host
            sio_url = self.host.rstrip("/")
            
            # Detect SSL for Socket.IO
            use_https = self.host.startswith("https://")
            
            # Create Socket.IO client with SSL configuration via aiohttp session
            # python-socketio uses aiohttp under the hood, so SSL must be configured through aiohttp
            # pingTimeout: 8000ms, pingInterval: 5000ms per Homey API docs
            
            # Create aiohttp connector with SSL configuration
            if use_https:
                # For HTTPS: create SSL context that doesn't verify certificates (for self-signed certs)
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                connector = aiohttp.TCPConnector(ssl=ssl_context)
            else:
                # For HTTP: disable SSL entirely
                connector = aiohttp.TCPConnector(ssl=False)
            
            # Create aiohttp session with the connector
            http_session = aiohttp.ClientSession(connector=connector)
            
            # Create AsyncClient with the custom HTTP session
            # Disable verbose logging from socketio library (only log warnings/errors)
            import logging
            sio_logger = logging.getLogger("socketio")
            sio_logger.setLevel(logging.WARNING)
            engineio_logger = logging.getLogger("engineio")
            engineio_logger.setLevel(logging.WARNING)
            
            self.sio = socketio.AsyncClient(
                http_session=http_session,
                logger=False,  # Disable socketio verbose logging
                engineio_logger=False,  # Disable engineio verbose logging
            )
            
            # Set up event handlers before connecting
            self.sio.on("connect", self._on_sio_connect)
            self.sio.on("disconnect", self._on_sio_disconnect)
            self.sio.on("connect_error", self._on_sio_connect_error)
            
            # Connect to Socket.IO server
            await self.sio.connect(
                sio_url,
                transports=["websocket"],  # Use websocket transport only
                wait_timeout=10,  # Wait up to 10 seconds for connection
            )
            
            # Wait a moment for connection to establish
            # Note: wait() doesn't accept timeout parameter - connection is already established by connect()
            # Just check if connected
            await asyncio.sleep(0.5)  # Brief pause to ensure connection is fully established
            
            if not self.sio.connected:
                _LOGGER.warning("Socket.IO connection failed - will use polling")
                await self._disconnect_socketio()
                return False
            
            # Authenticate with handshakeClient event
            # This must happen after connection is established
            # Note: For Local API, authentication might not be required or might work differently
            auth_success = await self._authenticate_socketio()
            if not auth_success:
                # Don't fail here - some Homey versions might not require Socket.IO authentication
                # The token is already validated at the HTTP level
                pass
            
            # Subscribe to device events
            # Try subscription even if authentication failed - Local API might work without explicit auth
            subscribe_success = await self._subscribe_device_events()
            if not subscribe_success:
                _LOGGER.warning("Socket.IO device subscription failed - will use polling")
                await self._disconnect_socketio()
                return False
            
            self._sio_connected = True
            _LOGGER.info("Socket.IO connected successfully - real-time updates enabled (polling continues as backup)")
            # Stop any reconnection task since we're connected
            self._stop_sio_reconnect_task()
            return True
            
        except Exception as err:
            _LOGGER.warning("Socket.IO connection error: %s - will use polling", err, exc_info=True)
            await self._disconnect_socketio()
            return False
    
    async def _authenticate_socketio(self) -> bool:
        """Authenticate Socket.IO connection with handshakeClient event.
        
        Returns True if authentication successful, False otherwise.
        """
        if not self.sio or not self.sio.connected:
            return False
        
        if not self.token:
            _LOGGER.error("Cannot authenticate Socket.IO: missing token")
            return False
        
        try:
            # Emit handshakeClient event with token and homeyId
            # According to Homey API docs, this returns a namespace (e.g., "/api")
            # For Local API (API Key), homeyId might be optional - try with token only if homeyId unavailable
            # Prepare handshake data
            handshake_data = {"token": self.token}
            if self.homey_id:
                handshake_data["homeyId"] = self.homey_id
            
            # Use call() for request-response pattern (most reliable)
            try:
                auth_response = await self.sio.call(
                    "handshakeClient",
                    handshake_data,
                    timeout=10
                )
            except Exception as call_err:
                _LOGGER.warning("Socket.IO authentication failed: %s", call_err)
                return False
            
            if auth_response:
                # Response might be the namespace string directly, or a dict with namespace
                if isinstance(auth_response, str):
                    self.sio_namespace = auth_response
                elif isinstance(auth_response, dict):
                    self.sio_namespace = auth_response.get("namespace", "/api")
                else:
                    self.sio_namespace = "/api"  # Default namespace
                
                return True
            else:
                _LOGGER.warning("Socket.IO authentication failed: invalid response")
                return False
                
        except Exception as err:
            _LOGGER.warning("Socket.IO authentication error: %s", err, exc_info=True)
            return False
    
    async def _subscribe_device_events(self) -> bool:
        """Subscribe to device update events via Socket.IO.
        
        Returns True if subscription successful, False otherwise.
        """
        if not self.sio or not self.sio.connected:
            return False
        
        try:
            # Subscribe to all device events using homey:manager:device URI
            # According to Homey API docs, we emit "subscribe" event with URI
            # Note: subscribe might not return a response - it's fire-and-forget
            
            # Set up event handlers BEFORE subscribing (so we don't miss any events)
            # Homey Socket.IO events may come in different formats:
            # - "homey:manager:device" - direct manager events
            # - "device" - generic device events
            # - "device:update" or "device.update" - update events
            # - Events might also come as data within a generic event
            self.sio.on("homey:manager:device", self._on_sio_device_event)
            self.sio.on("device", self._on_sio_device_event)
            self.sio.on("device:update", self._on_sio_device_event)
            self.sio.on("device.update", self._on_sio_device_event)
            # Also listen for any event that might contain device data
            self.sio.on("update", self._on_sio_device_event)
            self.sio.on("message", self._on_sio_device_event)
            
            # Try using call() first (request-response pattern)
            try:
                response = await self.sio.call(
                    "subscribe",
                    {"uri": "homey:manager:device"},
                    timeout=5  # Reduced timeout since subscription might not respond
                )
                if response:
                    return True
            except Exception:
                # Subscription might not return a response - use emit() as fallback
                pass
            
            # Fallback: Use emit() - subscription might be fire-and-forget
            # The server might not send a response, but events will start coming
            await self.sio.emit("subscribe", {"uri": "homey:manager:device"})
            
            # If we got here, subscription was sent (even if no response)
            # Events will come through the handlers we set up above
            return True
                
        except Exception as err:
            _LOGGER.warning("Socket.IO device subscription error: %s", err, exc_info=True)
            return False
    
    def _on_sio_connect(self) -> None:
        """Handle Socket.IO connection event."""
        # Don't set _sio_connected here - wait until authentication and subscription complete
        # This is set in _connect_socketio after successful auth/subscription
    
    def _on_sio_disconnect(self) -> None:
        """Handle Socket.IO disconnection event."""
        if self._sio_connected:  # Only log if we were previously connected
            _LOGGER.warning("Socket.IO disconnected from Homey - falling back to polling (every 5 seconds)")
        self._sio_connected = False
        # Start reconnection task if not already running
        self._start_sio_reconnect_task()
    
    def _on_sio_connect_error(self, data: Any) -> None:
        """Handle Socket.IO connection error."""
        if self._sio_connected:  # Only log if we were previously connected
            _LOGGER.warning("Socket.IO connection error: %s - falling back to polling (every 5 seconds)", data)
        self._sio_connected = False
        # Start reconnection task if not already running
        self._start_sio_reconnect_task()
    
    def _on_sio_device_event(self, *args: Any) -> None:
        """Handle device update event from Socket.IO.
        
        Args:
            *args: Variable arguments - could be (data,) or (event_name, data)
        """
        # Handle different call signatures
        data = None
        if not args:
            return
            # If first arg is a string, it might be the event name
            if len(args) == 1:
                data = args[0]
            elif len(args) >= 2:
                # Event name, then data
                data = args[1] if isinstance(args[1], dict) else args[0]
            else:
                data = args[0]
        
        if not data:
            return
        
        # Data structure may vary - handle different formats
        # Expected formats:
        # 1. {"id": "device_id", ...device_data...} - direct device data
        # 2. {"device": {"id": "device_id", ...}} - nested device format
        # 3. {"deviceId": "device_id", ...} - alternative format
        # 4. Array of devices: [{"id": "device_id", ...}, ...]
        # 5. Event with URI and data: {"uri": "homey:manager:device:device_id", "data": {...}}
        device_id = None
        device_data = None
        
        if isinstance(data, dict):
            # Check for URI-based format first
            if "uri" in data and "data" in data:
                uri = data.get("uri", "")
                if "homey:manager:device" in uri:
                    # Extract device ID from URI if present
                    parts = uri.split(":")
                    if len(parts) > 3:
                        device_id = parts[-1]  # Last part is device ID
                    device_data = data.get("data", {})
                    if not device_id and "id" in device_data:
                        device_id = device_data.get("id")
            elif "id" in data:
                # Direct device data format
                device_id = data.get("id")
                device_data = data
            elif "device" in data:
                # Nested device format
                device = data.get("device", {})
                device_id = device.get("id")
                device_data = device
            elif "deviceId" in data:
                # Alternative format
                device_id = data.get("deviceId")
                device_data = data
        elif isinstance(data, list) and len(data) > 0:
            # Array of devices - process each one
            for item in data:
                if isinstance(item, dict) and "id" in item:
                    self._on_device_update(item.get("id"), item)
            return
        
        if device_id and device_data:
            # Call existing handler
            self._on_device_update(device_id, device_data)
        else:
            # Only log unexpected formats at debug level (not info)
            _LOGGER.debug("Socket.IO device event unexpected format: %s", data)
    
    def _start_sio_reconnect_task(self) -> None:
        """Start background task to periodically attempt Socket.IO reconnection."""
        # Only start if not already running and we have a session
        if (self._sio_reconnect_task is None or self._sio_reconnect_task.done()) and self.session:
            # Get the event loop - if we're in Home Assistant, use hass.loop
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    self._sio_reconnect_task = asyncio.create_task(self._sio_reconnect_loop())
            except Exception as err:
                _LOGGER.warning("Could not start Socket.IO reconnection task: %s", err)
    
    def _stop_sio_reconnect_task(self) -> None:
        """Stop the Socket.IO reconnection task."""
        if self._sio_reconnect_task and not self._sio_reconnect_task.done():
            self._sio_reconnect_task.cancel()
        self._sio_reconnect_task = None
    
    async def _sio_reconnect_loop(self) -> None:
        """Background loop to periodically attempt Socket.IO reconnection."""
        import time
        while True:
            try:
                # Wait before attempting reconnection
                await asyncio.sleep(self._sio_reconnect_interval)
                
                # Only attempt if we're not already connected
                if not self._sio_connected and self.session:
                    try:
                        success = await self._connect_socketio()
                        if success:
                            _LOGGER.info("Socket.IO reconnected - real-time updates restored (polling disabled)")
                            return  # Exit loop since we're connected
                    except Exception as err:
                        # Only log errors, not every retry attempt
                        _LOGGER.debug("Socket.IO reconnection error: %s", err)
                elif self._sio_connected:
                    # Already connected, exit loop
                    return
            except asyncio.CancelledError:
                # Task was cancelled, exit cleanly
                return
            except Exception as err:
                _LOGGER.warning("Error in Socket.IO reconnection loop: %s", err)
                # Continue loop even on error
    
    async def _disconnect_socketio(self) -> None:
        """Disconnect Socket.IO client."""
        # Stop reconnection task
        self._stop_sio_reconnect_task()
        
        if self.sio:
            try:
                if self.sio.connected:
                    await self.sio.disconnect()
            except Exception as err:
                _LOGGER.debug("Error disconnecting Socket.IO: %s", err)
            finally:
                self.sio = None
                self._sio_connected = False
                self.sio_namespace = None

    def add_device_listener(self, listener: Callable[[str, dict[str, Any]], None]) -> None:
        """Add a listener for device updates."""
        self._listeners.append(listener)

    def remove_device_listener(self, listener: Callable[[str, dict[str, Any]], None]) -> None:
        """Remove a device update listener."""
        if listener in self._listeners:
            self._listeners.remove(listener)

    async def disconnect(self) -> None:
        """Disconnect from Homey API."""
        # Stop reconnection task
        self._stop_sio_reconnect_task()
        
        await self._disconnect_socketio()

        if self.session:
            await self.session.close()
            self.session = None

