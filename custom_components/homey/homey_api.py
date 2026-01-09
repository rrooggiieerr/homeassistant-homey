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
        self.devices: dict[str, dict[str, Any]] = {}
        self.flows: dict[str, dict[str, Any]] = {}
        self.zones: dict[str, dict[str, Any]] = {}  # Rooms/zones
        self.scenes: dict[str, dict[str, Any]] = {}  # Scenes
        self.moods: dict[str, dict[str, Any]] = {}  # Moods
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
                        if response.status == 200:
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
                        if response.status == 200:
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
            except Exception as err:
                _LOGGER.info(
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
        
        # Handle numeric capabilities - reject non-numeric strings
        numeric_capabilities = [
            "dim", "light_hue", "light_saturation", "light_temperature",
            "target_temperature", "measure_temperature", "fan_speed",
            "volume_set", "windowcoverings_state",
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
            API_MOODS,  # /api/manager/mood/mood
            f"{API_MOODS}/",  # With trailing slash
            f"{API_BASE_MANAGER}/moods/mood",  # Plural variation
            f"{API_BASE_MANAGER}/moods/mood/",  # With trailing slash
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
            f"{API_MOODS}/{mood_id}/set",  # /api/manager/mood/mood/{id}/set (matches permission name)
            f"{API_MOODS}/{mood_id}/set/",  # With trailing slash
            f"{API_MOODS}/{mood_id}/trigger",  # /api/manager/mood/mood/{id}/trigger
            f"{API_MOODS}/{mood_id}/trigger/",  # With trailing slash
            f"{API_BASE_MANAGER}/moods/mood/{mood_id}/set",  # Plural variation with /set
            f"{API_BASE_MANAGER}/moods/mood/{mood_id}/trigger",  # Plural variation
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

