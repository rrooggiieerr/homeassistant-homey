"""Support for Homey flows as buttons."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HomeyDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Homey flow buttons from a config entry."""
    coordinator: HomeyDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    api = hass.data[DOMAIN][entry.entry_id]["api"]

    entities = []
    flows = await api.get_flows()
    
    for flow_id, flow in flows.items():
        flow_enabled = flow.get("enabled", False)
        
        # Only include enabled flows that can be triggered
        if flow_enabled:
            entities.append(HomeyFlowButton(coordinator, flow_id, flow, api))

    if entities:
        _LOGGER.info("Created %d Homey flow button entities", len(entities))
    async_add_entities(entities)


class HomeyFlowButton(CoordinatorEntity, ButtonEntity):
    """Representation of a Homey flow as a Home Assistant button."""

    def __init__(
        self,
        coordinator: HomeyDataUpdateCoordinator,
        flow_id: str,
        flow: dict[str, Any],
        api,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._flow_id = flow_id
        self._flow = flow
        self._api = api
        self._attr_name = flow.get("name", "Unknown Flow")
        self._attr_unique_id = f"homey_{flow_id}_flow"
        self._attr_icon = "mdi:play-circle-outline"

        self._attr_device_info = {
            "identifiers": {(DOMAIN, "flows")},
            "name": "Homey Flows",
            "manufacturer": "Athom",
            "model": "Homey",
        }

    async def async_press(self) -> None:
        """Handle the button press - trigger the Homey flow."""
        success = await self._api.trigger_flow(self._flow_id)
        if not success:
            _LOGGER.error("Failed to trigger Homey flow: %s", self._attr_name)

