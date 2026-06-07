"""Data update coordinator for Hanchu - handles OAuth token refresh."""

from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timedelta

import aiohttp
from cryptography.hazmat.primitives import padding as sym_padding
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.serialization import load_der_public_key
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    AES_IV,
    AES_SECRET_KEY,
    AUTH_URL,
    CONF_ACCOUNT,
    CONF_PWD,
    CONF_SN,
    DATA_DEV_TYPE,
    DATA_MAX_COUNT,
    DATA_POLL_MINUTES,
    DATA_URL,
    DOMAIN,
    FAST_CHARGE_DISCHARGE_URL,
    IOT_GET_URL,
    IOT_SET_URL,
    IOT_SETTINGS_KEYS,
    POWER_POLL_MINUTES,
    POWER_URL,
    RSA_PUBLIC_KEY_B64,
    TOKEN_REFRESH_HOURS,
)

_LOGGER = logging.getLogger(__name__)

_BASE_HEADERS: dict[str, str] = {
    "Content-Type": "text/plain",
    "Share-Link-Key": "",
    "locale": "en",
    "version": "1.0",
    "appPlat": "iess",
}


def _rsa_encode_pwd(pwd: str) -> str:
    """Mirror Java rsaEncode: X509 key decode + RSA/ECB/PKCS1Padding + Base64."""
    try:
        decoded_key = base64.b64decode(RSA_PUBLIC_KEY_B64)
        public_key = load_der_public_key(decoded_key)
        encrypted = public_key.encrypt(pwd.encode("utf-8"), asym_padding.PKCS1v15())
        return base64.b64encode(encrypted).decode("utf-8")
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Failed to RSA-encrypt password")
        return ""

def _encrypt_payload(data: dict, key: bytes, iv: bytes) -> str:
    """Serialize *data* to JSON and encrypt it with AES-CBC + PKCS7 padding.

    Returns a Base64-encoded ciphertext string to use as the POST body.
    Adjust the encoding (e.g. hex, raw bytes) and Content-Type below if the
    gateway expects a different wire format.
    """
    raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
    padder = sym_padding.PKCS7(128).padder()
    padded = padder.update(raw) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(encrypted).decode("utf-8")

def _decrypt_payload(encrypted_b64: str, key: bytes, iv: bytes) -> dict:
    """Decode a Base64 AES-CBC ciphertext and return the parsed JSON dict.

    Inverse of _encrypt_payload — useful for verifying intercepted API messages.
    """
    ciphertext = base64.b64decode(encrypted_b64)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = sym_padding.PKCS7(128).unpadder()
    plain = unpadder.update(padded) + unpadder.finalize()
    return json.loads(plain.decode("utf-8"))


