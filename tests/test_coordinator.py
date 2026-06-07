"""Unit tests for HanchuAuthCoordinator and HanchuDataCoordinator."""

from __future__ import annotations

import base64
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_coordinator(account: str = "user@example.com", password: str = "s3cr3t"):
    """Return a HanchuAuthCoordinator with HA internals stubbed out."""
    from custom_components.hanchu_ess.coordinator import HanchuAuthCoordinator

    hass = MagicMock()
    entry = MagicMock()
    entry.data = {"account": account, "pwd": password}

    def _stub_super(self, hass, logger, *, name, update_interval):
        self.hass = hass

    with patch(
        "homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__",
        _stub_super,
    ):
        coord = HanchuAuthCoordinator(hass, entry)

    return coord


def _make_session(status: int = 200, payload: dict | None = None):
    """Return a mock aiohttp session whose post() yields *payload* as JSON."""
    if payload is None:
        payload = {"code": 200, "data": "fake.jwt.token"}

    response = AsyncMock()
    response.status = status
    response.raise_for_status = MagicMock()
    response.json = AsyncMock(return_value=payload)

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=response)
    cm.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.post = MagicMock(return_value=cm)
    return session, response


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAsyncUpdateData(unittest.IsolatedAsyncioTestCase):

    # ── happy path ────────────────────────────────────────────────────────

    async def test_success_returns_token_dict(self) -> None:
        """code=200 → returns {"token": "<jwt>"}; DataUpdateCoordinator caches it."""
        coord = _make_coordinator()
        session, _ = _make_session(payload={"code": 200, "data": "a.b.c"})

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            result = await coord._async_update_data()

        self.assertEqual(result, {"token": "a.b.c"})
        # Simulate what DataUpdateCoordinator.async_refresh() does, then check property.
        coord.data = result
        self.assertEqual(coord.access_token, "a.b.c")

    async def test_success_with_code_20001(self) -> None:
        """code=20001 is also accepted as a success code."""
        coord = _make_coordinator()
        session, _ = _make_session(payload={"code": 20001, "data": "tok"})

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            result = await coord._async_update_data()

        self.assertEqual(result["token"], "tok")

    # ── request shape ─────────────────────────────────────────────────────

    async def test_request_url(self) -> None:
        """POST must target the gateway login endpoint."""
        from custom_components.hanchu_ess.const import AUTH_URL

        coord = _make_coordinator()
        session, _ = _make_session()

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            await coord._async_update_data()

        url = session.post.call_args.args[0]
        self.assertEqual(url, AUTH_URL)

    async def test_request_headers(self) -> None:
        """POST must carry the Content-Type and gateway-required headers."""
        coord = _make_coordinator()
        session, _ = _make_session()

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            await coord._async_update_data()

        headers = session.post.call_args.kwargs["headers"]
        self.assertEqual(headers["Content-Type"], "text/plain")
        self.assertEqual(headers["version"], "1.0")
        self.assertEqual(headers["appPlat"], "iess")
        self.assertIn("locale", headers)
        self.assertIn("Access-Token", headers)

    async def test_request_body_decrypts_to_correct_credentials(self) -> None:
        """Body must be AES-CBC Base64 that decrypts to {account, pwd (RSA)}."""
        from cryptography.hazmat.primitives import padding as sym_padding
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

        from custom_components.hanchu_ess.const import AES_IV, AES_SECRET_KEY

        coord = _make_coordinator(account="user@example.com", password="s3cr3t")
        session, _ = _make_session()

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            await coord._async_update_data()

        encrypted_b64: str = session.post.call_args.kwargs["data"]
        ciphertext = base64.b64decode(encrypted_b64)

        cipher = Cipher(algorithms.AES(AES_SECRET_KEY), modes.CBC(AES_IV))
        dec = cipher.decryptor()
        padded = dec.update(ciphertext) + dec.finalize()
        unpadder = sym_padding.PKCS7(128).unpadder()
        plain = unpadder.update(padded) + unpadder.finalize()
        body = json.loads(plain.decode("utf-8"))

        self.assertEqual(body["account"], "user@example.com")
        # pwd must be a non-empty Base64 RSA ciphertext (128 bytes → 172-char B64)
        self.assertIsInstance(body["pwd"], str)
        self.assertEqual(len(base64.b64decode(body["pwd"])), 128)

    # ── error paths ───────────────────────────────────────────────────────

    async def test_api_error_code_raises_auth_failed(self) -> None:
        """A non-success API code must raise ConfigEntryAuthFailed."""
        from homeassistant.exceptions import ConfigEntryAuthFailed

        coord = _make_coordinator()
        session, _ = _make_session(payload={"code": 400, "msg": "wrong password"})

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            with self.assertRaises(ConfigEntryAuthFailed):
                await coord._async_update_data()

    async def test_empty_token_raises_update_failed(self) -> None:
        """code=200 with empty data string must raise UpdateFailed."""
        from homeassistant.helpers.update_coordinator import UpdateFailed

        coord = _make_coordinator()
        session, _ = _make_session(payload={"code": 200, "data": ""})

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            with self.assertRaises(UpdateFailed):
                await coord._async_update_data()

    async def test_http_401_raises_auth_failed(self) -> None:
        """HTTP 401 must raise ConfigEntryAuthFailed immediately."""
        from homeassistant.exceptions import ConfigEntryAuthFailed

        coord = _make_coordinator()
        session, _ = _make_session(status=401, payload={})

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            with self.assertRaises(ConfigEntryAuthFailed):
                await coord._async_update_data()

    async def test_network_error_raises_update_failed(self) -> None:
        """A transport-level error must be wrapped in UpdateFailed."""
        import aiohttp
        from homeassistant.helpers.update_coordinator import UpdateFailed

        coord = _make_coordinator()
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(side_effect=aiohttp.ClientConnectionError("unreachable"))
        cm.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.post = MagicMock(return_value=cm)

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            with self.assertRaises(UpdateFailed):
                await coord._async_update_data()


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# Helpers for HanchuDataCoordinator
# ---------------------------------------------------------------------------

