# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

---

## [1.1.3] - 2026-01-11

### 🎉 Major Device Classification and Capability Support Update

**This version significantly improves device classification accuracy, adds comprehensive support for all Homey device classes and capabilities, fixes maintenance button filtering, adds multi-channel switch support, and includes enhanced troubleshooting documentation.**

### Added

#### Comprehensive Device Class Support
- **All Homey Device Classes**: Added support for all Homey device classes including `light`, `socket`, `sensor`, `thermostat`, `speaker`, `tv`, `remote`, `windowcoverings`, `cover`, `garagedoor`, `curtain`, `blind`, `shutter`, `awning`, `lock`, `fan`, `camera`, `doorbell`, and `other`
- **Device Class Priority**: Homey's `device_class` field is now used as the primary classification method for more reliable device type detection
- **Garage Door Support**: Added support for `garagedoor_closed` capability (garage doors are now detected as covers)
- **Window Coverings Variants**: Added support for `windowcoverings_set` capability (alternative to `windowcoverings_state`) for devices that use different capability names

#### Multi-Channel Device Support
- **Multi-Channel Switches**: Added support for multi-channel switches with sub-capabilities (e.g., `onoff.output1`, `onoff.output2`)
- **Separate Switch Entities**: Multi-channel devices now create separate switch entities for each output channel
- **Entity Naming**: Multi-channel switches automatically get descriptive names (e.g., "Device Name Output 1", "Device Name Output 2")
- **Examples**: Supports devices like Shelly Plus 2 PM, Fibaro Double Switch, and other multi-channel relay devices

#### Enhanced Capability Support
- **Meter Capabilities**: Added support for `meter_power`, `meter_water`, and `meter_gas` capabilities with proper state classes (`TOTAL_INCREASING`)
- **Sub-Capability Support**: Full support for sub-capabilities (capabilities with dots, e.g., `measure_temperature.inside`, `alarm_motion.outside`)
- **Additional Binary Sensors**: Added support for `alarm_gas`, `alarm_fire`, `alarm_panic`, `alarm_burglar`, `alarm_generic`, `alarm_maintenance`, `button`, and `vibration` capabilities
- **Alternative Capability Names**: Added support for alternative capability names (`measure_wind_speed`, `measure_wind_direction`, `measure_light`, `measure_illuminance`)

#### Device-Specific Detection
- **Philips Hue Devices**: Enhanced detection to ensure Philips Hue devices (including White & Ambiance bulbs) are correctly identified as lights with full dimming and color temperature support
- **Sunricher Devices**: Added device-specific detection for Sunricher dimming devices to ensure they're classified as lights
- **Fibaro Devices**: Enhanced detection for Fibaro switches, outlets, and roller shutters to ensure correct classification
- **Shelly Devices**: Added device-specific detection for Shelly devices to ensure switches are correctly identified

#### Light Enhancements
- **Normalized Temperature Handling**: Improved handling of normalized `light_temperature` values (0-1) with automatic conversion to Kelvin range (2000-6500K)
- **Better Capability Detection**: Enhanced light entity creation to properly detect and expose dimming and color temperature capabilities

#### Maintenance Button Filtering
- **Maintenance Action Detection**: Added filtering for maintenance buttons using Homey's `maintenanceAction` property
- **Automatic Cleanup**: Added automatic cleanup of existing maintenance button entities (migrate, identify, reset buttons) on integration reload
- **Comprehensive Filtering**: Maintenance buttons are now filtered in button, sensor, and binary sensor platforms

#### Documentation
- **Troubleshooting Guide**: Added comprehensive troubleshooting guide with step-by-step instructions for gathering device information using Homey Developer Tools
- **Device Information Guide**: Added detailed guide explaining how to use Homey Web API Playground to get device capabilities and class information for issue reporting

### Fixed

