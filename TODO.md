# TODO

## High priority

- [x] **Add re-auth flow** — implement `async_step_reauth` in `config_flow.py` so users can re-enter credentials via the UI when `ConfigEntryAuthFailed` is raised, without removing the entry.

- [x] **Switch live tests to env vars** — revert `test_oauth_live.py`, `test_data_live.py`, and `test_power_live.py` to read credentials from `HANCHU_TEST_ACCOUNT`, `HANCHU_TEST_PWD`, and `HANCHU_TEST_SN` environment variables, and skip automatically with `unittest.skipUnless` when they are not set. The current hardcoded-constants approach risks accidentally committing real credentials.

- [x] **Reduce data poll interval** — `DATA_POLL_MINUTES = 5` polls for yearly energy totals that change at most a few times per hour. Change to 60 minutes (or 30 at most).

- [x] **CI missing `homeassistant` dependency** — `pyproject.toml` dev extras don't include `homeassistant`, so `pip install -e ".[dev]"` in CI won't install it and `pytest tests/` fails with import errors. Add `homeassistant>=2024.6.0` to dev deps.

## Medium priority

- [x] **Migrate to `entry.runtime_data`** — replace the `hass.data[DOMAIN][entry.entry_id]` coordinator storage pattern in `__init__.py` with `entry.runtime_data`, the preferred HA approach since 2024.x. It is type-safe, entry-scoped, and doesn't require manual cleanup.

- [x] **Standardise test runner** — CI uses `python -m unittest discover` but the project has `pytest.ini` and dev workflow uses `pytest`. Pick one and use it everywhere.

- [x] **Stale coordinator docstrings** — `HanchuDataCoordinator` class docstring says "every 10 minutes" but the poll interval is 30 minutes. Fix to match `DATA_POLL_MINUTES`.

- [x] **Unnecessary forward-reference strings in coordinator type hints** — `auth: "HanchuAuthCoordinator"` in `HanchuDataCoordinator` and `HanchuPowerCoordinator` can be unquoted; `from __future__ import annotations` is present and the class is defined earlier in the same file.

- [x] **`pyproject.toml` metadata is stale** — description still says "Scaffold for…" and authors still say "Hanchu Maintainers". Update to reflect current state and ownership.

## Low priority

- [x] **Redundant `token_data` attribute on `HanchuAuthCoordinator`** — the coordinator stores the token in both `self.token_data` and `self.data` (the parent class attribute). Remove `token_data`; the `access_token` property can read from `self.data` directly.

- [x] **Duplicated HTTP headers across all three coordinators** — extract to a module-level `_BASE_HEADERS` constant and spread it per-call with the appropriate `Access-Token` value.

- [x] **Fix `CONF_ACCOUNT` comment** — `const.py` describes it as `# account email address` but the config flow accepts usernames too (per `strings.json`). Update the comment.

## Code review findings

- [x] **`TOTAL_INCREASING` on yearly-reset sensors** — `HanchuEnergySensor` uses `SensorStateClass.TOTAL_INCREASING`, but these are yearly totals that reset to 0 every January 1st. HA's Energy dashboard discards data when a `TOTAL_INCREASING` sensor decreases. Change to `SensorStateClass.TOTAL` and expose a `last_reset` property returning `datetime(current_year, 1, 1, tzinfo=timezone.utc)`.

- [x] **Redundant `self.data` assignment in auth coordinator** — `coordinator.py` manually sets `self.data = token_data` before `return token_data`. `DataUpdateCoordinator` already assigns `self.data` from the return value; the manual line is dead code.

- [x] **Dead fallback in `access_token` property** — `coordinator.py` checks for an `"access_token"` key that is never stored (only `"token"` is ever written). Simplify to `return self.data.get("token") if self.data else None`.

- [x] **`device_info` duplicated across sensor classes** — `HanchuEnergySensor` and `HanchuBatterySensor` both build an identical `device_info` dict inline. Extract to a module-level helper `_device_info(entry)` to avoid drift.

- [x] **Magic request body values should be named constants** — `"devType": "2"` and `"maxCount": 1440` in `HanchuDataCoordinator._async_update_data` are unexplained magic values. Move them to `const.py` as `DATA_DEV_TYPE` and `DATA_MAX_COUNT`.

- [x] **Fix `manifest.json` logger namespace** — `"loggers": ["custom_components.hanchu"]` is missing the `_ess` suffix. The actual logger is `custom_components.hanchu_ess.*`, so HA log-level overrides in `configuration.yaml` won't work. Change to `"custom_components.hanchu_ess"`.

- [x] **Use `DATA_DEV_TYPE` constant in `HanchuSettingsCoordinator`** — `_async_update_data` and `async_set_settings` both hardcode `"devType": "2"` inline, whereas `HanchuDataCoordinator` correctly uses the `DATA_DEV_TYPE` constant. Replace both raw `"2"` references with the constant.

- [x] **Fix "5 minutes" docstrings** — `HanchuPowerCoordinator` (coordinator.py) and `HanchuBatterySensor` (sensor.py) both say "every 5 minutes" but the default `POWER_POLL_SECONDS = 600` is 10 minutes. Update to "10 minutes (default)".

- [x] **Fix `conftest.py` password key** — `mock_config_entry` fixture uses `"password": "test_password"` but the actual config key is `CONF_PWD = "pwd"`. Any test that exercises auth via this fixture silently gets `None` for the password. Change `"password"` → `"pwd"`.

- [x] **Add `options` block to `strings.json`** — the `options.step.init` section is present in `translations/en.json` but missing from `strings.json`. HA uses `strings.json` as the canonical schema, so options flow fields have no labels. Add the matching block.

- [x] **Sync `pyproject.toml` version with `manifest.json`** — `pyproject.toml` is at `0.1.0` while `manifest.json` is at `0.3.0`. They should stay in sync.

- [x] **Use typed `DeviceInfo` in `_device_info()`** — `sensor.py`'s `_device_info()` returns a plain `dict`. Use `homeassistant.helpers.device_registry.DeviceInfo(...)` for type safety and HA static-analysis validation.

- [x] **Improve `_rsa_encode_pwd` exception handling** — the bare `except Exception` logs and returns `""`, causing a generic `UpdateFailed` in the caller. Re-raise as `UpdateFailed` with exception chaining (`from err`) so the root cause is visible in logs.

- [x] **Document mixed `int`/`str` in `act_map`** — `async_fast_charge_discharge` uses `int` for start modes (`2`, `3`) but `str` for stop modes (`"-2"`, `"-3"`). Add a comment explaining this is intentional per the API contract.
