# Homey Integration for Home Assistant

## What’s New in 1.1.7

### 🌐 Multi-Homey Support
- Supports multiple Homey hubs with collision-safe device IDs
- Auto-rescope when a second hub is added (single-hub users are unaffected)
- Notifications for migration status and duplicate hub detection

### 🧠 Homey Logic Variables
- Logic numbers/booleans/strings now appear as Number, Switch, and Text entities
- **API key update required** if you don’t have the permissions:
  - **View Variables** (`homey.logic.readonly`) to read variables
  - **Variables** (`homey.logic`) to edit variables from Home Assistant

### ⚙️ Options & Settings Improvements
- Update Homey host/IP and API key from the integration options
- More stable string exposure toggles and related settings

### ✅ Added
- Read-only string sensors enabled by default (optional editable text entities)
- Extra switch support for additional settable boolean capabilities
- Enum/string select entities for mode-like capabilities
- Capability reporting with prefilled GitHub issue links
- Generic sensor coverage for numeric/string capabilities
- Heat pump compressor counters (`compressor_hours`, `compressor_starts`)

### 🧰 Fixes
- Cover control handling for enum vs numeric capabilities
- Prevent cleanup from removing the Homey Logic virtual device
- Multi-homey entity collisions and migration gaps addressed
- Light temperature inversion toggle persistence
- Binary sensor filtering for settable booleans
- Restored missing heat pump status entities

For the full list of changes, additions, and fixes, see the [CHANGELOG](https://github.com/ifMike/homeyHASS/blob/v1.1.7/CHANGELOG.md).

---

## Installation

After installing via HACS:

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for **"Homey"**
3. Enter your Homey IP address and API key
4. Select devices to import

For detailed setup instructions, see the [README](README.md).