#### Device Classification Fixes
- **Philips Hue E27 White & Ambiance**: Fixed issue where bulbs were recognized as lights but only supported on/off - now properly supports dimming and color temperature
- **Sunricher Dim Lighting**: Fixed issue where dimming devices were recognized as lights but only supported on/off - now properly supports dimming
- **Fibaro Walli Roller Shutter (FGWREU-111)**: Fixed issue where roller shutters were recognized as sensors - now correctly detected as covers
- **Fibaro Walli Switch (FGWDSEU-221)**: Fixed issue where switches were recognized as sensors - now correctly detected as switches
- **Fibaro Single/Double Switch (FGS-213/223)**: Fixed issue where switches were recognized as sensors - now correctly detected as switches
- **Fibaro Wall Plug (FGWPE-102)**: Fixed issue where wall plugs were recognized as sensors - now correctly detected as switches
- **Fibaro Walli Outlet (FGWOE-011)**: Fixed issue where outlets were recognized as sensors - now correctly detected as switches
- **Shelly Plus Plug S**: Fixed issue where Shelly devices were recognized as sensors - now correctly detected as switches
- **Shelly 1 Mini Gen 3**: Fixed issue where Shelly devices were recognized as sensors - now correctly detected as switches
- **Shelly Plus 2 PM**: Fixed issue where Shelly devices were recognized as sensors - now correctly detected as switches
- **Window Coverings with `windowcoverings_set`**: Fixed issue where devices using `windowcoverings_set` instead of `windowcoverings_state` were not detected as covers
- **Multi-Channel Switches**: Fixed issue where devices with `onoff.output1`, `onoff.output2` sub-capabilities were not creating switch entities - now creates separate switch entities for each channel

#### Priority Order Improvements
- **Control Capabilities First**: Fixed device classification priority to prioritize control capabilities (cover, light, switch) over sensor capabilities (measure_*, meter_*)
- **Switch vs Sensor**: Devices with `onoff` capability are now correctly classified as switches even when they also have metering capabilities

#### Maintenance Button Issues
- **Maintenance Buttons Appearing**: Fixed issue where maintenance buttons (migrate, identify, reset) were appearing as entities in Home Assistant
- **Entity Cleanup**: Added automatic removal of existing maintenance button entities on integration reload

#### Configuration Flow Bugfix
- **Missing Logger Import**: Fixed `NameError: name '_LOGGER' is not defined` error in config flow by adding missing logger import to `device_info.py` module

### Changed

#### Device Type Detection Logic
- **Priority Order**: Updated device type detection priority to: Cover > Light > Climate > Fan > Lock > Media Player > Switch > Sensor
- **Device Class Integration**: Homey's `device_class` field is now checked first for device classification, with capability-based detection as fallback
- **Multi-Entity Support**: Devices with both control and sensor capabilities now correctly get multiple entities (e.g., switch + power sensor)

#### Light Platform
- **Temperature Conversion**: Improved `light_temperature` handling to detect normalized values (0-1) and convert to Kelvin range automatically
- **Capability Logging**: Enhanced logging for light entity creation to help diagnose capability detection issues

#### Switch Platform
- **Classification Logic**: Updated switch platform to use centralized `get_device_type` function for consistent device classification
- **Multi-Channel Support**: Added support for multi-channel switches with sub-capabilities (e.g., `onoff.output1`, `onoff.output2`) - creates separate switch entities for each channel
- **Better Logging**: Improved logging to show why devices are or aren't created as switch entities

---

## [1.1.2] - 2026-01-10

