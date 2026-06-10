# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```powershell
# Install dev dependencies (do this once)
pip install -e ".[dev]"

# Lint
ruff check .

# Run all unit tests (no live network calls)
python -m pytest tests/test_scaffold.py tests/test_coordinator.py tests/test_settings_coordinator.py tests/test_button.py tests/test_decrypt.py -v

# Run a single test class or method
python -m pytest tests/test_coordinator.py::TestHanchuDataCoordinator::test_returns_current_year_values -v

# Scaffold structure check (must pass before CI)
python scripts/scaffold_check.py

# Run live tests (requires editing _CONF_ACCOUNT / _CONF_PWD / _CONF_SN constants in each file first)
python -m pytest tests/test_oauth_live.py tests/test_data_live.py tests/test_power_live.py -v

# Decrypt a captured Base64 AES-CBC ciphertext from the API
python tests/test_decrypt.py <base64-ciphertext>
```

CI runs `ruff check .`, `python scripts/scaffold_check.py`, and `python -m unittest discover -s tests -p "test_*.py"` on every push.

## Architecture

### Request/response encryption
All API calls use a two-layer encryption scheme reverse-engineered from the official Hanchu app:
- **Password**: RSA/ECB/PKCS1Padding with a 1024-bit X509 public key (`RSA_PUBLIC_KEY_B64` in `const.py`) → Base64
- **Request body**: JSON serialised, AES-128-CBC + PKCS7 padding → Base64 (`_encrypt_payload` in `coordinator.py`)
- Key and IV are both `b"9z64Qr8mZH7Pg8d1"` (same 16 bytes), sourced from the Hanchu web JS bundle
- Responses are plain JSON (not encrypted); `_decrypt_payload` exists only as a debug/test utility

### Coordinator chain
Four coordinators; the data, power, and settings coordinators all depend on the auth coordinator for a token:

```
HanchuAuthCoordinator (1h)  →  HanchuDataCoordinator (30min)
                            →  HanchuPowerCoordinator (10min)
                            →  HanchuSettingsCoordinator (on-demand, no auto-poll)
```

All four are stored in `entry.runtime_data` as a `HanchuRuntimeData` dataclass (defined in `__init__.py`). Platforms import `HanchuConfigEntry` from `.` and access coordinators via `entry.runtime_data.<name>_coordinator`.

### Sensor entities
`sensor.py` registers **14 sensor entities** per config entry:
- Six `HanchuEnergySensor` instances (yearly totals: load, generation, charge, discharge, from_grid, to_grid) backed by `HanchuDataCoordinator`
- Seven `HanchuLivePowerSensor` instances (solar_power, load_power, grid_import_power, grid_export_power, battery_charge_power, battery_discharge_power, battery_power) backed by `HanchuPowerCoordinator`
- One `HanchuBatterySensor` (live SOC, 0–100%) backed by `HanchuPowerCoordinator`; the API returns SOC as a decimal fraction (e.g. `"0.74"`), multiplied by 100 in the coordinator

### Settings entities (select, number, time, button)
All backed by `HanchuSettingsCoordinator` (`update_interval=None` — no automatic polling):

- **select.py** — 1 `HanchuWorkModeSelect` entity (User-defined / Self-consumption mode); `EntityCategory.CONFIG`
- **number.py** — 6 `HanchuSettingNumber` entities (power limits 0–5000 W, SOC thresholds 0–100 %, both whole-number step); `EntityCategory.CONFIG`
- **time.py** — 4 `HanchuTimePeriod` entities (charge period 1 start/end, discharge period 1 start/end); `EntityCategory.CONFIG`
- **button.py** — 2 button entities:
  - `HanchuReadSettingsButton` — calls `coordinator.async_refresh()` → fetches from `iotGet`; clears `_pending`
  - `HanchuWriteSettingsButton` — calls `coordinator.async_write_pending()` → sends only staged changes to `iotSet`

**Staging behaviour**: changing a select/number/time entity calls `coordinator.async_update_local({key: value})`, which (a) merges the value into `coordinator.data` so entities update immediately, and (b) adds the key to `coordinator._pending`. `async_write_pending()` sends only `_pending` keys to `iotSet` and clears the dict; a successful read (`_async_update_data`) also clears `_pending`. This avoids writing unchanged fields and respects the `iotSet` rate limit.

### Other notes
- Config entry only supports a single instance (`single_config_entry: true` in manifest; aborts in `config_flow.py` if an entry already exists).
- `_device_info(entry)` in `sensor.py` is shared by all platforms to ensure all entities appear under the same HA device.

## Releasing a New Version

1. Bump `"version"` in `custom_components/hanchu_ess/manifest.json`.
2. In `CHANGELOG.md`: move `[Unreleased]` bullets into a new `## [X.Y.Z] - YYYY-MM-DD` section; restore an empty `[Unreleased]`; update comparison links at the bottom.
3. Commit both files, create a tag matching the version (`v0.2.0` for version `0.2.0`), push the tag.
4. The GitHub Actions `release.yml` workflow extracts the changelog section, zips `custom_components/hanchu_ess/` as `hanchu.zip`, and publishes a GitHub Release.

Tag format rule: `v` + exact version string from `manifest.json`. The changelog entry must exist before the tag is pushed or the workflow exits with an error.
