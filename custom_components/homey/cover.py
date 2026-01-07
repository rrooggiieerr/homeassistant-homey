"""Support for Homey covers."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.cover import CoverEntity, CoverEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HomeyDataUpdateCoordinator
from .device_info import get_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Homey covers from a config entry."""
    coordinator: HomeyDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    zones = hass.data[DOMAIN][entry.entry_id].get("zones", {})

    entities = []
    # Use coordinator data if available (more up-to-date), otherwise fetch fresh
    devices = coordinator.data if coordinator.data else await api.get_devices()

    for device_id, device in devices.items():
        capabilities = device.get("capabilitiesObj", {})
        if "windowcoverings_state" in capabilities:
            entities.append(HomeyCover(coordinator, device_id, device, api, zones))

    async_add_entities(entities)


class HomeyCover(CoordinatorEntity, CoverEntity):
    """Representation of a Homey cover."""

    def __init__(
        self,
        coordinator: HomeyDataUpdateCoordinator,
        device_id: str,
        device: dict[str, Any],
        api,
        zones: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        """Initialize the cover."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._device = device
        self._api = api
        self._attr_name = device.get("name", "Unknown Cover")
        self._attr_unique_id = f"homey_{device_id}_cover"

        capabilities = device.get("capabilitiesObj", {})
        supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP

        if "windowcoverings_tilt_up" in capabilities and "windowcoverings_tilt_down" in capabilities:
            supported_features |= CoverEntityFeature.SET_TILT_POSITION | CoverEntityFeature.OPEN_TILT | CoverEntityFeature.CLOSE_TILT

        self._attr_supported_features = supported_features

        self._attr_device_info = get_device_info(device_id, device, zones)

    @property
    def current_cover_position(self) -> int | None:
        """Return current position of cover."""
        device_data = self.coordinator.data.get(self._device_id, self._device)
        capabilities = device_data.get("capabilitiesObj", {})
        state = capabilities.get("windowcoverings_state", {}).get("value")
        if state is not None:
            # Convert state (0-1) to percentage (0-100)
            return int(state * 100)
        return None

    @property
    def is_closed(self) -> bool | None:
        """Return if the cover is closed."""
        position = self.current_cover_position
        if position is not None:
            return position == 0
        return None

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        await self._api.set_capability_value(self._device_id, "windowcoverings_state", 1.0)
        await self.coordinator.async_request_refresh()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        await self._api.set_capability_value(self._device_id, "windowcoverings_state", 0.0)
        await self.coordinator.async_request_refresh()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        # Get current position and set it again to stop
        position = self.current_cover_position
        if position is not None:
            await self._api.set_capability_value(
                self._device_id, "windowcoverings_state", position / 100.0
            )
        await self.coordinator.async_request_refresh()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Move the cover to a specific position."""
        position = kwargs.get("position", 0)
        await self._api.set_capability_value(
            self._device_id, "windowcoverings_state", position / 100.0
        )
        await self.coordinator.async_request_refresh()

