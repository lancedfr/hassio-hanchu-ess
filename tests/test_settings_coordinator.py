"""Unit tests for HanchuSettingsCoordinator."""

from __future__ import annotations

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

def _make_settings_coordinator(token: str | None = "test.jwt.token", sn: str = "TEST_SN"):
    """Return a HanchuSettingsCoordinator with HA internals and auth stubbed out."""
    from custom_components.hanchu_ess.coordinator import HanchuSettingsCoordinator

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
        coord = HanchuSettingsCoordinator(hass, entry, auth)

    return coord


def _make_session(status: int = 200, payload: dict | None = None):
    """Return a mock aiohttp session."""
    if payload is None:
        payload = {"code": 200, "data": {}}

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


def _full_settings_payload() -> dict:
    """Return a realistic iotGet response."""
    return {
        "code": 200,
        "data": {
            "WORK_MODE_CMB": "3",
            "CHG_PWR_LMT": "3700",
            "DSCHG_PWR_LMT": "500",
            "DTU_AC_CHG_SOC_LMT": "65",
            "CHG_BAT_SOC_LMT": "100.00",
            "DSCHG_BAT_SOC_LMT": "10.00",
            "OFF_GRID_SOC_L": "10.00",
            "TCT_START_1": "14400",  # 04:00
            "TCT_END_1": "19800",    # 05:30
            "TDT_START_1": "61500",  # 17:05  (approx)
            "TDT_END_1": "67500",    # 18:45
        },
    }


# ---------------------------------------------------------------------------
# Tests — _async_update_data (read)
# ---------------------------------------------------------------------------

class TestHanchuSettingsCoordinatorRead(unittest.IsolatedAsyncioTestCase):

    async def test_returns_data_dict(self) -> None:
        """code=200 → coordinator.data is the inner 'data' dict."""
        coord = _make_settings_coordinator()
        session, _ = _make_session(payload=_full_settings_payload())

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            result = await coord._async_update_data()

        self.assertEqual(result["WORK_MODE_CMB"], "3")
        self.assertEqual(result["CHG_PWR_LMT"], "3700")

    async def test_code_20001_accepted(self) -> None:
        """code=20001 is a valid success code."""
        payload = {**_full_settings_payload(), "code": 20001}
        coord = _make_settings_coordinator()
        session, _ = _make_session(payload=payload)

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            result = await coord._async_update_data()

        self.assertIn("WORK_MODE_CMB", result)

    async def test_no_token_raises_update_failed(self) -> None:
        """Raises UpdateFailed when there is no auth token."""
        from homeassistant.helpers.update_coordinator import UpdateFailed

        coord = _make_settings_coordinator(token=None)
        with self.assertRaises(UpdateFailed):
            await coord._async_update_data()

    async def test_http_401_raises_auth_failed(self) -> None:
        """HTTP 401 triggers re-auth."""
        from homeassistant.exceptions import ConfigEntryAuthFailed

        coord = _make_settings_coordinator()
        session, _ = _make_session(status=401, payload={})

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            with self.assertRaises(ConfigEntryAuthFailed):
                await coord._async_update_data()

    async def test_api_error_code_raises_update_failed(self) -> None:
        """Non-success API code raises UpdateFailed."""
        from homeassistant.helpers.update_coordinator import UpdateFailed

        coord = _make_settings_coordinator()
        session, _ = _make_session(payload={"code": 500, "msg": "error"})

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            with self.assertRaises(UpdateFailed):
                await coord._async_update_data()

    async def test_network_error_raises_update_failed(self) -> None:
        """Transport-level error is wrapped in UpdateFailed."""
        import aiohttp
        from homeassistant.helpers.update_coordinator import UpdateFailed

        coord = _make_settings_coordinator()
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(side_effect=aiohttp.ClientConnectionError("timeout"))
        cm.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.post = MagicMock(return_value=cm)

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            with self.assertRaises(UpdateFailed):
                await coord._async_update_data()

    async def test_request_targets_iot_get_url(self) -> None:
        """POST must target the iotGet endpoint."""
        from custom_components.hanchu_ess.const import IOT_GET_URL

        coord = _make_settings_coordinator()
        session, _ = _make_session(payload=_full_settings_payload())

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            await coord._async_update_data()

        self.assertEqual(session.post.call_args.args[0], IOT_GET_URL)

    async def test_access_token_in_header(self) -> None:
        """The Access-Token header must carry the auth token."""
        coord = _make_settings_coordinator(token="settings.token")
        session, _ = _make_session(payload=_full_settings_payload())

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            await coord._async_update_data()

        headers = session.post.call_args.kwargs["headers"]
        self.assertEqual(headers["Access-Token"], "settings.token")