def _make_data_coordinator(token: str | None = "test.jwt.token", sn: str = "TEST_SN"):
    """Return a HanchuDataCoordinator with HA internals and auth stubbed out."""
    from custom_components.hanchu_ess.coordinator import HanchuDataCoordinator

    hass = MagicMock()
    entry = MagicMock()
    entry.data = {"sn": sn}

    auth = MagicMock()
    auth.access_token = token

    def _stub_super(self, hass, logger, *, name, update_interval):
        self.hass = hass
        self.data = None

    with patch(
        "homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__",
        _stub_super,
    ):
        coord = HanchuDataCoordinator(hass, entry, auth)

    return coord


def _year_record(year: int, **overrides) -> dict:
    """Return a plausible yearly energy record for *year* (date is a string)."""
    base = {
        "date":       str(year),
        "loadEe":     1000.0,
        "pvDge":      800.0,
        "batTdChg":   200.0,
        "batTdDschg": 180.0,
        "gridTdEe":   300.0,
        "gridTdFe":   100.0,
    }
    base.update(overrides)
    return base


def _data_session(status: int = 200, payload: dict | None = None):
    """Thin wrapper around _make_session for data-endpoint responses."""
    return _make_session(status=status, payload=payload)


# ---------------------------------------------------------------------------
# Tests for HanchuDataCoordinator
# ---------------------------------------------------------------------------

