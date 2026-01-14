# Homey Integration for Home Assistant

## ⚠️ Important: API Key Requirement for Real-Time Updates

**This version includes Socket.IO real-time updates!** To enable instant state synchronization (< 1 second latency), you need to create a new API key with the required permission:

1. Go to **Homey Settings → API Keys**
2. **Create a new API key** with the **System → View System** permission (`homey.system.readonly`) enabled
3. Make sure to enable all the same permissions as your current API key, plus the new `homey.system.readonly` permission
4. After creating the new API key, update your Home Assistant integration configuration with the new key
5. Restart Home Assistant or reload the Homey integration

**Note**: The integration will work without this permission, but will use polling (5-10 second updates) instead of instant updates. Socket.IO provides real-time synchronization for the best experience.

---

## Installation

After installing via HACS:

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for **"Homey"**
3. Enter your Homey IP address and API key
4. Select devices to import

For detailed setup instructions, see the [README](README.md).