# ---------------------------------------------------------------------------
# Tests — async_update_local (local staging)
# ---------------------------------------------------------------------------

class TestHanchuSettingsCoordinatorLocal(unittest.TestCase):

    def test_async_update_local_merges_into_data(self) -> None:
        """async_update_local merges the given values into coordinator.data and _pending."""
        coord = _make_settings_coordinator()
        coord.data = {"WORK_MODE_CMB": "1", "CHG_PWR_LMT": "3700"}
        coord.async_set_updated_data = lambda d: setattr(coord, "data", d)

        coord.async_update_local({"CHG_PWR_LMT": 5000, "DSCHG_PWR_LMT": 500})

        self.assertEqual(coord.data["WORK_MODE_CMB"], "1")
        self.assertEqual(coord.data["CHG_PWR_LMT"], 5000)
        self.assertEqual(coord.data["DSCHG_PWR_LMT"], 500)
        self.assertEqual(coord._pending["CHG_PWR_LMT"], 5000)
        self.assertEqual(coord._pending["DSCHG_PWR_LMT"], 500)

    def test_async_update_local_notifies_listeners(self) -> None:
        """async_update_local calls async_set_updated_data to notify listeners."""
        coord = _make_settings_coordinator()
        coord.data = {"WORK_MODE_CMB": "3"}
        notified = []
        coord.async_set_updated_data = lambda d: notified.append(d)

        coord.async_update_local({"WORK_MODE_CMB": 1})

        self.assertEqual(len(notified), 1)
        self.assertEqual(notified[0]["WORK_MODE_CMB"], 1)
        self.assertEqual(coord._pending["WORK_MODE_CMB"], 1)

    def test_async_update_local_tolerates_none_data(self) -> None:
        """async_update_local works when coordinator.data is None (before first read)."""
        coord = _make_settings_coordinator()
        coord.data = None
        received = []
        coord.async_set_updated_data = lambda d: received.append(d)

        coord.async_update_local({"CHG_PWR_LMT": 3000})

        self.assertEqual(received[0]["CHG_PWR_LMT"], 3000)
        self.assertEqual(coord._pending["CHG_PWR_LMT"], 3000)


# ---------------------------------------------------------------------------
# Tests — async_set_settings (write — called by Write Settings button)
# ---------------------------------------------------------------------------

class TestHanchuSettingsCoordinatorWrite(unittest.IsolatedAsyncioTestCase):

    async def test_write_success_calls_iot_set_url(self) -> None:
        """Write must POST to the iotSet endpoint."""
        from custom_components.hanchu_ess.const import IOT_SET_URL

        coord = _make_settings_coordinator()
        coord.async_refresh = AsyncMock()
        session, _ = _make_session(payload={"code": 200, "msg": "Success!", "data": {}})

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            await coord.async_set_settings({"WORK_MODE_CMB": 3})

        self.assertEqual(session.post.call_args.args[0], IOT_SET_URL)

    async def test_write_triggers_refresh(self) -> None:
        """async_set_settings calls async_refresh after a successful write."""
        coord = _make_settings_coordinator()
        refresh_mock = AsyncMock()
        coord.async_refresh = refresh_mock
        session, _ = _make_session(payload={"code": 200, "msg": "Success!", "data": {}})

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            await coord.async_set_settings({"CHG_PWR_LMT": 3000})

        refresh_mock.assert_awaited_once()

    async def test_write_no_token_raises_update_failed(self) -> None:
        """Raises UpdateFailed immediately when there is no auth token."""
        from homeassistant.helpers.update_coordinator import UpdateFailed

        coord = _make_settings_coordinator(token=None)
        with self.assertRaises(UpdateFailed):
            await coord.async_set_settings({"WORK_MODE_CMB": 1})

    async def test_write_api_error_raises_update_failed(self) -> None:
        """Non-success iotSet response raises UpdateFailed."""
        from homeassistant.helpers.update_coordinator import UpdateFailed

        coord = _make_settings_coordinator()
        coord.async_refresh = AsyncMock()
        session, _ = _make_session(payload={"code": 500, "msg": "device error"})

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            with self.assertRaises(UpdateFailed):
                await coord.async_set_settings({"WORK_MODE_CMB": 1})

    async def test_write_network_error_raises_update_failed(self) -> None:
        """Transport-level write error is wrapped in UpdateFailed."""
        import aiohttp
        from homeassistant.helpers.update_coordinator import UpdateFailed

        coord = _make_settings_coordinator()
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(side_effect=aiohttp.ClientConnectionError("refused"))
        cm.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.post = MagicMock(return_value=cm)

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            with self.assertRaises(UpdateFailed):
                await coord.async_set_settings({"CHG_PWR_LMT": 2000})