class TestHanchuDataCoordinator(unittest.IsolatedAsyncioTestCase):

    # ── happy path ────────────────────────────────────────────────────────

    async def test_returns_current_year_values(self) -> None:
        """Returns the 6 energy fields extracted from the current year's record."""
        from datetime import datetime

        current_year = datetime.now().year
        records = [
            _year_record(current_year - 1, loadEe=500.0),
            _year_record(current_year),
            _year_record(current_year + 1, loadEe=9999.0),  # future, ignored
        ]
        coord = _make_data_coordinator()
        session, _ = _data_session(payload={"code": 200, "data": records})

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            result = await coord._async_update_data()

        self.assertEqual(result["load"],       1000.0)
        self.assertEqual(result["generation"], 800.0)
        self.assertEqual(result["charge"],     200.0)
        self.assertEqual(result["discharge"],  180.0)
        self.assertEqual(result["from_grid"],  300.0)
        self.assertEqual(result["to_grid"],    100.0)

    async def test_success_with_code_20001(self) -> None:
        """code=20001 is also a valid success code."""
        from datetime import datetime

        records = [_year_record(datetime.now().year)]
        coord = _make_data_coordinator()
        session, _ = _data_session(payload={"code": 20001, "data": records})

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            result = await coord._async_update_data()

        self.assertIn("load", result)

    async def test_null_fields_default_to_zero(self) -> None:
        """Missing or null energy fields must default to 0.0, not raise."""
        from datetime import datetime

        records = [_year_record(datetime.now().year, loadEe=None, pvDge=None)]
        coord = _make_data_coordinator()
        session, _ = _data_session(payload={"code": 200, "data": records})

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            result = await coord._async_update_data()

        self.assertEqual(result["load"], 0.0)
        self.assertEqual(result["generation"], 0.0)

    # ── request shape ─────────────────────────────────────────────────────

    async def test_request_targets_data_url(self) -> None:
        """POST must target the energy statistics endpoint, not the auth URL."""
        from datetime import datetime

        from custom_components.hanchu_ess.const import DATA_URL

        coord = _make_data_coordinator()
        session, _ = _data_session(payload={"code": 200, "data": [_year_record(datetime.now().year)]})

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            await coord._async_update_data()

        self.assertEqual(session.post.call_args.args[0], DATA_URL)

    async def test_access_token_sent_in_header(self) -> None:
        """The auth token must appear in the Access-Token header."""
        from datetime import datetime

        coord = _make_data_coordinator(token="my.secret.token")
        session, _ = _data_session(payload={"code": 200, "data": [_year_record(datetime.now().year)]})

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            await coord._async_update_data()

        headers = session.post.call_args.kwargs["headers"]
        self.assertEqual(headers["Access-Token"], "my.secret.token")
        self.assertEqual(headers["Content-Type"], "text/plain")
        self.assertEqual(headers["version"], "1.0")
        self.assertEqual(headers["appPlat"], "iess")

    async def test_request_body_contains_sn(self) -> None:
        """Decrypted request body must include the configured serial number."""
        from datetime import datetime

        from cryptography.hazmat.primitives import padding as sym_padding
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

        from custom_components.hanchu_ess.const import AES_IV, AES_SECRET_KEY

        coord = _make_data_coordinator(sn="TEST_SN")
        session, _ = _data_session(payload={"code": 200, "data": [_year_record(datetime.now().year)]})

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            await coord._async_update_data()

        encrypted_b64: str = session.post.call_args.kwargs["data"]
        ciphertext = base64.b64decode(encrypted_b64)
        cipher = Cipher(algorithms.AES(AES_SECRET_KEY), modes.CBC(AES_IV))
        dec = cipher.decryptor()
        padded = dec.update(ciphertext) + dec.finalize()
        unpadder = sym_padding.PKCS7(128).unpadder()
        body = json.loads(unpadder.update(padded) + unpadder.finalize())

        self.assertEqual(body["sn"], "TEST_SN")
        self.assertEqual(body["devType"], "2")
        self.assertEqual(body["maxCount"], 1440)
        self.assertTrue(body["masterSum"])

    # ── error paths ───────────────────────────────────────────────────────

    async def test_no_token_raises_update_failed(self) -> None:
        """Raises UpdateFailed immediately when there is no auth token."""
        from homeassistant.helpers.update_coordinator import UpdateFailed

        coord = _make_data_coordinator(token=None)
        with self.assertRaises(UpdateFailed):
            await coord._async_update_data()

    async def test_api_error_code_raises_update_failed(self) -> None:
        """A non-success API code raises UpdateFailed (not ConfigEntryAuthFailed)."""
        from homeassistant.helpers.update_coordinator import UpdateFailed

        coord = _make_data_coordinator()
        session, _ = _data_session(payload={"code": 500, "msg": "server error"})

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            with self.assertRaises(UpdateFailed):
                await coord._async_update_data()

    async def test_http_401_raises_auth_failed(self) -> None:
        """HTTP 401 raises ConfigEntryAuthFailed so HA triggers re-auth."""
        from homeassistant.exceptions import ConfigEntryAuthFailed

        coord = _make_data_coordinator()
        session, _ = _data_session(status=401, payload={})

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            with self.assertRaises(ConfigEntryAuthFailed):
                await coord._async_update_data()

    async def test_missing_current_year_raises_update_failed(self) -> None:
        """Raises UpdateFailed when no record matches the current year."""
        from homeassistant.helpers.update_coordinator import UpdateFailed

        coord = _make_data_coordinator()
        session, _ = _data_session(payload={"code": 200, "data": [_year_record(1999)]})

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            with self.assertRaises(UpdateFailed):
                await coord._async_update_data()

    async def test_network_error_raises_update_failed(self) -> None:
        """A transport-level error is wrapped in UpdateFailed."""
        import aiohttp
        from homeassistant.helpers.update_coordinator import UpdateFailed

        coord = _make_data_coordinator()
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(side_effect=aiohttp.ClientConnectionError("timeout"))
        cm.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.post = MagicMock(return_value=cm)

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            with self.assertRaises(UpdateFailed):
                await coord._async_update_data()