### Fixed
- **Config Flow Validation Error** - Fixed "extra keys not allowed" error in config flow by importing `CONF_TOKEN` from local `const.py` instead of `homeassistant.const` (which doesn't include this constant). This resolves validation errors when adding the integration via HACS or manual installation.

---

## [1.1.1] - 2026-01-11

### Added
- **Migration Guide** - Added comprehensive migration instructions for users switching from manual installation to HACS
- **Installation Conflict Detection** - Integration now detects and warns about conflicting installation methods (manual + HACS)

### Fixed
- Improved detection of installation method conflicts to prevent update issues

---

## [1.1.0] - 2026-01-11

### 🎉 Major Feature Release: Scenes, Moods, and Enhanced Platforms

**This version adds comprehensive support for Homey Scenes and Moods, physical device buttons, Number and Select platforms, flow management services, and extensive sensor/binary sensor capabilities. It also includes a robust permission checking system and improved error handling.**

### Added

#### New Platforms
- **Scene Platform** - Homey scenes now appear as Scene entities in Home Assistant
- **Moods Support** - Homey moods are exposed as Scene entities with distinct icons
- **Number Platform** - Ready for numeric control capabilities (placeholder for future capabilities)
- **Select Platform** - Ready for mode/option selection capabilities (placeholder for future capabilities)
- **Physical Device Buttons** - Physical device buttons (`button`, `button.1`, etc.) now appear as Button entities

#### Enhanced Sensor Capabilities
- **Additional Sensor Types**: Noise (dB), Rain (mm), Wind Strength/Angle (m/s, °), Ultraviolet (UV index), PM2.5/PM10 (µg/m³), VOC (µg/m³), AQI, Frequency (Hz), Gas (ppm), Soil Moisture/Temperature (%, °C), Energy (kWh)
- **Proper State Classes**: Energy sensors now use `TOTAL_INCREASING` state class for proper energy tracking

#### Enhanced Binary Sensor Capabilities
- **Additional Alarm Types**: Gas, Fire, Panic, Burglar, Generic, Maintenance alarms
- **Physical Buttons**: Button capabilities detected as binary sensors
- **Vibration Detection**: Vibration sensor support

#### Climate Enhancements
- **Humidity Support**: Added current and target humidity properties with proper unit conversion
- **HVAC Mode Detection**: Dynamic HVAC mode detection based on available thermostat capabilities (`thermostat_mode_off`, `thermostat_mode_heat`, `thermostat_mode_cool`, `thermostat_mode_auto`)
- **Mode Support**: Full support for OFF, HEAT, COOL, AUTO, and HEAT_COOL modes

#### Media Player Enhancements
- **Rich Metadata**: Added support for artist, album, track name, duration, position
- **Playback Controls**: Added shuffle and repeat state support
- **Position Tracking**: Media position with timestamp tracking

#### Flow Management
- **Flow Enable/Disable Services**: Added `homey.enable_flow` and `homey.disable_flow` services
- **Service Flexibility**: Both services support `flow_id` or `flow_name` parameters

#### Permission System
- **Comprehensive Permission Checking**: Added permission validation system that checks API permissions for all features
- **Graceful Degradation**: Integration continues to work even when permissions are missing - features are simply disabled
- **Clear Warnings**: Detailed log messages inform users about missing permissions and their impact
- **Permission Documentation**: Updated README with complete permission requirements and impact table

#### HACS Integration
- **HACS Support**: Added `hacs.json` configuration file for HACS integration
- **HACS Installation Guide**: Updated README with comprehensive HACS installation instructions
- **Table of Contents**: Added navigation table of contents to README for easier navigation

### Fixed
- **Humidity Conversions** - Fixed handling of normalized (0-1) vs percentage (0-100) humidity values in sensors and climate controls
- **Climate Initialization Bug** - Fixed `capabilities` variable used before definition in climate platform
- **Migration Buttons** - Filtered out internal Homey migration capabilities (`button.migrate_v3`, `button.reset_meter`, `button.identify`) from appearing as button entities
- **Empty Feature Handling** - Integration now gracefully handles cases where users have permissions but no features configured (e.g., moods permission but no moods)
- **Entity Registry Method** - Fixed `AttributeError` when removing devices by replacing non-existent `async_entries_for_device` with proper entity registry iteration
- **Authentication Error Detection** - Improved error handling to correctly identify authentication failures (401) vs connection issues, providing clearer error messages
- **Light Color Sync** - Fixed incorrect color values on startup by refreshing device state when entities are first added to Home Assistant
- **Button Platform Indentation** - Fixed syntax error in button platform that prevented integration from loading
- **Thermostat Temperature Control** - Fixed thermostat temperature setting to handle all parameter formats (`temperature`, `target_temperature_high`, `target_temperature_low`) and added default min/max temperatures for proper UI controls
- **Flows Device Removal** - Fixed virtual "flows" device being incorrectly removed by device cleanup logic when device filtering is enabled
- **Flow Logging** - Improved flow discovery logging to show enabled vs disabled flows and help diagnose flow visibility issues

### Changed
- **Permission Names** - Updated all permission references to use correct Homey API v3 permission names (`homey.device.readonly`, `homey.flow.start`, etc.)
- **Error Handling** - Improved distinction between permission errors (401/403) and missing features (empty results)
- **Logging** - More informative log messages that distinguish between permission issues and normal empty results
- **Scene/Mood Detection** - Scenes and moods are now properly detected and exposed, with moods using distinct icons

### Technical Details

#### Permission Mapping
- `homey.device.readonly` - Required for device discovery and reading states
- `homey.device.control` - Required for device control
- `homey.zone.readonly` - Recommended for room/area organization
- `homey.flow.readonly` - Recommended for flow listing
- `homey.flow.start` - Recommended for flow triggering and management
- `homey.mood.readonly` - Recommended for mood listing
- `homey.mood.set` - Recommended for mood activation
- Scenes use device permissions (no separate scene permissions in Homey API v3)

#### Humidity Conversion Logic
- Automatically detects if humidity values are normalized (0-1) or percentage (0-100) based on capability `max` value
- Converts normalized values to percentage when reading
- Converts percentage to normalized values when writing
- Applies to both `measure_humidity` sensors and `target_humidity` climate controls

#### Feature Availability Handling
- Empty results (200 OK with empty data) are treated as normal - user just doesn't have that feature configured
- Permission errors (401/403) trigger warnings and disable features
- 404 errors are treated as feature not available on this Homey version
- Integration never breaks due to missing features or permissions

**Impact**: This release significantly expands the integration's capabilities, adding support for scenes, moods, and many new sensor types. The permission system ensures users understand what features require which permissions, and the integration gracefully handles all edge cases.

---

## [1.0.2] - 2026-01-09

### 🚀 Major Fix: Flow Support for Homey Pro 2026

**This version fixes critical issues with flow discovery and triggering, and adds support for Advanced Flows.**

### Fixed
- **Fixed flow endpoint bug** - Changed from incorrect `/api/manager/flows/flow` (plural) to correct `/api/manager/flow/flow` (singular) per Homey API v3 documentation
- **Fixed flow discovery** - Flows now properly appear as button entities in Home Assistant
- **Fixed flow triggering** - Both Standard and Advanced Flows can now be triggered successfully

### Added
- **Advanced Flows support** - Added support for Homey Advanced Flows using `/api/manager/flow/advancedflow` endpoint
- **Improved flow discovery** - Now fetches both Standard and Advanced Flows separately and combines them
- **Case-insensitive flow name matching** - Flow names can now be matched regardless of case when using service calls
- **Update guide** - Added comprehensive update instructions to README

### Changed
- **Reduced verbose logging** - Removed excessive debug logs for cleaner production logs
- **Improved flow error messages** - Better error messages when flows are not found, including list of available flows
- **Enhanced flow triggering** - Automatically uses correct endpoint (standard vs advanced) based on flow type

### Technical Details
- Standard Flows: `/api/manager/flow/flow` endpoint
- Advanced Flows: `/api/manager/flow/advancedflow` endpoint
- Flow type detection: Automatically marks flows as "standard" or "advanced" for correct endpoint usage
- Flow name matching: Now supports both exact match and case-insensitive matching

**Impact**: This fix resolves issues where flows were not appearing or could not be triggered, especially on Homey Pro 2026. All users with flows should update to this version.

---

## [1.0.1] - 2026-01-08

### 🎨 Major Fix: Light Color Control

**This version includes a critical fix for light color control that was preventing colors from changing correctly.**

### ⚠️ IMPORTANT: API Key Update Required

**Before upgrading to version 1.0.1, you MUST create a new API key in Homey with the following permissions:**

1. Go to **Homey Web App** → **Settings** → **API Keys**
2. Create a **new API key** (or update your existing one)
3. Ensure these permissions are enabled:
   - `device:read` - Required to read device states
   - `device:write` - Required to control devices
   - `zone:read` - **Required for room/area organization** (recommended)
   - `flow:read` - **Required for Flow support** (needed to list Flows and create button entities)
   - `flow:write` - **Required for Flow support** (needed to trigger Flows)
4. Update your Home Assistant integration configuration with the new API key

**Why?** This version includes improvements that require proper API permissions. Without `zone:read`, devices won't be organized by rooms. Without `device:write`, you won't be able to control devices. Without `flow:read` and `flow:write`, Flow support (button entities and service calls) will be disabled.

### Added
- Manual device deletion support - users can now delete devices from the Devices page
- Device selection during initial setup - choose which devices to import
- Post-setup device management - add/remove devices via integration options
- Device filtering - only selected devices are imported and managed

### Changed
- Removed emojis from device selection UI for better compatibility
- Improved error handling for 401 authentication errors - now tries all endpoints before failing
- Enhanced device value conversion to prevent "invalid literal for int()" errors
- Improved room/zone detection - gracefully handles missing zone permissions
- Updated config flow to handle missing zones/rooms gracefully
- Reduced polling interval from 30 seconds to 10 seconds for faster background updates
- Implemented immediate device state refresh after control commands for instant UI feedback (1-2 seconds)
- Improved logging - reduced excessive debug logging for production use
- Enhanced color control error handling - better error messages and logging for troubleshooting color issues

### Fixed
- **Fixed light color control** - Colors now change correctly! The issue was a value format mismatch between Home Assistant (hue 0-360°, saturation 0-100%) and Homey API (normalized 0-1). The integration now automatically converts between these formats.
- Fixed light color mode validation - prevents "invalid supported color modes" warnings by correctly handling color mode combinations
- Improved color setting reliability - ensures light is turned on before setting color, sets saturation before hue, and enforces minimum brightness for color visibility
- Fixed schema serialization errors in config flow (`cv.multi_select` instead of boolean checkboxes)
- Fixed authentication flow - no longer fails immediately on first 401 error
- Fixed device registry updates - devices now properly sync names and areas
- Fixed device deletion - devices removed from Homey are now properly cleaned up
- Fixed deprecated constants (`ATTR_COLOR_TEMP_KELVIN`, removed `UnitOfVoltage`)
- Fixed coordinator update interval - now uses `timedelta` instead of `int`
- Fixed binary sensor device class - removed unsupported `CO2` device class
- Fixed thermostat temperature sync - now properly syncs back to Homey
- Fixed motion/contact sensor state updates - improved value parsing
- Fixed cover position handling - better handling of missing capability values
- Fixed flow triggering - tries multiple endpoints and HTTP methods
- Fixed missing `Any` import in `__init__.py`
- Fixed OptionsFlow initialization error (`AttributeError: property 'config_entry' has no setter`)
- Fixed missing `CONF_DEVICE_FILTER` import in coordinator causing `NameError`
- Fixed status update delays - status now updates immediately after control commands instead of waiting for polling cycle

### Technical Details
- Added automatic value format conversion for `light_hue` and `light_saturation` capabilities
- Home Assistant format → Homey API format: hue (0-360° → 0-1), saturation (0-100% → 0-1)
- Homey API format → Home Assistant format: hue (0-1 → 0-360°), saturation (0-1 → 0-100%)
- Updated API reference documentation to reflect Homey's normalized value format (0-1) for many capabilities

**Impact**: This fix resolves a critical issue where light colors would not change or would change incorrectly. All users with color-capable lights should update to this version.

### Known Issues
- **Room/Zone Detection**: Room grouping may not work if API key doesn't have `zone:read` permission. Devices will still be imported but without room grouping.
- **Config Flow Window Size**: Home Assistant config flow dialogs have a fixed size and cannot be customized. This is a Home Assistant limitation.
- **Socket.IO Real-time Updates**: Currently disabled due to authentication complexity. Using polling instead (10-second intervals) with immediate refresh after control commands for near-instant feedback.
- **Entity Name Updates**: Entity names (`_attr_name`) don't update automatically when device names change in Homey. Device names in UI will update, but entity names require integration reload.
- **External Changes**: Changes made outside Home Assistant (via Homey app or physical switches) may take up to 10 seconds to appear in Home Assistant due to polling interval.

---

## [1.0.0] - 2026-01-08

### Added
- Initial release
- Support for multiple device types: lights, switches, sensors, binary sensors, covers, climate, fans, locks, media players
- Homey Flow (automation) triggering via button entities and service calls
- Automatic device discovery and synchronization
- Device registry synchronization (names, areas, deletions)
- Config flow for easy setup
- Options flow for device management
- Room/area organization based on Homey zones
- Device type detection and grouping

### Technical Details
- Uses `DataUpdateCoordinator` for efficient polling
- Supports multiple Homey API endpoint structures (Manager API and V1 API)
- Automatic endpoint discovery
- Robust error handling and fallback mechanisms
- Type hints throughout codebase
- Comprehensive logging

---

## Version History Notes

### How to Use This Changelog

- **Unreleased**: Changes that are in development but not yet released
- **Version numbers**: Follow semantic versioning (MAJOR.MINOR.PATCH)
- **Sections**: Added, Changed, Fixed, Removed, Known Issues
- **Details**: Each entry should be clear and actionable

### Contributing

When making changes:
1. Add entries to the "Unreleased" section
2. Group changes by type (Added, Changed, Fixed, etc.)
3. Be specific about what changed and why
4. Include relevant issue numbers or references
5. When releasing, move "Unreleased" to a new version section

---

**Last Updated**: 2026-01-08