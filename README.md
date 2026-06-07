# Hanchu ESS Home Assistant Integration

`hanchu` is a custom Home Assistant integration for the Hanchu ESS PCS (Power Conversion System), prepared for HACS.


## Installation

### Via HACS (recommended)

1. Open HACS in your Home Assistant instance.
2. Go to **Integrations → ⋮ → Custom repositories**.
3. Add `https://github.com/lancedfr/hassio-hanchu-ess` as an **Integration** repository.
4. Search for **Hanchu ESS** in HACS and click **Download**.
5. Restart Home Assistant.
6. Go to **Settings → Devices & Services → Add Integration**, search for **Hanchu ESS**, and follow the setup wizard.

### Manual installation

1. Download or clone this repository:
   ```bash
   git clone https://github.com/lancedfr/hassio-hanchu-ess.git
   ```
2. Copy the `custom_components/hanchu_ess` folder into your Home Assistant `config` directory so the path becomes:
   ```
   <config>/custom_components/hanchu_ess/
   ```
3. Restart Home Assistant.
4. Go to **Settings → Devices & Services → Add Integration**, search for **Hanchu ESS**, and follow the setup wizard.

### Configuration

When prompted, enter:

| Field | Description |
|-------|-------------|
| **Name** | Friendly name for this device (default: `Hanchu ESS`) |
| **Account** | Your Hanchu ESS gateway account (email or username) |
| **Password** | Your Hanchu ESS gateway password |
| **Device Serial Number (SN)** | The SN shown on the homepage of the official Hanchu ESS site or app |

---

## Sensors

### Yearly energy totals (kWh)

Polled every **30 minutes** from the `historyStaticsChart` endpoint. Values reset to 0 on January 1st each year.

| Sensor | Description |
|--------|-------------|
| **Load** | Total energy consumed by the home |
| **Generation** | Total solar energy generated |
| **Charge** | Total energy charged into the battery |
| **Discharge** | Total energy discharged from the battery |
| **From Grid** | Total energy imported from the grid |
| **To Grid** | Total energy exported to the grid |

### Live power flows (W)

Polled every **10 minutes** from the `powerChart` endpoint.

| Sensor | Description |
|--------|-------------|
| **Solar Production Power** | Current solar panel output |
| **Ac Coupled Solar Power** | Current AC Coupled Inverter output |
| **Home Usage Power** | Current household power consumption |
| **Grid Import Power** | Power currently being drawn from the grid (0 when exporting) |
| **Grid Export Power** | Power currently being sent to the grid (0 when importing) |
| **Battery Charge Power** | Power currently charging the battery (0 when discharging) |
| **Battery Discharge Power** | Power currently discharging from the battery (0 when charging) |
| **Battery Power** | Net battery power — positive = discharging, negative = charging |

### Battery state

| Sensor | Description |
|--------|-------------|
| **Home Battery** | Live battery state-of-charge (0–100 %) |

![sensors.png](sensors.png)

---

## Configuration entities

All configuration entities appear under the **Configuration** section of the Hanchu ESS device page in Home Assistant. Changes are staged locally and are not sent to the device until you press **Write Settings**.

### Work mode

| Entity | Options |
|--------|---------|
| **Work Mode** | User-defined / Self-consumption mode |

### Power and SOC limits

| Entity | Range | Unit |
|--------|-------|------|
| **Charging Power Maximum** | 0–5000 | W |
| **Discharge Power Maximum** | 0–5000 | W |
| **Grid to Battery Charge Maximum** | 0–100 | % |
| **Maximum Charge SOC** | 0–100 | % |
| **On-Grid Battery Discharge Minimum** | 0–100 | % |
| **Off-Grid Battery Discharge Minimum** | 0–100 | % |

### Charge/discharge time periods

| Entity | Description |
|--------|-------------|
| **Charge Period 1 Start** | Start time of the first daily charge window |
| **Charge Period 1 End** | End time of the first daily charge window |
| **Discharge Period 1 Start** | Start time of the first daily discharge window |
| **Discharge Period 1 End** | End time of the first daily discharge window |

Time values are stored as seconds-since-midnight by the PCS and displayed as HH:MM in Home Assistant.

![configuration.png](configuration.png)

---

## Settings buttons

Two button entities appear on the Hanchu ESS device page in Home Assistant:

| Button | Action |
|--------|--------|
| **Read Settings** | Fetches current PCS settings from the device via `iotGet` and updates all entities |
| **Write Settings** | Sends only the settings you have changed to the device via `iotSet` |

Changes made to the work mode, numeric, or time period entities are **staged locally** and are not sent to the device until you press **Write Settings**. Only fields that were actually changed are written, avoiding unnecessary `iotSet` calls and respecting the API rate limit.

