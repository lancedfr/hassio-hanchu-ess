"""Live OAuth integration test against the real Hanchu endpoint."""

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
class TestOAuthLiveEndpoint(unittest.IsolatedAsyncioTestCase):
    """Validate OAuth token fetching using the real remote API."""

    async def test_fetch_oauth_token_live(self) -> None:
        """POST encrypted credentials and assert a JWT token is returned."""
        from custom_components.hanchu_ess.const import AES_IV, AES_SECRET_KEY, AUTH_URL  # noqa: PLC0415
        from custom_components.hanchu_ess.coordinator import (  # noqa: PLC0415
            _encrypt_payload,
            _rsa_encode_pwd,
        )

        pwd_rsa = _rsa_encode_pwd(_CONF_PWD)
        self.assertTrue(pwd_rsa, "RSA-encrypted password must not be empty")

        encrypted_body = _encrypt_payload(
            {"account": _CONF_ACCOUNT, "pwd": pwd_rsa},
            AES_SECRET_KEY,
            AES_IV,
        )

        # On Windows aiohttp's default aiodns resolver cannot reach DNS servers;
        # ThreadedResolver delegates to socket.getaddrinfo which uses the OS stack.
        connector = aiohttp.TCPConnector(resolver=aiohttp.resolver.ThreadedResolver())
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            async with session.post(
                AUTH_URL,
                data=encrypted_body,
                headers={
                    **_HEADERS
                },
            ) as response:
                raw = await response.text()
                self.assertLess(response.status, 500, f"Server error {response.status}: {raw[:200]}")
                payload: dict = json.loads(raw)

        self.assertIn(
            payload.get("code"),
            (200, 20001),
            f"Login failed: code={payload.get('code')} msg={payload.get('msg')} full={payload}",
        )

        token = payload.get("data")
        self.assertTrue(token, f"Expected a token string in 'data', got: {payload}")
        self.assertIsInstance(token, str)


if __name__ == "__main__":
    unittest.main()
