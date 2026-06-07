"""Live integration test — authenticate then send fast charge / discharge commands."""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

import aiohttp

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_HEADERS = {
    "Content-Type": "text/plain",
    "Share-Link-Key": "",
    "locale": "en",
    "version": "1.0",
    "appPlat": "iess",
}

_CONF_ACCOUNT = os.environ.get("HANCHU_TEST_ACCOUNT", "")
_CONF_PWD = os.environ.get("HANCHU_TEST_PWD", "")
_CONF_SN = os.environ.get("HANCHU_TEST_SN", "")

_SKIP_REASON = "Set HANCHU_TEST_ACCOUNT, HANCHU_TEST_PWD, HANCHU_TEST_SN to run live tests"


@unittest.skipUnless(_CONF_ACCOUNT and _CONF_PWD and _CONF_SN, _SKIP_REASON)
class TestFastChargeLive(unittest.IsolatedAsyncioTestCase):
    """Authenticate against the real API, then send a 1-minute fast charge and immediately stop it."""

    async def test_fast_charge_then_stop(self) -> None:
        from custom_components.hanchu_ess.const import (
            AES_IV,
            AES_SECRET_KEY,
            AUTH_URL,
            FAST_CHARGE_DISCHARGE_URL,
        )
        from custom_components.hanchu_ess.coordinator import _encrypt_payload, _rsa_encode_pwd

        connector = aiohttp.TCPConnector(resolver=aiohttp.resolver.ThreadedResolver())
        timeout = aiohttp.ClientTimeout(total=30)

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:

            # ── Step 1: authenticate ──────────────────────────────────────
            pwd_rsa = _rsa_encode_pwd(_CONF_PWD)
            self.assertTrue(pwd_rsa, "RSA encryption returned empty string")

            auth_body = _encrypt_payload(
                {"account": _CONF_ACCOUNT, "pwd": pwd_rsa},
                AES_SECRET_KEY,
                AES_IV,
            )

            async with session.post(
                AUTH_URL,
                data=auth_body,
                headers={**_HEADERS, "Access-Token": ""},
            ) as resp:
                raw = await resp.text()
                self.assertLess(resp.status, 500, f"Auth server error: {raw[:200]}")
                auth_payload: dict = json.loads(raw)

            self.assertIn(
                auth_payload.get("code"),
                (200, 20001),
                f"Login failed: {auth_payload}",
            )
            token: str = auth_payload["data"]
            self.assertTrue(token, "Auth returned empty token")

            # ── Step 2: start fast charge for 1 minute ────────────────────
            start_body = _encrypt_payload(
                {"sn": _CONF_SN, "act": 2, "duration": 60},
                AES_SECRET_KEY,
                AES_IV,
            )

            async with session.post(
                FAST_CHARGE_DISCHARGE_URL,
                data=start_body,
                headers={**_HEADERS, "Access-Token": token},
            ) as resp:
                raw = await resp.text()
                self.assertLess(resp.status, 500, f"Fast charge start server error: {raw[:200]}")
                start_result: dict = json.loads(raw)

            print(f"\n  Fast charge start response: {json.dumps(start_result, indent=4)}")
            self.assertIn(
                start_result.get("code"),
                (200, 20001),
                f"Fast charge start failed: {start_result}",
            )

            # ── Step 3: stop fast charge ──────────────────────────────────
            stop_body = _encrypt_payload(
                {"sn": _CONF_SN, "act": "-2"},
                AES_SECRET_KEY,
                AES_IV,
            )

            async with session.post(
                FAST_CHARGE_DISCHARGE_URL,
                data=stop_body,
                headers={**_HEADERS, "Access-Token": token},
            ) as resp:
                raw = await resp.text()
                self.assertLess(resp.status, 500, f"Fast charge stop server error: {raw[:200]}")
                stop_result: dict = json.loads(raw)

            print(f"\n  Fast charge stop response: {json.dumps(stop_result, indent=4)}")
            self.assertIn(
                stop_result.get("code"),
                (200, 20001),
                f"Fast charge stop failed: {stop_result}",
            )


if __name__ == "__main__":
    unittest.main()