# ---------------------------------------------------------------------------
# Helpers for HanchuPowerCoordinator
# ---------------------------------------------------------------------------

def _make_power_coordinator(token: str | None = "test.jwt.token", sn: str = "TEST_SN"):
    """Return a HanchuPowerCoordinator with HA internals and auth stubbed out."""
    from custom_components.hanchu_ess.coordinator import HanchuPowerCoordinator

    hass = MagicMock()
    entry = MagicMock()
    entry.data = {"sn": sn}

    auth = MagicMock()
    auth.access_token = token

    def _stub_super(self, hass, logger, *, name, update_interval):
        self.hass = hass
        self.data = None

    with patch(
        "homeassistant.helpers.update_coordinator.DataUpdateCoordinator.__init__",
        _stub_super,
    ):
        coord = HanchuPowerCoordinator(hass, entry, auth)

    return coord


def _power_payload(
    bat_soc: str = "0.740",
    pv_tt_pwr: float = 3200.0,
    load_pwr: float = 1500.0,
    pwr_grid_sum: float = 800.0,
    bat_p: float = -900.0,
) -> dict:
    """Return a plausible powerChart API response with all live-power fields."""
    return {
        "code": 200,
        "data": {
            "batSoc": bat_soc,
            "sn": "H01XE244K0139",
            "pvTtPwr": pv_tt_pwr,
            "loadPwr": load_pwr,
            "pwrGridSum": pwr_grid_sum,
            "batP": bat_p,
        },
    }


def _power_session(status: int = 200, payload: dict | None = None):
    """Thin wrapper around _make_session for power-endpoint responses."""
    return _make_session(status=status, payload=payload if payload is not None else _power_payload())


# ---------------------------------------------------------------------------
# Tests for HanchuPowerCoordinator
# ---------------------------------------------------------------------------

