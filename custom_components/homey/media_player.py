"""Support for Homey media players."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
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
    """Set up Homey media players from a config entry."""
    coordinator: HomeyDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    zones = hass.data[DOMAIN][entry.entry_id].get("zones", {})

    entities = []
    # Use coordinator data if available (more up-to-date), otherwise fetch fresh
    devices = coordinator.data if coordinator.data else await api.get_devices()
    
    # Filter devices if device_filter is configured
    from . import filter_devices
    devices = filter_devices(devices, entry.data.get("device_filter"))

    for device_id, device in devices.items():
        capabilities = device.get("capabilitiesObj", {})
        if any(
            cap in capabilities
            for cap in ["volume_set", "speaker_playing", "speaker_next", "speaker_prev"]
        ):
            entities.append(HomeyMediaPlayer(coordinator, device_id, device, api, zones))

    async_add_entities(entities)


class HomeyMediaPlayer(CoordinatorEntity, MediaPlayerEntity):
    """Representation of a Homey media player."""

    def __init__(
        self,
        coordinator: HomeyDataUpdateCoordinator,
        device_id: str,
        device: dict[str, Any],
        api,
        zones: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        """Initialize the media player."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._device = device
        self._api = api
        self._attr_name = device.get("name", "Unknown Media Player")
        self._attr_unique_id = f"homey_{device_id}_media_player"

        capabilities = device.get("capabilitiesObj", {})
        supported_features = 0

        if "volume_set" in capabilities:
            supported_features |= MediaPlayerEntityFeature.VOLUME_SET
        if "volume_mute" in capabilities:
            supported_features |= MediaPlayerEntityFeature.VOLUME_MUTE
        if "speaker_playing" in capabilities:
            supported_features |= MediaPlayerEntityFeature.PLAY | MediaPlayerEntityFeature.PAUSE
        if "speaker_next" in capabilities:
            supported_features |= MediaPlayerEntityFeature.NEXT_TRACK
        if "speaker_prev" in capabilities:
            supported_features |= MediaPlayerEntityFeature.PREVIOUS_TRACK

        self._attr_supported_features = supported_features

        self._attr_device_info = get_device_info(device_id, device, zones)

    @property
    def state(self) -> MediaPlayerState:
        """Return the state of the media player."""
        device_data = self.coordinator.data.get(self._device_id, self._device)
        capabilities = device_data.get("capabilitiesObj", {})
        playing = capabilities.get("speaker_playing", {}).get("value", False)
        return MediaPlayerState.PLAYING if playing else MediaPlayerState.IDLE

    @property
    def volume_level(self) -> float | None:
        """Return the volume level."""
        device_data = self.coordinator.data.get(self._device_id, self._device)
        capabilities = device_data.get("capabilitiesObj", {})
        volume = capabilities.get("volume_set", {}).get("value")
        return float(volume) if volume is not None else None

    @property
    def is_volume_muted(self) -> bool:
        """Return true if volume is muted."""
        device_data = self.coordinator.data.get(self._device_id, self._device)
        capabilities = device_data.get("capabilitiesObj", {})
        muted = capabilities.get("volume_mute", {}).get("value", False)
        return bool(muted)

    async def async_media_play(self) -> None:
        """Send play command."""
        if "speaker_playing" in self._device.get("capabilitiesObj", {}):
            await self._api.set_capability_value(self._device_id, "speaker_playing", True)
            # Immediately refresh this device's state for instant UI feedback
            await self.coordinator.async_refresh_device(self._device_id)

    async def async_media_pause(self) -> None:
        """Send pause command."""
        if "speaker_playing" in self._device.get("capabilitiesObj", {}):
            await self._api.set_capability_value(self._device_id, "speaker_playing", False)
            # Immediately refresh this device's state for instant UI feedback
            await self.coordinator.async_refresh_device(self._device_id)

    async def async_media_next_track(self) -> None:
        """Send next track command."""
        if "speaker_next" in self._device.get("capabilitiesObj", {}):
            await self._api.set_capability_value(self._device_id, "speaker_next", True)
            # Immediately refresh this device's state for instant UI feedback
            await self.coordinator.async_refresh_device(self._device_id)

    async def async_media_previous_track(self) -> None:
        """Send previous track command."""
        if "speaker_prev" in self._device.get("capabilitiesObj", {}):
            await self._api.set_capability_value(self._device_id, "speaker_prev", True)
            # Immediately refresh this device's state for instant UI feedback
            await self.coordinator.async_refresh_device(self._device_id)

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level.
        
        Home Assistant uses normalized volume (0.0-1.0).
        Homey API also uses normalized volume (0-1), so no conversion needed.
        """
        if "volume_set" in self._device.get("capabilitiesObj", {}):
            # Both HA and Homey use normalized 0-1 for volume, so pass through directly
            await self._api.set_capability_value(self._device_id, "volume_set", volume)
            # Immediately refresh this device's state for instant UI feedback
            await self.coordinator.async_refresh_device(self._device_id)

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute or unmute volume."""
        if "volume_mute" in self._device.get("capabilitiesObj", {}):
            await self._api.set_capability_value(self._device_id, "volume_mute", mute)
            # Immediately refresh this device's state for instant UI feedback
            await self.coordinator.async_refresh_device(self._device_id)

