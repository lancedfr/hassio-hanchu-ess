"""Live integration test — authenticate then fetch energy statistics."""

from __future__ import annotations

import json
import os
import sys
import unittest
from datetime import datetime
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
class TestEnergyStatisticsLive(unittest.IsolatedAsyncioTestCase):
    """Authenticate against the real API, then pull yearly energy statistics."""

    async def test_fetch_energy_statistics(self) -> None:
        from custom_components.hanchu_ess.const import (  # noqa: PLC0415
            AES_IV,
            AES_SECRET_KEY,
            AUTH_URL,
            DATA_URL,
        )
        from custom_components.hanchu_ess.coordinator import (  # noqa: PLC0415
            _encrypt_payload,
            _rsa_encode_pwd,
        )

        # On Windows aiohttp's default aiodns resolver cannot reach DNS servers;
        # ThreadedResolver delegates to socket.getaddrinfo which uses the OS stack.
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

            # ── Step 2: fetch energy statistics ───────────────────────────
            data_body = _encrypt_payload(
                {
                    "sn": _CONF_SN,
                    "devType": "2",
                    "maxCount": 1440,
                    "dateStr": "0",
                    "masterSum": True,
                },
                AES_SECRET_KEY,
                AES_IV,
            )

            async with session.post(
                DATA_URL,
                data=data_body,
                headers={**_HEADERS, "Access-Token": token},
            ) as resp:
                raw = await resp.text()
                self.assertLess(resp.status, 500, f"Data server error: {raw[:200]}")
                data_payload: dict = json.loads(raw)

        self.assertIn(
            data_payload.get("code"),
            (200, 20001),
            f"Data request failed: {data_payload}",
        )

        records: list[dict] = data_payload.get("data") or []
        self.assertTrue(records, "Response contained no records")

        # ── Step 3: assert current-year record exists and has expected fields ──
        current_year = str(datetime.now().year)
        year_record = next((r for r in records if r.get("date") == current_year), None)
        self.assertIsNotNone(
            year_record,
            f"No record for {current_year} in response. Years present: "
            f"{[r.get('date') for r in records]}",
        )

        for field in ("loadEe", "pvDge", "batTdChg", "batTdDschg", "gridTdEe", "gridTdFe"):
            self.assertIn(field, year_record, f"Missing field '{field}' in year record")
            self.assertIsInstance(
                year_record[field], (int, float),
                f"Field '{field}' is not numeric: {year_record[field]!r}",
            )

        print(f"\n  Year: {current_year}")
        print(f"  Load            (loadEe):     {year_record['loadEe']} kWh")
        print(f"  Generation      (pvDge):       {year_record['pvDge']} kWh")
        print(f"  Charge          (batTdChg):    {year_record['batTdChg']} kWh")
        print(f"  Discharge       (batTdDschg):  {year_record['batTdDschg']} kWh")
        print(f"  From Grid       (gridTdEe):    {year_record['gridTdEe']} kWh")
        print(f"  To Grid         (gridTdFe):    {year_record['gridTdFe']} kWh")
        print(f"\n  Full record: {json.dumps(year_record, indent=4)}")


if __name__ == "__main__":
    unittest.main()
