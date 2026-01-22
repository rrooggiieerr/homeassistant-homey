"""Support for Homey text entities."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CAPABILITY_TO_PLATFORM,
    CONF_EXPOSE_SETTABLE_TEXT,
    DEFAULT_EXPOSE_SETTABLE_TEXT,
    DOMAIN,
)
from .coordinator import HomeyDataUpdateCoordinator
from .device_info import build_entity_unique_id, get_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Homey text entities from a config entry."""
    coordinator: HomeyDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    zones = hass.data[DOMAIN][entry.entry_id].get("zones", {})
    multi_homey = hass.data[DOMAIN][entry.entry_id].get("multi_homey", False)
    homey_id = hass.data[DOMAIN][entry.entry_id].get("homey_id")

    entities: list[HomeyText] = []
    devices = coordinator.data if coordinator.data else await api.get_devices()

    # Filter devices if device_filter is configured
    from . import filter_devices
    devices = filter_devices(devices, entry.data.get("device_filter"))

    expose_settable_text = entry.options.get(
        CONF_EXPOSE_SETTABLE_TEXT,
        entry.data.get(CONF_EXPOSE_SETTABLE_TEXT, DEFAULT_EXPOSE_SETTABLE_TEXT),
    )
    if not expose_settable_text:
        _LOGGER.debug("Settable text entities disabled by options")
        async_add_entities(entities)
        return

    for device_id, device in devices.items():
        capabilities = device.get("capabilitiesObj", {})

        for capability_id, cap_data in capabilities.items():
            # Only settable string capabilities without options should be text entities
            if cap_data.get("type") != "string" or not cap_data.get("setable"):
                continue

            # Skip capabilities handled by other platforms
            mapped_platform = CAPABILITY_TO_PLATFORM.get(capability_id)
            if mapped_platform and mapped_platform != "text":
                continue

            # Skip capabilities that have explicit options (handled by select)
            if "values" in cap_data or "options" in cap_data:
                continue

            entities.append(
                HomeyText(
                    coordinator,
                    device_id,
                    device,
                    capability_id,
                    cap_data,
                    api,
                    zones,
                    homey_id,
                    multi_homey,
                )
            )

    async_add_entities(entities)


class HomeyText(CoordinatorEntity, TextEntity):
    """Representation of a Homey text entity."""

    def __init__(
        self,
        coordinator: HomeyDataUpdateCoordinator,
        device_id: str,
        device: dict[str, Any],
        capability_id: str,
        capability_data: dict[str, Any],
        api,
        zones: dict[str, dict[str, Any]] | None = None,
        homey_id: str | None = None,
        multi_homey: bool = False,
    ) -> None:
        """Initialize the text entity."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._device = device
        self._capability_id = capability_id
        self._capability_data = capability_data
        self._api = api
        self._homey_id = homey_id
        self._multi_homey = multi_homey

        device_name = device.get("name", "Unknown Device")
        capability_title = capability_data.get("title")
        capability_label = capability_title or capability_id.replace("_", " ").title()
        self._attr_name = f"{device_name} {capability_label}"
        self._attr_unique_id = build_entity_unique_id(
            homey_id, device_id, capability_id, multi_homey
        )

        self._attr_device_info = get_device_info(
            self._homey_id, device_id, device, zones, self._multi_homey
        )

    @property
    def native_value(self) -> str | None:
        """Return the current text value."""
        device_data = self.coordinator.data.get(self._device_id, self._device)
        capabilities = device_data.get("capabilitiesObj", {})
        value = capabilities.get(self._capability_id, {}).get("value")
        if value is None:
            return None
        return str(value)

    async def async_set_value(self, value: str) -> None:
        """Set the text value."""
        success = await self._api.set_capability_value(self._device_id, self._capability_id, value)
        if success:
            _LOGGER.debug(
                "Successfully set %s to %s for device %s",
                self._capability_id,
                value,
                self._device_id,
            )
            await self.coordinator.async_refresh_device(self._device_id)
        else:
            _LOGGER.error(
                "Failed to set %s to %s for device %s",
                self._capability_id,
                value,
                self._device_id,
            )
