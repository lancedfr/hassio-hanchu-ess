# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- Poll interval changes via **Configure** now take effect immediately without requiring a manual reload of the integration.

## [0.3.0] - 2026-06-10

### Fixed

- Release zip now contains integration files at the archive root (not nested under
  `custom_components/hanchu_ess/`), and excludes compiled bytecode.

## [0.2.0] - 2026-06-10

### Added

- Release planning and changelog template based on Keep a Changelog.

## [0.1.0] - 2026-06-09

### Added

- OAuth-based authentication with the Hanchu ESS cloud gateway (RSA-encrypted
  password, AES-CBC-encrypted request bodies, automatic token refresh every hour).
- **Energy sensors** (yearly totals, kWh, `TOTAL` state class, resets 1 Jan):
  Load, Generation, Charge, Discharge, From Grid, To Grid.
- **Live power sensors** (watts, `MEASUREMENT` state class, polled every
  10 minutes by default): Solar Production Power, Home Usage Power, Grid Import
  Power, Grid Export Power, Battery Charge Power, Battery Discharge Power, Battery
  Power.
- **AC Coupled Solar Power sensor** — reads production from a second RS485 meter
  channel for systems with AC-coupled solar inverters.
- **Battery SOC sensor** — Home Battery state-of-charge (%).
- **Settings entities** (all backed by `iotGet`/`iotSet`, staged locally until
  the Write Settings button is pressed):
  - Work Mode select: User-defined / Self-consumption mode.
  - Charging Power Maximum (W).
  - Discharge Power Maximum (W).
  - Grid to Battery Charge Maximum (%).
  - Maximum Charge SOC (%).
  - On-Grid Battery Discharge Minimum (%).
  - Off-Grid Battery Discharge Minimum (%).
  - Three charge time periods (start + end per period) and three discharge time
    periods — six `time` entities each.
- **Read Settings / Write Settings buttons** for explicit IoT fetch and push.
- **`hanchu_ess.fast_charge_discharge` service** — start/stop fast charge or fast
  discharge with a configurable duration (1–1440 minutes).
- Configurable poll intervals set at integration setup time and adjustable via
  **Configure** (options flow) without removing the integration:
  - Energy data poll interval (default 1800 s, minimum 60 s).
  - Live power poll interval (default 600 s, minimum 30 s).
- Re-authentication flow: credentials can be updated in-place when the cloud
  gateway rejects them.
- HACS-ready repository structure with `hacs.json` and `manifest.json`.

[Unreleased]: https://github.com/lancedfr/hassio-hanchu-ess/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/lancedfr/hassio-hanchu-ess/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/lancedfr/hassio-hanchu-ess/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/lancedfr/hassio-hanchu-ess/releases/tag/v0.1.0
