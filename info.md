# Homey Integration for Home Assistant

## What’s New in 1.1.9

### ✨ New Features
- **Capability title naming**: Homey apps can provide human-readable titles for capabilities. By default, entities use the capability ID (e.g., "measure_temperature"). Enable this in integration options to use app-provided titles instead (e.g., "Temperature") for cleaner names. Use `homey.rename_entities_to_titles` to update existing entities after enabling.
- **Media player shuffle/repeat**: Control shuffle and repeat modes on speakers (Sonos, etc.)
- **Binary sensor alarms**: Vibration, occupancy, and presence sensors now get proper device classes

### 🔧 Improvements
- **Device classification**: Heater, switch, and vacuum device classes now mapped correctly
- **Capability reporting**: When new capabilities appear on devices, a notification with a prefilled GitHub issue link is shown. Call `homey.test_capability_report` from Developer Tools → Actions to test the report format. Reports include device info, capability type, and suggested platform for unknown capabilities.

For the full list of changes, see the [CHANGELOG](https://github.com/ifMike/homeyHASS/blob/v1.1.9/CHANGELOG.md).

---

## Installation

After installing via HACS:

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for **"Homey"**
3. Enter your Homey IP address and API key
4. Select devices to import

For detailed setup instructions, see the [README](README.md).