class TestHanchuPowerCoordinator(unittest.IsolatedAsyncioTestCase):

    # ── happy path ────────────────────────────────────────────────────────

    async def test_returns_battery_soc_as_percentage(self) -> None:
        """batSoc string '0.740' must be returned as battery_soc=74.0."""
        coord = _make_power_coordinator()
        session, _ = _power_session(payload=_power_payload("0.740"))

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            result = await coord._async_update_data()

        self.assertEqual(result["battery_soc"], 74.0)

    async def test_soc_rounding(self) -> None:
        """batSoc '0.8333' must round to one decimal place → 83.3."""
        coord = _make_power_coordinator()
        session, _ = _power_session(payload=_power_payload("0.8333"))

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            result = await coord._async_update_data()

        self.assertAlmostEqual(result["battery_soc"], 83.3, places=1)

    async def test_full_charge_returns_100(self) -> None:
        """batSoc '1.0' must return battery_soc=100.0."""
        coord = _make_power_coordinator()
        session, _ = _power_session(payload=_power_payload("1.0"))

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            result = await coord._async_update_data()

        self.assertEqual(result["battery_soc"], 100.0)

    async def test_success_with_code_20001(self) -> None:
        """code=20001 is also a valid success code."""
        coord = _make_power_coordinator()
        payload = {"code": 20001, "data": {"batSoc": "0.5"}}
        session, _ = _power_session(payload=payload)

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            result = await coord._async_update_data()

        self.assertEqual(result["battery_soc"], 50.0)

    # ── request shape ─────────────────────────────────────────────────────

    async def test_request_targets_power_url(self) -> None:
        """POST must target the powerChart endpoint."""
        from custom_components.hanchu_ess.const import POWER_URL

        coord = _make_power_coordinator()
        session, _ = _power_session()

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            await coord._async_update_data()

        self.assertEqual(session.post.call_args.args[0], POWER_URL)

    async def test_access_token_sent_in_header(self) -> None:
        """The auth token must appear in the Access-Token header."""
        coord = _make_power_coordinator(token="power.secret.token")
        session, _ = _power_session()

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            await coord._async_update_data()

        headers = session.post.call_args.kwargs["headers"]
        self.assertEqual(headers["Access-Token"], "power.secret.token")
        self.assertEqual(headers["Content-Type"], "text/plain")
        self.assertEqual(headers["version"], "1.0")
        self.assertEqual(headers["appPlat"], "iess")

    async def test_request_body_contains_sn(self) -> None:
        """Decrypted request body must be {"sn": <configured serial number>}."""
        from cryptography.hazmat.primitives import padding as sym_padding
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

        from custom_components.hanchu_ess.const import AES_IV, AES_SECRET_KEY

        coord = _make_power_coordinator(sn="TEST_SN")
        session, _ = _power_session()

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            await coord._async_update_data()

        encrypted_b64: str = session.post.call_args.kwargs["data"]
        ciphertext = base64.b64decode(encrypted_b64)
        cipher = Cipher(algorithms.AES(AES_SECRET_KEY), modes.CBC(AES_IV))
        dec = cipher.decryptor()
        padded = dec.update(ciphertext) + dec.finalize()
        unpadder = sym_padding.PKCS7(128).unpadder()
        body = json.loads(unpadder.update(padded) + unpadder.finalize())

        self.assertEqual(body["sn"], "TEST_SN")
        self.assertEqual(list(body.keys()), ["sn"])

    # ── error paths ───────────────────────────────────────────────────────

    async def test_no_token_raises_update_failed(self) -> None:
        """Raises UpdateFailed immediately when there is no auth token."""
        from homeassistant.helpers.update_coordinator import UpdateFailed

        coord = _make_power_coordinator(token=None)
        with self.assertRaises(UpdateFailed):
            await coord._async_update_data()

    async def test_missing_bat_soc_raises_update_failed(self) -> None:
        """Raises UpdateFailed when batSoc is absent from the response."""
        from homeassistant.helpers.update_coordinator import UpdateFailed

        coord = _make_power_coordinator()
        payload = {"code": 200, "data": {"sn": "H01XE244K0139"}}
        session, _ = _power_session(payload=payload)

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            with self.assertRaises(UpdateFailed):
                await coord._async_update_data()

    async def test_api_error_code_raises_update_failed(self) -> None:
        """A non-success API code raises UpdateFailed."""
        from homeassistant.helpers.update_coordinator import UpdateFailed

        coord = _make_power_coordinator()
        session, _ = _power_session(payload={"code": 500, "msg": "server error"})

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            with self.assertRaises(UpdateFailed):
                await coord._async_update_data()

    async def test_http_401_raises_auth_failed(self) -> None:
        """HTTP 401 raises ConfigEntryAuthFailed so HA triggers re-auth."""
        from homeassistant.exceptions import ConfigEntryAuthFailed

        coord = _make_power_coordinator()
        session, _ = _power_session(status=401, payload={})

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            with self.assertRaises(ConfigEntryAuthFailed):
                await coord._async_update_data()

    async def test_network_error_raises_update_failed(self) -> None:
        """A transport-level error is wrapped in UpdateFailed."""
        import aiohttp
        from homeassistant.helpers.update_coordinator import UpdateFailed

        coord = _make_power_coordinator()
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(side_effect=aiohttp.ClientConnectionError("refused"))
        cm.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.post = MagicMock(return_value=cm)

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            with self.assertRaises(UpdateFailed):
                await coord._async_update_data()