class HanchuAuthCoordinator(DataUpdateCoordinator[dict]):
    """Refresh a Hanchu OAuth token once per hour via the gateway login endpoint."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_auth",
            update_interval=timedelta(hours=TOKEN_REFRESH_HOURS),
        )
        self._entry = entry

    # ------------------------------------------------------------------
    # DataUpdateCoordinator interface
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict:
        """Encrypt credentials, POST to auth endpoint, and return token data.

        Raises:
            ConfigEntryAuthFailed: on HTTP 401 or a non-success API error code.
            UpdateFailed: on any network / HTTP error.
        """
        account: str = self._entry.data[CONF_ACCOUNT]
        pwd_plain: str = self._entry.data[CONF_PWD]
        pwd_rsa: str = _rsa_encode_pwd(pwd_plain)
        if not pwd_rsa:
            raise UpdateFailed("Failed to RSA-encrypt password")

        encrypted_body = _encrypt_payload(
            {"account": account, "pwd": pwd_rsa},
            AES_SECRET_KEY,
            AES_IV,
        )

        session = async_get_clientsession(self.hass)
        try:
            async with session.post(
                AUTH_URL,
                data=encrypted_body,
                headers={**_BASE_HEADERS, "Access-Token": ""},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status == 401:
                    raise ConfigEntryAuthFailed(
                        "Hanchu ESS authentication rejected - verify account and password."
                    )
                response.raise_for_status()
                result: dict = await response.json(content_type=None)
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Network error communicating with Hanchu ESS API: {err}") from err

        # API returns code 200 or 20001 on success; "data" is the raw token string.
        if result.get("code") not in (200, 20001):
            raise ConfigEntryAuthFailed(
                f"Hanchu ESS auth error (code={result.get('code')}): "
                f"{result.get('msg') or result.get('message', 'unknown error')}"
            )

        token_str: str = result.get("data", "")
        if not token_str:
            raise UpdateFailed("Hanchu ESS login succeeded but returned no token")
        token_data = {"token": token_str}
        _LOGGER.debug("Hanchu ESS OAuth token refreshed successfully")
        return token_data

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    @property
    def access_token(self) -> str | None:
        """Return the bearer access token string, or None if not yet fetched."""
        if not self.data:
            return None
        return self.data.get("token")


class HanchuDataCoordinator(DataUpdateCoordinator[dict]):
    """Poll the Hanchu energy statistics endpoint every 30 minutes."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        auth: HanchuAuthCoordinator,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_data",
            update_interval=timedelta(minutes=DATA_POLL_MINUTES),
        )
        self._entry = entry
        self._auth = auth

    async def _async_update_data(self) -> dict:
        """Fetch yearly energy totals for the current year."""
        token = self._auth.access_token
        if not token:
            raise UpdateFailed("No auth token available — waiting for auth coordinator")

        encrypted_body = _encrypt_payload(
            {
                "sn": self._entry.data[CONF_SN],
                "devType": DATA_DEV_TYPE,
                "maxCount": DATA_MAX_COUNT,
                "dateStr": "0",
                "masterSum": True,
            },
            AES_SECRET_KEY,
            AES_IV,
        )

        session = async_get_clientsession(self.hass)
        try:
            async with session.post(
                DATA_URL,
                data=encrypted_body,
                headers={**_BASE_HEADERS, "Access-Token": token},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status == 401:
                    raise ConfigEntryAuthFailed("Hanchu ESS token expired — re-authenticating")
                response.raise_for_status()
                result: dict = await response.json(content_type=None)
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Network error fetching energy data: {err}") from err

        if result.get("code") not in (200, 20001):
            raise UpdateFailed(
                f"Hanchu ESS data error (code={result.get('code')}): "
                f"{result.get('msg') or result.get('message', 'unknown error')}"
            )

        records: list[dict] = result.get("data") or []
        current_year = str(datetime.now().year)
        year_data = next((r for r in records if r.get("date") == current_year), None)
        if year_data is None:
            raise UpdateFailed(f"No energy data found for year {current_year}")

        return {
            "load":       float(year_data.get("loadEe") or 0),
            "generation": float(year_data.get("pvDge") or 0),
            "charge":     float(year_data.get("batTdChg") or 0),
            "discharge":  float(year_data.get("batTdDschg") or 0),
            "from_grid":  float(year_data.get("gridTdEe") or 0),
            "to_grid":    float(year_data.get("gridTdFe") or 0),
        }


class HanchuPowerCoordinator(DataUpdateCoordinator[dict]):
    """Poll the Hanchu powerChart endpoint every 5 minutes for live device state."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        auth: HanchuAuthCoordinator,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_power",
            update_interval=timedelta(minutes=POWER_POLL_MINUTES),
        )
        self._entry = entry
        self._auth = auth

    async def _async_update_data(self) -> dict:
        """Fetch live device state including battery SOC."""
        token = self._auth.access_token
        if not token:
            raise UpdateFailed("No auth token available — waiting for auth coordinator")

        encrypted_body = _encrypt_payload({"sn": self._entry.data[CONF_SN]}, AES_SECRET_KEY, AES_IV)

        session = async_get_clientsession(self.hass)
        try:
            async with session.post(
                POWER_URL,
                data=encrypted_body,
                headers={**_BASE_HEADERS, "Access-Token": token},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status == 401:
                    raise ConfigEntryAuthFailed("Hanchu ESS token expired — re-authenticating")
                response.raise_for_status()
                result: dict = await response.json(content_type=None)
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Network error fetching power data: {err}") from err

        if result.get("code") not in (200, 20001):
            raise UpdateFailed(
                f"Hanchu ESS power error (code={result.get('code')}): "
                f"{result.get('msg') or result.get('message', 'unknown error')}"
            )

        device: dict = result.get("data") or {}
        raw_soc = device.get("batSoc")
        if raw_soc is None:
            raise UpdateFailed("powerChart response missing batSoc field")

        grid_raw = float(device.get("pwrGridSum") or 0)
        bat_raw = float(device.get("batP") or 0)

        return {
            "battery_soc":            round(float(raw_soc) * 100, 1),
            "solar_power":            float(device.get("pvTtPwr") or 0),
            "ext_solar_power":        float(device.get("bypMeterTotalPower") or 0),
            "load_power":             float(device.get("loadPwr") or 0),
            "grid_import_power":      max(0.0, grid_raw),
            "grid_export_power":      max(0.0, -grid_raw),
            "battery_charge_power":   max(0.0, bat_raw),
            "battery_discharge_power": max(0.0, -bat_raw),
            "battery_power":          -bat_raw,
        }


class HanchuSettingsCoordinator(DataUpdateCoordinator[dict]):
    """On-demand reader/writer for Hanchu PCS work-mode settings via the iotGet/iotSet endpoints.

    There is no automatic polling — press the Read Settings button entity to load current
    values from the device, and press Write Settings to send staged changes to the device.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        auth: HanchuAuthCoordinator,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_settings",
            update_interval=None,
        )
        self._entry = entry
        self._auth = auth
        self._pending: dict = {}

    async def _async_update_data(self) -> dict:
        """Fetch current work-mode settings from iotGet."""
        token = self._auth.access_token
        if not token:
            raise UpdateFailed("No auth token available — waiting for auth coordinator")

        encrypted_body = _encrypt_payload(
            {
                "devType": "2",
                "sn": self._entry.data[CONF_SN],
                "keys": IOT_SETTINGS_KEYS,
            },
            AES_SECRET_KEY,
            AES_IV,
        )

        session = async_get_clientsession(self.hass)
        try:
            async with session.post(
                IOT_GET_URL,
                data=encrypted_body,
                headers={**_BASE_HEADERS, "Access-Token": token},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status == 401:
                    raise ConfigEntryAuthFailed("Hanchu ESS token expired — re-authenticating")
                response.raise_for_status()
                result: dict = await response.json(content_type=None)
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Network error fetching settings: {err}") from err

        if result.get("code") not in (200, 20001):
            raise UpdateFailed(
                f"Hanchu ESS settings error (code={result.get('code')}): "
                f"{result.get('msg') or result.get('message', 'unknown error')}"
            )

        data = result.get("data") or {}
        self._pending = {}
        return data

    @callback
    def async_update_local(self, values: dict) -> None:
        """Merge values into coordinator data and staging dict without an API call.

        Notifies all listeners so entities reflect the change immediately.
        Call async_write_pending() (via the Write Settings button) to persist to the device.
        """
        self._pending.update(values)
        merged = {**(self.data or {}), **values}
        self.async_set_updated_data(merged)

    async def async_write_pending(self) -> None:
        """Send only locally staged changes to iotSet; no-op if nothing is pending."""
        if not self._pending:
            return
        await self.async_set_settings(self._pending.copy())

    async def async_set_settings(self, values: dict) -> None:
        """Write one or more setting fields to the device via iotSet.

        Raises UpdateFailed on network or API error.
        """
        token = self._auth.access_token
        if not token:
            raise UpdateFailed("No auth token available — cannot write settings")

        encrypted_body = _encrypt_payload(
            {
                "devType": "2",
                "sn": self._entry.data[CONF_SN],
                "value": values,
            },
            AES_SECRET_KEY,
            AES_IV,
        )

        session = async_get_clientsession(self.hass)
        try:
            async with session.post(
                IOT_SET_URL,
                data=encrypted_body,
                headers={**_BASE_HEADERS, "Access-Token": token},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status == 401:
                    raise ConfigEntryAuthFailed("Hanchu ESS token expired — re-authenticating")
                response.raise_for_status()
                result: dict = await response.json(content_type=None)
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Network error writing settings: {err}") from err

        if result.get("code") not in (200, 20001):
            raise UpdateFailed(
                f"Hanchu ESS iotSet error (code={result.get('code')}): "
                f"{result.get('msg') or result.get('message', 'unknown error')}"
            )

        _LOGGER.debug("Hanchu ESS settings written: %s", list(values.keys()))
        self._pending = {}
        await self.async_refresh()

    async def async_fast_charge_discharge(self, mode: str, duration_minutes: int | None) -> None:
        """POST a fast-charge/discharge command to the gateway.

        mode: fast_charge | fast_discharge | stop_charge | stop_discharge
        duration_minutes: required for start modes, ignored for stop modes.
        """
        token = self._auth.access_token
        if not token:
            raise UpdateFailed("No auth token available — cannot send command")

        act_map = {
            "fast_charge":    2,
            "fast_discharge": 3,
            "stop_charge":    "-2",
            "stop_discharge": "-3",
        }
        payload: dict = {"sn": self._entry.data[CONF_SN], "act": act_map[mode]}
        if mode in ("fast_charge", "fast_discharge"):
            payload["duration"] = (duration_minutes or 0) * 60

        encrypted_body = _encrypt_payload(payload, AES_SECRET_KEY, AES_IV)
        session = async_get_clientsession(self.hass)
        try:
            async with session.post(
                FAST_CHARGE_DISCHARGE_URL,
                data=encrypted_body,
                headers={**_BASE_HEADERS, "Access-Token": token},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status == 401:
                    raise ConfigEntryAuthFailed("Hanchu ESS token expired — re-authenticating")
                response.raise_for_status()
                result: dict = await response.json(content_type=None)
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Network error sending fast charge/discharge: {err}") from err

        if result.get("code") not in (200, 20001):
            raise UpdateFailed(
                f"Hanchu ESS fast charge/discharge error (code={result.get('code')}): "
                f"{result.get('msg') or result.get('message', 'unknown error')}"
            )
        _LOGGER.debug("Hanchu ESS fast charge/discharge sent: mode=%s", mode)
