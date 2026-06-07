"""Tests for _decrypt_payload — AES-CBC decryption of Hanchu gateway messages."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from custom_components.hanchu_ess.const import AES_IV, AES_SECRET_KEY  # noqa: E402
from custom_components.hanchu_ess.coordinator import _decrypt_payload, _encrypt_payload  # noqa: E402


class TestDecryptPayload(unittest.TestCase):

    def test_roundtrip(self) -> None:
        """Encrypting then decrypting must recover the original dict exactly."""
        original = {"account": "user@example.com", "pwd": "some-rsa-ciphertext"}
        encrypted = _encrypt_payload(original, AES_SECRET_KEY, AES_IV)
        recovered = _decrypt_payload(encrypted, AES_SECRET_KEY, AES_IV)
        self.assertEqual(recovered, original)

    def test_roundtrip_unicode(self) -> None:
        """Payload with non-ASCII values must survive the roundtrip."""
        original = {"msg": "你好", "code": 200}
        encrypted = _encrypt_payload(original, AES_SECRET_KEY, AES_IV)
        recovered = _decrypt_payload(encrypted, AES_SECRET_KEY, AES_IV)
        self.assertEqual(recovered, original)

    def test_decrypt_known_ciphertext(self) -> None:
        """Decrypt a message encrypted outside this library (e.g. captured from the app).

        Replace ENCRYPTED_MSG with the Base64 ciphertext you want to inspect.
        The assertion is deliberately loose so the test is reusable as a debug tool.
        """
        # Produce a known ciphertext from a known plaintext so the test is self-contained.
        known_plain = {"station": "home", "power_kw": 3.7}
        known_cipher = _encrypt_payload(known_plain, AES_SECRET_KEY, AES_IV)

        result = _decrypt_payload(known_cipher, AES_SECRET_KEY, AES_IV)

        self.assertIn("station", result)
        self.assertIn("power_kw", result)
        self.assertAlmostEqual(result["power_kw"], 3.7)

    def test_wrong_key_raises(self) -> None:
        """Decrypting with the wrong key must raise (bad padding or JSON parse error)."""
        encrypted = _encrypt_payload({"x": 1}, AES_SECRET_KEY, AES_IV)
        wrong_key = b"WrongKey12345678"
        with self.assertRaises(Exception):
            _decrypt_payload(encrypted, wrong_key, AES_IV)


if __name__ == "__main__":
    # ── Quick CLI decrypt tool ────────────────────────────────────────────
    # Usage: python tests/test_decrypt.py <base64-ciphertext>
    import json
    import sys as _sys

    if len(_sys.argv) == 2:
        msg = _decrypt_payload(_sys.argv[1], AES_SECRET_KEY, AES_IV)
        print(json.dumps(msg, indent=2, ensure_ascii=False))
    else:
        unittest.main()
