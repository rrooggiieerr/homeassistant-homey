# Homey Integration for Home Assistant

## ⚠️ Important: API Key Requirement for Real-Time Updates

**This version includes Socket.IO real-time updates!** To enable instant state synchronization (< 1 second latency), you need to update your API key permissions:

1. Go to **Homey Settings → API Keys**
2. **Edit your existing API key** (you don't need to create a new one)
3. Enable the **System → View System** permission (`homey.system.readonly`)
4. After updating permissions, restart Home Assistant or reload the Homey integration

**Note**: The integration will work without this permission, but will use polling (5-10 second updates) instead of instant updates. Socket.IO provides real-time synchronization for the best experience.

---

## Installation

After installing via HACS:

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for **"Homey"**
3. Enter your Homey IP address and API key
4. Select devices to import

For detailed setup instructions, see the [README](README.md).
