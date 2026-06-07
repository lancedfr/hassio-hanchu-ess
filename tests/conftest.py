"""Shared fixtures for Hanchu integration tests.

Unit tests (test_scaffold, test_coordinator, etc.) work on any platform.
Fixtures that rely on pytest-homeassistant-custom-component are only active
when that package is installed (Linux/WSL/CI).  Install with:
    pip install -e ".[dev,integration]"
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

try:
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    _HA_TEST_FRAMEWORK = True
except ImportError:
    _HA_TEST_FRAMEWORK = False

from custom_components.hanchu_ess.const import DOMAIN


@pytest.fixture
def mock_config_entry():
    """Return a mock config entry for hanchu (requires HA test framework)."""
    if not _HA_TEST_FRAMEWORK:
        pytest.skip("pytest-homeassistant-custom-component not installed (Linux/WSL only)")
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            "account": "test@example.com",
            "password": "test_password",
            "sn": "TEST_SN_001",
            "name": "Hanchu",
        },
        entry_id="test_entry_id",
    )


@pytest.fixture
def mock_auth_token() -> str:
    return "mock_bearer_token"


@pytest.fixture
def mock_coordinators(mock_auth_token):
    """Patch all four API coordinators so no live network calls are made."""
    with (
        patch(
            "custom_components.hanchu_ess.coordinator.HanchuAuthCoordinator._async_update_data",
            new_callable=AsyncMock,
            return_value=mock_auth_token,
        ),
        patch(
            "custom_components.hanchu_ess.coordinator.HanchuDataCoordinator._async_update_data",
            new_callable=AsyncMock,
            return_value={},
        ),
        patch(
            "custom_components.hanchu_ess.coordinator.HanchuPowerCoordinator._async_update_data",
            new_callable=AsyncMock,
            return_value={},
        ),
        patch(
            "custom_components.hanchu_ess.coordinator.HanchuSettingsCoordinator._async_update_data",
            new_callable=AsyncMock,
            return_value={},
        ),
    ):
        yield
