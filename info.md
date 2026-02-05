# Homey Integration for Home Assistant

## What’s New in 1.1.8

### 🧰 Fixes
- **Cover stop**: Enum-based covers now stop correctly even when a position capability exists
- **Token prompts**: Avoids nightly reauth on transient 401s and logs the reason clearly for troubleshooting

For the full list of changes, additions, and fixes, see the [CHANGELOG](https://github.com/ifMike/homeyHASS/blob/v1.1.8/CHANGELOG.md).

---

## Installation

After installing via HACS:

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for **"Homey"**
3. Enter your Homey IP address and API key
4. Select devices to import

For detailed setup instructions, see the [README](README.md).
