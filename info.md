# Homey Integration for Home Assistant

## ⚠️ Action Required Before Updating

**This update includes major real-time improvements and requires a NEW API key.**

1. Go to **Homey Settings → API Keys**
2. **Create a new API key** with **System → View System** permission (`homey.system.readonly`)
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
