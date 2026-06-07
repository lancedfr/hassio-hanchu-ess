"""Basic tests for scaffold integrity."""

from __future__ import annotations

import base64
import importlib
import json
import sys
import unittest
from pathlib import Path


class TestScaffold(unittest.TestCase):
    """Validate scaffold files and key metadata."""

    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]

    def test_manifest_has_rich_fields(self) -> None:
        manifest_path = self.root / "custom_components" / "hanchu_ess" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        for key in (
            "domain",
            "name",
            "version",
            "config_flow",
            "documentation",
            "issue_tracker",
            "codeowners",
            "integration_type",
            "iot_class",
            "quality_scale",
            "loggers",
            "requirements",
            "dependencies",
        ):
            self.assertIn(key, manifest)

        self.assertEqual(manifest["domain"], "hanchu")
        self.assertTrue(manifest["config_flow"])

    def test_hacs_has_optional_presentation_fields(self) -> None:
        hacs_path = self.root / "hacs.json"
        hacs = json.loads(hacs_path.read_text(encoding="utf-8"))

        for key in (
            "name",
            "domains",
            "country",
            "homeassistant",
            "render_readme",
            "filename",
            "content_in_root",
            "zip_release",
        ):
            self.assertIn(key, hacs)

        self.assertIn("hanchu", hacs["domains"])

    def test_core_files_exist(self) -> None:
        expected = [
            "custom_components/hanchu_ess/__init__.py",
            "custom_components/hanchu_ess/config_flow.py",
            "custom_components/hanchu_ess/const.py",
            "custom_components/hanchu_ess/coordinator.py",
            "custom_components/hanchu_ess/manifest.json",
            "custom_components/hanchu_ess/strings.json",
            "custom_components/hanchu_ess/translations/en.json",
        ]

        for rel_path in expected:
            path = self.root / rel_path
            self.assertTrue(path.exists(), f"Missing file: {rel_path}")


class TestAuthConstants(unittest.TestCase):
    """Validate auth-related constants and encryption helpers."""

    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]
        # Make the package importable without a full HA install.
        src = str(self.root)
        if src not in sys.path:
            sys.path.insert(0, src)

    def test_const_has_auth_fields(self) -> None:
        """Ensure const.py exports all required auth symbols."""
        const = importlib.import_module("custom_components.hanchu_ess.const")
        for attr in (
            "AUTH_URL",
            "AES_IV",
            "AES_SECRET_KEY",
            "RSA_PUBLIC_KEY_B64",
            "CONF_ACCOUNT",
            "CONF_PWD",
            "TOKEN_REFRESH_HOURS",
        ):
            self.assertTrue(hasattr(const, attr), f"const.py missing: {attr}")

        self.assertIn("hanchuess.com", const.AUTH_URL)
        self.assertEqual(len(const.AES_IV), 16, "AES_IV must be exactly 16 bytes")
        self.assertIn(
            len(const.AES_SECRET_KEY),
            (16, 24, 32),
            "AES_SECRET_KEY must be 16, 24, or 32 bytes",
        )

    def test_encrypt_payload_returns_base64(self) -> None:
        """_encrypt_payload should return a valid Base64 string."""
        from custom_components.hanchu_ess.coordinator import _encrypt_payload  # noqa: PLC0415

        key = b"TestKey123456789"  # 16 bytes
        iv = b"9z64Qr8mZH7Pg8d1"  # 16 bytes
        result = _encrypt_payload({"account": "user@example.com", "pwd": "secret"}, key, iv)

        self.assertIsInstance(result, str)
        decoded = base64.b64decode(result)
        self.assertEqual(len(decoded) % 16, 0)

    def test_rsa_encode_pwd_matches_java_shape(self) -> None:
        """RSA helper should return Base64 data for a 1024-bit PKCS#1 v1.5 encrypt."""
        from custom_components.hanchu_ess.coordinator import _rsa_encode_pwd  # noqa: PLC0415

        encoded = _rsa_encode_pwd("plain-password")
        self.assertIsInstance(encoded, str)
        self.assertNotEqual(encoded, "")

        raw = base64.b64decode(encoded)
        # Java key is 1024-bit, so RSA ciphertext is fixed at 128 bytes.
        self.assertEqual(len(raw), 128)

    def test_manifest_iot_class_is_cloud_polling(self) -> None:
        manifest_path = self.root / "custom_components" / "hanchu_ess" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["iot_class"], "cloud_polling")


if __name__ == "__main__":
    unittest.main()