# ---------------------------------------------------------------------------
# Tests for new live-power fields in HanchuPowerCoordinator
# ---------------------------------------------------------------------------

class TestHanchuPowerCoordinatorLivePowerFields(unittest.IsolatedAsyncioTestCase):

    async def _fetch(self, payload: dict) -> dict:
        coord = _make_power_coordinator()
        session, _ = _make_session(payload=payload)
        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            return await coord._async_update_data()

    # ── solar ────────────────────────────────────────────────────────────

    async def test_solar_power(self) -> None:
        """pvTtPwr is exposed as solar_power."""
        result = await self._fetch(_power_payload(pv_tt_pwr=3200.0))
        self.assertEqual(result["solar_power"], 3200.0)

    async def test_solar_power_defaults_to_zero_when_absent(self) -> None:
        result = await self._fetch({"code": 200, "data": {"batSoc": "0.5"}})
        self.assertEqual(result["solar_power"], 0.0)

    # ── load ─────────────────────────────────────────────────────────────

    async def test_load_power(self) -> None:
        """loadPwr is exposed as load_power."""
        result = await self._fetch(_power_payload(load_pwr=1500.0))
        self.assertEqual(result["load_power"], 1500.0)

    # ── grid ─────────────────────────────────────────────────────────────

    async def test_grid_import_when_positive(self) -> None:
        """Positive pwrGridSum → grid_import_power = value, grid_export_power = 0."""
        result = await self._fetch(_power_payload(pwr_grid_sum=800.0))
        self.assertEqual(result["grid_import_power"], 800.0)
        self.assertEqual(result["grid_export_power"], 0.0)

    async def test_grid_export_when_negative(self) -> None:
        """Negative pwrGridSum → grid_export_power = abs(value), grid_import_power = 0."""
        result = await self._fetch(_power_payload(pwr_grid_sum=-500.0))
        self.assertEqual(result["grid_import_power"], 0.0)
        self.assertEqual(result["grid_export_power"], 500.0)

    async def test_grid_zero(self) -> None:
        result = await self._fetch(_power_payload(pwr_grid_sum=0.0))
        self.assertEqual(result["grid_import_power"], 0.0)
        self.assertEqual(result["grid_export_power"], 0.0)

    # ── battery power ─────────────────────────────────────────────────────

    async def test_battery_charging(self) -> None:
        """Positive batP → charging; charge=value, discharge=0, battery_power=-value."""
        result = await self._fetch(_power_payload(bat_p=1000.0))
        self.assertEqual(result["battery_charge_power"], 1000.0)
        self.assertEqual(result["battery_discharge_power"], 0.0)
        self.assertEqual(result["battery_power"], -1000.0)

    async def test_battery_discharging(self) -> None:
        """Negative batP → discharging; discharge=abs(value), charge=0, battery_power=abs(value)."""
        result = await self._fetch(_power_payload(bat_p=-900.0))
        self.assertEqual(result["battery_charge_power"], 0.0)
        self.assertEqual(result["battery_discharge_power"], 900.0)
        self.assertEqual(result["battery_power"], 900.0)

    async def test_battery_idle(self) -> None:
        result = await self._fetch(_power_payload(bat_p=0.0))
        self.assertEqual(result["battery_charge_power"], 0.0)
        self.assertEqual(result["battery_discharge_power"], 0.0)
        self.assertEqual(result["battery_power"], 0.0)


if __name__ == "__main__":
    unittest.main()