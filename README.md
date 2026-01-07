# Homey Integration for Home Assistant

[![GitHub](https://img.shields.io/github/license/ifMike/homeyHASS)](https://github.com/ifMike/homeyHASS/blob/main/LICENSE)
[![GitHub issues](https://img.shields.io/github/issues/ifMike/homeyHASS)](https://github.com/ifMike/homeyHASS/issues)
[![GitHub stars](https://img.shields.io/github/stars/ifMike/homeyHASS)](https://github.com/ifMike/homeyHASS/stargazers)

A Home Assistant integration that automatically discovers and connects all your Homey devices, making them available natively in Home Assistant.

## Overview

This integration bridges your [Homey](https://homey.app) hub with Home Assistant, allowing you to control all your Homey devices directly from Home Assistant. It supports a wide range of device types including lights, switches, sensors, climate devices, and more. Additionally, it allows you to trigger Homey Flows (automations) from Home Assistant.

**Note**: This is a work in progress made by just one guy with too much time on his hands who couldn't sit on his ass waiting for someone else to create this plugin. It works, but expect bugs, occasional updates, and the occasional "oops, that broke something" moment. 🤷‍♂️

## Features

- 🔍 **Automatic Device Discovery**: Automatically discovers all devices from your Homey hub
- 💡 **Multiple Entity Types**: Supports lights, switches, sensors, binary sensors, covers, climate devices, fans, locks, and media players
- 🎨 **Full Light Control**: Supports dimming, color (HS), and color temperature control
- 📊 **Comprehensive Sensors**: Temperature, humidity, pressure, power, voltage, current, luminance, CO2, CO, and more
- 🚨 **Security Sensors**: Motion, contact, tamper, smoke, CO/CO2 alarms, water leak, and battery sensors
- 🌡️ **Climate Control**: Thermostat support with target temperature control
- 🎬 **Homey Flows**: Trigger your Homey automations (Flows) from Home Assistant as button entities or via service calls
- 🏠 **Room Organization**: Automatically assigns devices to Home Assistant Areas based on Homey rooms
- 🔄 **Automatic Synchronization**: Automatically syncs device changes from Homey (renames, room changes, deletions)
- 📡 **Real-time Updates**: Polling-based updates every 30 seconds (Socket.IO support planned)
- ⚙️ **Easy Setup**: Simple configuration flow through Home Assistant's UI
- 🎯 **Smart Device Grouping**: All entities from the same device are automatically grouped under one device entry

## Prerequisites

Before installing the integration, you need to create an API Key in Homey:

1. Open the [Homey Web App](https://homey.app)
2. Go to **Settings** → **API Keys**
3. Click **New API Key**
4. Give it a name (e.g., "Home Assistant")
5. Select the necessary permissions:
   - `device:read` - Required to read device states
   - `device:write` - Required to control devices
   - `flow:read` - Required to list Flows (optional, for Flow support)
   - `flow:write` - Required to trigger Flows (optional, for Flow support)
6. Copy the API Key (you won't be able to see it again!)

**Important**: Keep this API Key safe - you'll need it during the setup process!

## Installation

### Manual Installation

#### Option 1: Direct File System Access

If you have direct access to your Home Assistant file system (e.g., via SSH, Docker volume, etc.):

1. Download or clone this repository:
   ```bash
   git clone https://github.com/ifMike/homeyHASS.git
   ```

2. Copy the `custom_components/homey` folder to your Home Assistant `custom_components` directory:
   ```
   <config directory>/custom_components/homey/
   ```
   
   For example, if your Home Assistant config directory is `/config`, the path would be:
   ```
   /config/custom_components/homey/
   ```

3. Restart Home Assistant

4. Go to **Settings** → **Devices & Services** → **Add Integration**

5. Search for **"Homey"** and follow the setup instructions

---

#### Option 2: Using Samba (Network Drive)

This is a user-friendly way to access your Home Assistant config folder if you don't have direct file system access.

**Step 1 — Enable Samba in Home Assistant**

1. In Home Assistant UI, go to **Settings** → **Add-ons**
2. Click **Add-on Store** (if not already there)
3. Search for **"Samba share"** and install it
4. Open the add-on configuration
5. Set:
   - **Username**: `homeassistant`
   - **Password**: (choose a password and remember it!)
6. Click **Save** and then **Start**
7. Enable **Start on boot** toggle

**Step 2 — Connect from Your Computer**

**On macOS:**
1. Open **Finder**
2. Press `⌘ + K` (or go to **Go** → **Connect to Server**)
3. Enter your Home Assistant IP address:
   ```
   smb://YOUR_HA_IP_ADDRESS
   ```
   > **Note**: Replace `YOUR_HA_IP_ADDRESS` with your actual Home Assistant IP (e.g., `smb://192.168.1.161`)
4. Click **Connect**
5. Log in with:
   - **Username**: `homeassistant`
   - **Password**: (the password you set in Step 1)
6. You'll now see folders like:
   ```
   config/
   └── custom_components/
   ```
7. Navigate to `config/custom_components/` and copy the `homey` folder there

**On Windows:**
1. Open **File Explorer**
2. In the address bar, type:
   ```
   \\YOUR_HA_IP_ADDRESS
   ```
   > **Note**: Replace `YOUR_HA_IP_ADDRESS` with your actual Home Assistant IP (e.g., `\\192.168.1.161`)
3. Press Enter
4. Log in when prompted with:
   - **Username**: `homeassistant`
   - **Password**: (the password you set in Step 1)
5. Navigate to `config/custom_components/` and copy the `homey` folder there

**Step 3 — Restart Home Assistant**

After copying files:
- Go to **Settings** → **System** → **Restart**

**Step 4 — Add the Integration**

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for **"Homey"** and follow the setup instructions

### Installation via HACS (Coming Soon)

This integration will be available in HACS in the future.

## Configuration

### Setup Steps

1. In Home Assistant, go to **Settings** → **Devices & Services**
2. Click **Add Integration**
3. Search for **Homey**
4. Enter the following information:
   - **Host**: Your Homey's IP address or hostname
     - Examples: `homey.local` or `192.168.1.100` (without `http://` prefix)
     - The integration will automatically add the `http://` prefix if needed
   - **Token**: The API Key you created in Homey
5. Click **Submit**

The integration will automatically discover all your Homey devices and create entities in Home Assistant.

## Usage

### Devices

Once configured, all your Homey devices will appear in Home Assistant under **Settings** → **Devices & Services** → **Homey**. Each device will show all its supported entities grouped together.

**Example**: A Philips Hue lightstrip with power measurement will show as:
- 1 device: "Hue lightstrip plus 1"
  - 1 light entity (for dimming and color control)
  - 1 sensor entity (for power consumption)

### Homey Flows (Automations)

The integration exposes your Homey Flows in two ways:

#### 1. Button Entities

Each enabled Homey Flow appears as a button entity in Home Assistant. Simply press the button to trigger the Flow.

**Entity ID format**: `button.<flow_name>`

#### 2. Service Call

You can trigger Flows from automations, scripts, or the Developer Tools:

**Service**: `homey.trigger_flow`

**Service Data**:
```yaml
# Trigger by Flow ID
flow_id: "1234567890abcdef"

# OR trigger by Flow name
flow_name: "Turn on all lights"
```

**Example Automation**:
```yaml
automation:
  - alias: "Trigger Homey Flow at Sunset"
    trigger:
      - platform: sun
        event: sunset
    action:
      - service: homey.trigger_flow
        data:
          flow_name: "Evening Scene"
```

## Device Organization

Devices are automatically organized by:

- **Room/Area**: Devices are assigned to their Homey rooms, which become Areas in Home Assistant
- **Device Type**: Automatically detected based on capabilities (light, switch, sensor, etc.)
- **Grouping**: All entities from the same device are grouped under one device entry

**Note**: A single physical device may have multiple entities (e.g., a light with power measurement will show as 1 device with 2 entities: a light entity and a power sensor entity). This is normal and expected behavior.

## Automatic Synchronization

The integration automatically synchronizes changes made in Homey with Home Assistant:

### Device Name Changes
- When you rename a device in Homey, the device name in Home Assistant updates automatically
- Updates occur within ~30 seconds (the polling interval)

### Room/Area Changes
- When you move a device to a different room in Homey, the device's area in Home Assistant updates automatically
- New areas are automatically created in Home Assistant if they don't exist
- Room names are refreshed periodically (~5 minutes) to pick up room name changes

### Device Deletion
- When you delete a device in Homey, it and all its entities are automatically removed from Home Assistant
- Cleanup occurs within ~30 seconds after deletion

### Update Frequency
- Device states: Updated every 30 seconds via polling
- Device names/rooms: Checked every 30 seconds
- Zones (rooms): Refreshed every ~5 minutes

**Note**: Entity names (`_attr_name`) are set during initialization and won't update automatically. The device name in the UI will update, but individual entity names may show the old name until you reload the integration. This is a Home Assistant limitation and is acceptable for most use cases.

## Supported Devices

The integration supports devices with the following capabilities:

### Lights
- `onoff` - Basic on/off control
- `dim` - Brightness control (0-100%)
- `light_hue` - Color hue control (0-360°)
- `light_saturation` - Color saturation control (0-100%)
- `light_temperature` - Color temperature control (Kelvin)

**Supported Color Modes**:
- `onoff` - Simple on/off
- `brightness` - Dimming only
- `hs` - Hue and saturation (full color)
- `color_temp` - Color temperature (warm/cool white) - Uses Kelvin scale (2000K-6500K)

**Note**: HS color and color temperature modes are mutually exclusive. If both are available, HS color mode is preferred.

### Switches
- `onoff` - On/off control

**Note**: Devices with dimming or color capabilities are created as lights, not switches.

### Sensors
- `measure_temperature` - Temperature sensor (°C)
- `measure_humidity` - Humidity sensor (%)
- `measure_pressure` - Pressure sensor (hPa)
- `measure_power` - Power consumption sensor (W)
- `measure_voltage` - Voltage sensor (V)
- `measure_current` - Current sensor (A)
- `measure_luminance` - Light level sensor (lux)
- `measure_co2` - CO2 sensor (ppm)
- `measure_co` - CO sensor (ppm)

### Binary Sensors
- `alarm_motion` - Motion detector
- `alarm_contact` - Door/window contact sensor
- `alarm_tamper` - Tamper sensor
- `alarm_smoke` - Smoke detector
- `alarm_co` - CO alarm
- `alarm_co2` - CO2 alarm
- `alarm_water` - Water leak sensor
- `alarm_battery` - Low battery indicator

### Covers
- `windowcoverings_state` - Window covering position (0-100%)
- `windowcoverings_tilt_up` / `windowcoverings_tilt_down` - Tilt control

### Climate
- `target_temperature` - Target temperature control (°C)
- `measure_temperature` - Current temperature (°C)

### Fans
- `fan_speed` - Fan speed control (0-100%)
- `onoff` - On/off control

### Locks
- `locked` - Lock state and control

### Media Players
- `volume_set` - Volume control (0-100%)
- `volume_mute` - Mute control
- `speaker_playing` - Play/pause control
- `speaker_next` - Next track
- `speaker_prev` - Previous track

## Troubleshooting

### Connection Issues

If you're having trouble connecting to Homey:

1. **Check the Host Address**: 
   - Make sure you're using the correct IP address or hostname
   - Examples: `192.168.1.100` or `homey.local` (no `http://` prefix needed)
   - The integration will automatically add the `http://` prefix if needed

2. **Check API Key**: 
   - Verify that your API Key is correct and has the necessary permissions
   - Make sure you copied the entire key (they can be quite long)

3. **Network Access**: 
   - Ensure that your Home Assistant instance can reach your Homey hub on the network
   - Check if there are any firewalls blocking the connection
   - Try pinging your Homey from the Home Assistant host

4. **Check Logs**: 
   - Go to **Settings** → **System** → **Logs**
   - Look for entries starting with `homey` or `custom_components.homey`
   - Enable debug logging if needed:
     ```yaml
     logger:
       default: info
       logs:
         custom_components.homey: debug
     ```

### Devices Not Appearing

If devices aren't appearing in Home Assistant:

1. **Check Device Capabilities**: 
   - Make sure your devices have supported capabilities (see Supported Devices above)
   - Some devices may not expose their capabilities via the API

2. **Restart Integration**: 
   - Try removing and re-adding the integration
   - Or reload the integration: **Settings** → **Devices & Services** → **Homey** → **⋮** → **Reload**

3. **Check Logs**: 
   - Check the logs for any errors related to device discovery
   - Look for messages about unsupported capabilities

### Duplicate Devices

If you see duplicate devices:

1. **Reload Integration**: 
   - Go to **Settings** → **Devices & Services** → **Homey** → **⋮** → **Reload**
   - This will refresh the device registry

2. **Restart Home Assistant**: 
   - Sometimes a full restart is needed to refresh the device registry
   - This is especially true after updating the integration

3. **Check Device Info**: 
   - All entities from the same device should be grouped under one device entry
   - If you see separate devices with the same name, it may be a device registry caching issue

### Real-time Updates Not Working

If device states aren't updating:

- The integration uses polling for updates (every 30 seconds by default)
- Socket.IO support is planned for real-time updates
- Check your network connectivity between Home Assistant and Homey
- Check the logs for any connection errors

### Device Changes Not Syncing

If device name or room changes made in Homey aren't appearing in Home Assistant:

1. **Wait for Polling**: Changes are detected during the next polling cycle (up to 30 seconds)
2. **Check Logs**: Look for messages about device registry updates in the logs
3. **Manual Refresh**: Reload the integration: **Settings** → **Devices & Services** → **Homey** → **⋮** → **Reload**
4. **Verify Changes**: Make sure the changes were actually saved in Homey

## Development

### Project Structure

```
custom_components/homey/
├── __init__.py          # Integration setup and service registration
├── manifest.json        # Integration metadata
├── config_flow.py       # Configuration flow UI
├── const.py            # Constants and capability mappings
├── coordinator.py      # Data update coordinator with device registry sync
├── homey_api.py        # Homey API client
├── device_info.py      # Device info helper functions
├── strings.json        # User-facing strings
├── switch.py           # Switch platform
├── light.py            # Light platform
├── sensor.py           # Sensor platform
├── binary_sensor.py    # Binary sensor platform
├── cover.py            # Cover platform
├── climate.py          # Climate platform
├── fan.py              # Fan platform
├── lock.py             # Lock platform
├── media_player.py     # Media player platform
└── button.py           # Button platform (for Flows)
```

### Key Technical Features

- **Device Registry Synchronization**: The coordinator automatically updates the Home Assistant device registry when devices are renamed, moved to different rooms, or deleted in Homey
- **Consistent Device Info**: All entities from the same device use identical device identifiers to ensure proper grouping
- **Smart Entity Creation**: Prevents duplicate entities (e.g., devices with light capabilities won't also create switch entities)
- **Zone Refresh**: Periodically refreshes room/zone information to keep areas up-to-date
- **Robust API Handling**: Supports multiple Homey API endpoint structures and automatically discovers the correct one

### Contributing

Contributions are welcome! Please feel free to:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Reporting Issues

If you encounter any issues, please:

1. Check the [existing issues](https://github.com/ifMike/homeyHASS/issues) first
2. Create a new issue with:
   - A clear description of the problem
   - Steps to reproduce
   - Home Assistant version
   - Homey firmware version
   - Relevant log entries

## API Documentation

For more information about the Homey API:

- [Homey API Documentation](https://api.developer.homey.app/)
- [Homey API Keys Guide](https://support.homey.app/hc/en-us/articles/8178797067292-Getting-started-with-API-Keys)
- [Homey Local API](https://apps.developer.homey.app/the-basics/local-api)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Credits

- **Author**: Mikael Collin ([@ifmike](https://github.com/ifMike))
- **Built for**: Home Assistant
- **Uses**: Homey Local API by Athom

## Acknowledgments

- Built for the Home Assistant community
- Uses the Homey Local API by Athom
- Inspired by the need to bridge Homey and Home Assistant ecosystems
- Created by one guy with too much time on his hands who couldn't sit on his ass waiting for someone else to build this 😄

## Support

For support, please:

1. Check the [Troubleshooting](#troubleshooting) section above
2. Search [existing issues](https://github.com/ifMike/homeyHASS/issues)
3. Create a new issue if needed

---

**Note**: This is a community-driven project and is not officially affiliated with Athom or Home Assistant. It's a work in progress made by just one guy with too much time on his hands who couldn't sit on his ass waiting for someone else to create this plugin. If you find bugs, report them. If you want features, ask nicely. If you want to help, pull requests are welcome! 🚀
