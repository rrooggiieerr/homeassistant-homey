# Homey Integration for Home Assistant

## ⚠️ Action Required Before Updating

**This update includes major real-time improvements and requires a NEW API key.**

1. Go to **Homey Settings → API Keys**
2. **Create a new API key** with these permissions:
   
   **Required Permissions:**
   - **View devices** (`homey.device.readonly`) - Required to read device states and discover devices
   - **Control devices** (`homey.device.control`) - Required to control devices (turn on/off, set brightness, etc.)
   - **View System** (`homey.system.readonly`) - Required for Socket.IO real-time updates. Without this, the integration will use polling (5-10 second updates) instead of instant updates (< 1 second).
   
   **Recommended Permissions:**
   - **View Zones** (`homey.zone.readonly`) - Recommended for room/area organization. Without this, devices won't be organized by Homey rooms.
   - **View Flows** (`homey.flow.readonly`) - Recommended to list Flows (needed for Flow button entities and service calls using flow names)
   - **Start Flows** (`homey.flow.start`) - Recommended to trigger, enable, and disable Flows
   - **View Moods** (`homey.mood.readonly`) - Recommended to list Moods (needed for Mood entities)
   - **Set Moods** (`homey.mood.set`) - Recommended to trigger Moods
3. Update the integration in Home Assistant (**Settings → Devices & Services → Homey → Configure**)
4. Restart Home Assistant or reload the integration

Without this permission, real-time updates will not work and the integration will fall back to polling (5-10 seconds).

---

## What’s New in 1.1.6

### 🚀 Major Real-Time Updates
- **Socket.IO real-time updates** (< 1 second latency)
- Automatic fallback to polling (5-10 seconds) if Socket.IO fails
- Reduced log noise for Socket.IO updates

### ✅ New Configuration Options
- **Options flow** to change Homey host/IP, API key, and fallback polling interval
- **Reauthentication flow** when API key becomes invalid
- **Auto-recovery** after Homey restart or network outages

### 🧰 Stability & Fixes
- Cover position compatibility fixes for older Home Assistant versions
- Device selection defaults to **all devices selected**
- Prevents device removals when Homey temporarily returns no devices

For the full list of changes, additions, and fixes, see the [CHANGELOG](https://github.com/ifMike/homeyHASS/blob/v1.1.6/CHANGELOG.md).

---

## Installation

After installing via HACS:

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for **"Homey"**
3. Enter your Homey IP address and API key
4. Select devices to import

For detailed setup instructions, see the [README](README.md).