![settings.png](settings.png)

---

## Services

### `hanchu_ess.fast_charge_discharge`

Imperatively starts or stops a fast charge or discharge cycle on the battery.
Available from **Developer Tools → Services**, automations, and scripts.

> **Safety note:** To ensure optimal performance and safety, please do not change any control settings or perform OTA updates during fast charging or discharging.

| Field | Required | Description |
|-------|----------|-------------|
| **mode** | Yes | `fast_charge` — start charging at maximum rate<br>`fast_discharge` — start discharging at maximum rate<br>`stop_charge` — cancel an active fast charge<br>`stop_discharge` — cancel an active fast discharge |
| **duration** | For start modes only | How long to run the cycle, in whole minutes (1–1440). Ignored for stop modes. |

**Example — start a 15-minute fast charge:**
```yaml
service: hanchu_ess.fast_charge_discharge
data:
  mode: fast_charge
  duration: 15
```

**Example — stop fast charge:**
```yaml
service: hanchu_ess.fast_charge_discharge
data:
  mode: stop_charge
```

---

## What is included

- UI-only setup using a config flow — collects account, password, and device serial number
- Four `DataUpdateCoordinator` classes in `coordinator.py`:
  - `HanchuAuthCoordinator` — refreshes the OAuth token every hour
  - `HanchuDataCoordinator` — polls yearly energy statistics every 30 minutes
  - `HanchuPowerCoordinator` — polls live power flows and battery SOC every 10 minutes
  - `HanchuSettingsCoordinator` — on-demand reader/writer for work mode settings (no auto-poll)
- **15 sensor entities** (6 energy + 7 live power + 1 battery SOC)
- **1 select entity** — Work Mode (Configuration category)
- **6 number entities** — power (0–5000 W) and SOC limits (0–100 %, whole numbers only) (Configuration category)
- **4 time entities** — charge/discharge period 1 boundaries (Configuration category)
- **2 button entities** — **Read Settings** (fetches via `iotGet`) and **Write Settings** (sends only changed values via `iotSet`)
- **1 service** — `hanchu_ess.fast_charge_discharge` (fast charge / discharge control)
- Re-authentication flow — credentials can be updated via the UI without removing the entry
- AES-CBC payload encryption and RSA password encryption matching the official Hanchu ESS app protocol
- CI, linting, and unit tests

## Project layout

```
custom_components/hanchu_ess/   Integration source files
  __init__.py               Entry setup, wires up all coordinators
  config_flow.py            UI config flow (account, password, SN) + re-auth
  const.py                  API URLs, AES/RSA keys, poll intervals, IoT field names
  coordinator.py            Auth, data, power, and settings coordinators
  sensor.py                 Sensor platform — 6 energy + 7 live power + 1 battery SOC
  select.py                 Select platform — Work Mode (stages changes locally)
  number.py                 Number platform — power and SOC limit settings (stages locally)
  time.py                   Time platform — charge/discharge time periods (stages locally)
  button.py                 Button platform — Read Settings and Write Settings
  manifest.json
  strings.json / translations/

tests/
  test_scaffold.py                Structural checks
  test_coordinator.py             Unit tests for auth, data, and power coordinators
  test_settings_coordinator.py    Unit tests for settings coordinator (read + write + local staging)
  test_button.py                  Unit tests for Read/Write Settings button entities
  test_decrypt.py                 AES-CBC roundtrip and decrypt utility
  test_oauth_live.py              Live OAuth login test (real endpoint)
  test_data_live.py               Live energy statistics test (real endpoint)
  test_power_live.py              Live power data test (real endpoint)
  test_fast_charge_live.py        Live fast charge / discharge test (real endpoint)

scripts/scaffold_check.py   Tiny local structure checker
.github/workflows/ci.yml    CI for lint + tests
```

## Quick local checks

```powershell
python scripts/scaffold_check.py
python -m pytest tests/test_scaffold.py tests/test_coordinator.py tests/test_settings_coordinator.py tests/test_button.py tests/test_decrypt.py -v
```

## Run live tests (real endpoints)

Live tests are skipped automatically unless credentials are provided via environment variables:

```powershell
$env:HANCHU_TEST_ACCOUNT = "your@email.com"
$env:HANCHU_TEST_PWD     = "yourpassword"
$env:HANCHU_TEST_SN      = "yourserialnum"

python -m pytest tests/test_oauth_live.py tests/test_data_live.py tests/test_power_live.py tests/test_fast_charge_live.py -v
```

`test_decrypt.py` also doubles as a CLI decrypt tool:

```powershell
python tests/test_decrypt.py <base64-ciphertext>
```

