"""Unit tests for Hanchu button entities."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _make_coordinator(data: dict | None = None):
    """Return a minimal HanchuSettingsCoordinator stub."""
    coord = MagicMock()
    coord.data = data
    coord.async_refresh = AsyncMock()
    coord.async_set_settings = AsyncMock()
    coord.async_write_pending = AsyncMock()
    return coord


def _make_entry(entry_id: str = "test_entry_id", sn: str = "TEST_SN", name: str = "Hanchu"):
    entry = MagicMock()
    entry.entry_id = entry_id
    entry.data = {"sn": sn, "name": name}
    return entry


def _make_read_button(coord=None, entry=None):
    from custom_components.hanchu_ess.button import HanchuReadSettingsButton

    if coord is None:
        coord = _make_coordinator()
    if entry is None:
        entry = _make_entry()

    with patch("custom_components.hanchu_ess.button._device_info", return_value={}):
        btn = HanchuReadSettingsButton(coord, entry)
    return btn, coord


def _make_write_button(coord=None, entry=None):
    from custom_components.hanchu_ess.button import HanchuWriteSettingsButton

    if coord is None:
        coord = _make_coordinator()
    if entry is None:
        entry = _make_entry()

    with patch("custom_components.hanchu_ess.button._device_info", return_value={}):
        btn = HanchuWriteSettingsButton(coord, entry)
    return btn, coord


class TestHanchuButtons(unittest.IsolatedAsyncioTestCase):

    async def test_read_button_calls_async_refresh(self) -> None:
        """Pressing Read Settings triggers coordinator.async_refresh."""
        btn, coord = _make_read_button()
        await btn.async_press()
        coord.async_refresh.assert_awaited_once()

    async def test_write_button_calls_async_write_pending(self) -> None:
        """Pressing Write Settings delegates to coordinator.async_write_pending."""
        btn, coord = _make_write_button()

        await btn.async_press()

        coord.async_write_pending.assert_awaited_once()

    async def test_write_button_delegates_to_async_write_pending(self) -> None:
        """Write Settings always calls async_write_pending (coordinator guards against empty pending)."""
        coord = _make_coordinator(data=None)
        btn, coord = _make_write_button(coord=coord)

        await btn.async_press()

        coord.async_write_pending.assert_awaited_once()

    def test_read_button_unique_id(self) -> None:
        """Read Settings unique_id is prefixed with entry_id."""
        btn, _ = _make_read_button(entry=_make_entry(entry_id="abc123"))
        self.assertEqual(btn._attr_unique_id, "abc123_read_settings")

    def test_write_button_unique_id(self) -> None:
        """Write Settings unique_id is prefixed with entry_id."""
        btn, _ = _make_write_button(entry=_make_entry(entry_id="abc123"))
        self.assertEqual(btn._attr_unique_id, "abc123_write_settings")


if __name__ == "__main__":
    unittest.main()