# ---------------------------------------------------------------------------
# Tests — async_write_pending and _pending lifecycle
# ---------------------------------------------------------------------------

class TestHanchuSettingsCoordinatorPending(unittest.IsolatedAsyncioTestCase):

    async def test_async_write_pending_calls_set_settings_with_pending(self) -> None:
        """async_write_pending sends only the staged keys via async_set_settings."""
        coord = _make_settings_coordinator()
        coord._pending = {"CHG_PWR_LMT": 3000}
        coord.async_set_settings = AsyncMock()

        await coord.async_write_pending()

        coord.async_set_settings.assert_awaited_once_with({"CHG_PWR_LMT": 3000})

    async def test_async_write_pending_noop_when_empty(self) -> None:
        """async_write_pending does nothing when no changes are staged."""
        coord = _make_settings_coordinator()
        coord._pending = {}
        coord.async_set_settings = AsyncMock()

        await coord.async_write_pending()

        coord.async_set_settings.assert_not_called()

    async def test_pending_cleared_after_successful_write(self) -> None:
        """async_set_settings clears _pending after a successful iotSet call."""
        coord = _make_settings_coordinator()
        coord._pending = {"CHG_PWR_LMT": 3000}
        coord.async_refresh = AsyncMock()
        session, _ = _make_session(payload={"code": 200, "msg": "Success!", "data": {}})

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            await coord.async_set_settings({"CHG_PWR_LMT": 3000})

        self.assertEqual(coord._pending, {})

    async def test_pending_cleared_after_successful_read(self) -> None:
        """_async_update_data clears _pending after a successful iotGet call."""
        coord = _make_settings_coordinator()
        coord._pending = {"CHG_PWR_LMT": 3000}
        session, _ = _make_session(payload=_full_settings_payload())

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            await coord._async_update_data()

        self.assertEqual(coord._pending, {})


# ---------------------------------------------------------------------------
# Tests — time conversion helpers
# ---------------------------------------------------------------------------

class TestTimePeriodConversion(unittest.TestCase):

    def test_seconds_to_time_04_00(self) -> None:
        import datetime

        from custom_components.hanchu_ess.time import _seconds_to_time
        self.assertEqual(_seconds_to_time(14400), datetime.time(4, 0))

    def test_seconds_to_time_05_30(self) -> None:
        import datetime

        from custom_components.hanchu_ess.time import _seconds_to_time
        self.assertEqual(_seconds_to_time(19800), datetime.time(5, 30))

    def test_seconds_to_time_midnight(self) -> None:
        import datetime

        from custom_components.hanchu_ess.time import _seconds_to_time
        self.assertEqual(_seconds_to_time(0), datetime.time(0, 0))

    def test_seconds_to_time_23_59(self) -> None:
        import datetime

        from custom_components.hanchu_ess.time import _seconds_to_time
        self.assertEqual(_seconds_to_time(86340), datetime.time(23, 59))

    def test_time_to_seconds_roundtrip(self) -> None:
        from custom_components.hanchu_ess.time import _seconds_to_time, _time_to_seconds
        for secs in [0, 14400, 19800, 61500, 86340]:
            t = _seconds_to_time(secs)
            self.assertEqual(_time_to_seconds(t), secs)

    def test_time_to_seconds_04_00(self) -> None:
        import datetime

        from custom_components.hanchu_ess.time import _time_to_seconds
        self.assertEqual(_time_to_seconds(datetime.time(4, 0)), 14400)


# ---------------------------------------------------------------------------
# Tests — async_fast_charge_discharge
# ---------------------------------------------------------------------------

