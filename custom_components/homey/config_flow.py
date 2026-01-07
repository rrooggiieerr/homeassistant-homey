"""Config flow for Homey integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_TOKEN
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default="http://homey.local"): str,
        vol.Required(CONF_TOKEN): str,
    }
)


class HomeyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Homey."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate the connection
            try:
                host = user_input[CONF_HOST].strip().rstrip("/")
                token = user_input[CONF_TOKEN].strip()

                # Ensure host has protocol
                if not host.startswith(("http://", "https://")):
                    host = f"http://{host}"

                # Test connection - try multiple possible endpoints
                # Create a temporary session for testing (Homey local API doesn't use SSL)
                timeout = aiohttp.ClientTimeout(total=10)
                connector = aiohttp.TCPConnector(ssl=False)
                
                # Try different possible endpoints based on Homey API documentation
                endpoints_to_try = [
                    "/api/manager/system/info",  # Manager API structure
                    "/api/manager/system/info/",  # With trailing slash
                    "/api/manager/system",
                    "/api/manager/system/",
                    "/api/v1/manager/system/info",
                    "/api/v1/manager/system/info/",
                    "/api/v1/manager/system",
                    "/api/v1/manager/system/",
                    "/api/v1/system/info",
                    "/api/v1/system/info/",
                    "/api/v1/system",
                    "/api/v1/system/",
                ]
                
                data = None
                last_error = None
                
                async with aiohttp.ClientSession(
                    connector=connector,
                    timeout=timeout,
                    headers={"Authorization": f"Bearer {token}"},
                ) as session:
                    for endpoint in endpoints_to_try:
                        url = f"{host}{endpoint}"
                        _LOGGER.debug("Trying endpoint: %s", url)
                        
                        try:
                            async with session.get(url) as response:
                                _LOGGER.debug("Response status: %s for %s", response.status, url)
                                
                                if response.status == 200:
                                    try:
                                        data = await response.json()
                                        _LOGGER.info("Successfully connected to Homey using endpoint: %s", endpoint)
                                        break
                                    except Exception as json_err:
                                        # If JSON parsing fails, read text for debugging
                                        try:
                                            response_text = await response.read()
                                            _LOGGER.warning("Failed to parse JSON from %s: %s, body: %s", url, json_err, response_text[:200].decode('utf-8', errors='ignore'))
                                        except:
                                            _LOGGER.warning("Failed to parse JSON from %s: %s", url, json_err)
                                        # Continue to next endpoint
                                elif response.status == 401:
                                    errors["base"] = "invalid_auth"
                                    _LOGGER.error("Authentication failed with endpoint %s", endpoint)
                                    return self.async_show_form(
                                        step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
                                    )
                                elif response.status == 404:
                                    _LOGGER.debug("Endpoint %s not found, trying next...", endpoint)
                                    last_error = f"Endpoint {endpoint} not found"
                                    continue
                                else:
                                    _LOGGER.debug("Unexpected status %s for %s: %s", response.status, url, response_text[:200])
                                    last_error = f"Status {response.status} for {endpoint}"
                                    continue
                        except Exception as err:
                            _LOGGER.debug("Error trying endpoint %s: %s", endpoint, err)
                            last_error = str(err)
                            continue
                    
                    # If we got data from any endpoint, proceed
                    if data:
                        # Use Homey name as unique ID
                        unique_id = data.get("id") or data.get("homeyId") or host
                        name = data.get("name") or data.get("homeyName") or "Homey"
                        
                        # Determine which endpoint structure worked
                        working_endpoint = "manager" if "/api/manager" in endpoint else "v1"

                        await self.async_set_unique_id(unique_id)
                        self._abort_if_unique_id_configured()

                        return self.async_create_entry(
                            title=name,
                            data={
                                CONF_HOST: host,
                                CONF_TOKEN: token,
                                "working_endpoint": working_endpoint,  # Store which worked
                            },
                        )
                    else:
                        # Try devices endpoint as final fallback - if this works, API is accessible
                        _LOGGER.debug("System endpoints failed, trying devices endpoint as fallback...")
                        device_endpoints = [
                            "/api/manager/devices/device/",  # Manager API structure with trailing slash
                            "/api/manager/devices/device",
                            "/api/v1/device/",
                            "/api/v1/device",
                        ]
                        for device_endpoint in device_endpoints:
                            try:
                                url = f"{host}{device_endpoint}"
                                _LOGGER.debug("Trying devices endpoint: %s", url)
                                async with session.get(url) as response:
                                    response_text = await response.text()
                                    _LOGGER.debug("Devices endpoint %s returned status %s, body: %s", device_endpoint, response.status, response_text[:500])
                                    
                                    if response.status == 200:
                                        # Devices endpoint works, so API is accessible
                                        _LOGGER.info("Devices endpoint accessible at %s, proceeding with setup", device_endpoint)
                                        await self.async_set_unique_id(host)
                                        self._abort_if_unique_id_configured()
                                        
                                        # Determine which endpoint structure worked
                                        working_endpoint = "manager" if "/api/manager" in device_endpoint else "v1"
                                        
                                        return self.async_create_entry(
                                            title="Homey",
                                            data={
                                                CONF_HOST: host,
                                                CONF_TOKEN: token,
                                                "working_endpoint": working_endpoint,  # Store which worked
                                            },
                                        )
                                    elif response.status == 401:
                                        errors["base"] = "invalid_auth"
                                        _LOGGER.error("Authentication failed with devices endpoint %s", device_endpoint)
                                        return self.async_show_form(
                                            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
                                        )
                                    elif response.status == 404:
                                        _LOGGER.debug("Devices endpoint %s not found, trying next...", device_endpoint)
                                        continue
                                    else:
                                        _LOGGER.debug("Unexpected status %s for %s: %s", response.status, device_endpoint, response_text[:200])
                                        continue
                            except Exception as dev_err:
                                _LOGGER.debug("Error trying devices endpoint %s: %s", device_endpoint, dev_err)
                                continue
                        
                        # If we get here, all endpoints failed
                        errors["base"] = "cannot_connect"
                        _LOGGER.error("Could not connect to Homey API. Tried system endpoints: %s and device endpoints: %s. Last error: %s", endpoints_to_try, device_endpoints, last_error)
            except aiohttp.ClientConnectorError as err:
                errors["base"] = "cannot_connect"
                _LOGGER.error("Connection error: %s", err)
            except aiohttp.ServerTimeoutError:
                errors["base"] = "cannot_connect"
                _LOGGER.error("Connection timeout")
            except aiohttp.ClientError as err:
                errors["base"] = "cannot_connect"
                _LOGGER.error("Client error: %s", err)
            except Exception as err:
                _LOGGER.exception("Unexpected exception: %s", err)
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