class TestHanchuFastChargeDischarge(unittest.IsolatedAsyncioTestCase):

    async def test_fast_charge_posts_to_correct_url(self) -> None:
        """POST must target FAST_CHARGE_DISCHARGE_URL."""
        from custom_components.hanchu_ess.const import FAST_CHARGE_DISCHARGE_URL

        coord = _make_settings_coordinator()
        session, _ = _make_session(payload={"code": 200, "data": {}})

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            await coord.async_fast_charge_discharge("fast_charge", 15)

        self.assertEqual(session.post.call_args.args[0], FAST_CHARGE_DISCHARGE_URL)

    async def test_fast_charge_sets_act_2_and_duration_seconds(self) -> None:
        """fast_charge uses act=2 and duration in seconds."""
        from custom_components.hanchu_ess.const import AES_IV, AES_SECRET_KEY
        from custom_components.hanchu_ess.coordinator import _decrypt_payload

        coord = _make_settings_coordinator(sn="TEST_SN")
        session, _ = _make_session(payload={"code": 200, "data": {}})

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            await coord.async_fast_charge_discharge("fast_charge", 15)

        body = session.post.call_args.kwargs["data"]
        payload = _decrypt_payload(body, AES_SECRET_KEY, AES_IV)
        self.assertEqual(payload["act"], 2)
        self.assertEqual(payload["duration"], 900)  # 15 * 60
        self.assertEqual(payload["sn"], "TEST_SN")

    async def test_fast_discharge_sets_act_3(self) -> None:
        """fast_discharge uses act=3."""
        from custom_components.hanchu_ess.const import AES_IV, AES_SECRET_KEY
        from custom_components.hanchu_ess.coordinator import _decrypt_payload

        coord = _make_settings_coordinator()
        session, _ = _make_session(payload={"code": 200, "data": {}})

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            await coord.async_fast_charge_discharge("fast_discharge", 30)

        body = session.post.call_args.kwargs["data"]
        payload = _decrypt_payload(body, AES_SECRET_KEY, AES_IV)
        self.assertEqual(payload["act"], 3)
        self.assertEqual(payload["duration"], 1800)  # 30 * 60

    async def test_stop_charge_sets_act_minus2_no_duration(self) -> None:
        """stop_charge uses act='-2' and omits duration."""
        from custom_components.hanchu_ess.const import AES_IV, AES_SECRET_KEY
        from custom_components.hanchu_ess.coordinator import _decrypt_payload

        coord = _make_settings_coordinator()
        session, _ = _make_session(payload={"code": 200, "data": {}})

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            await coord.async_fast_charge_discharge("stop_charge", None)

        body = session.post.call_args.kwargs["data"]
        payload = _decrypt_payload(body, AES_SECRET_KEY, AES_IV)
        self.assertEqual(payload["act"], "-2")
        self.assertNotIn("duration", payload)

    async def test_stop_discharge_sets_act_minus3_no_duration(self) -> None:
        """stop_discharge uses act='-3' and omits duration."""
        from custom_components.hanchu_ess.const import AES_IV, AES_SECRET_KEY
        from custom_components.hanchu_ess.coordinator import _decrypt_payload

        coord = _make_settings_coordinator()
        session, _ = _make_session(payload={"code": 200, "data": {}})

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            await coord.async_fast_charge_discharge("stop_discharge", None)

        body = session.post.call_args.kwargs["data"]
        payload = _decrypt_payload(body, AES_SECRET_KEY, AES_IV)
        self.assertEqual(payload["act"], "-3")
        self.assertNotIn("duration", payload)

    async def test_no_token_raises_update_failed(self) -> None:
        """Raises UpdateFailed immediately when there is no auth token."""
        from homeassistant.helpers.update_coordinator import UpdateFailed

        coord = _make_settings_coordinator(token=None)
        with self.assertRaises(UpdateFailed):
            await coord.async_fast_charge_discharge("fast_charge", 10)

    async def test_http_401_raises_auth_failed(self) -> None:
        """HTTP 401 triggers re-auth."""
        from homeassistant.exceptions import ConfigEntryAuthFailed

        coord = _make_settings_coordinator()
        session, _ = _make_session(status=401, payload={})

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            with self.assertRaises(ConfigEntryAuthFailed):
                await coord.async_fast_charge_discharge("fast_charge", 10)

    async def test_api_error_code_raises_update_failed(self) -> None:
        """Non-success API code raises UpdateFailed."""
        from homeassistant.helpers.update_coordinator import UpdateFailed

        coord = _make_settings_coordinator()
        session, _ = _make_session(payload={"code": 500, "msg": "device error"})

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            with self.assertRaises(UpdateFailed):
                await coord.async_fast_charge_discharge("fast_charge", 10)

    async def test_network_error_raises_update_failed(self) -> None:
        """Transport-level error is wrapped in UpdateFailed."""
        import aiohttp
        from homeassistant.helpers.update_coordinator import UpdateFailed

        coord = _make_settings_coordinator()
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(side_effect=aiohttp.ClientConnectionError("refused"))
        cm.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.post = MagicMock(return_value=cm)

        with patch("custom_components.hanchu_ess.coordinator.async_get_clientsession", return_value=session):
            with self.assertRaises(UpdateFailed):
                await coord.async_fast_charge_discharge("fast_charge", 10)


if __name__ == "__main__":
    unittest.main()
