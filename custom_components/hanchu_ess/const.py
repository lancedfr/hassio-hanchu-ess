"""Constants for the Hanchu integration."""

DOMAIN = "hanchu"
DEFAULT_NAME = "Hanchu ESS"
# ---------------------------------------------------------------------------
# Auth / API  (config-entry data keys)
# ---------------------------------------------------------------------------
# account (email or username)
CONF_ACCOUNT = "account"
# account password
CONF_PWD = "pwd"
# device serial number found on homepage of official site labelled SN
CONF_SN = "sn"

AUTH_URL = "https://iess3.hanchuess.com/gateway/identify/auth/login/account"
DATA_URL = "https://iess3.hanchuess.com/gateway/platform/pcs/historyStaticsChart"
POWER_URL = "https://iess3.hanchuess.com/gateway/platform/pcs/powerChart"
IOT_GET_URL = "https://iess3.hanchuess.com/gateway/platform/deviceNew/iotGet"
IOT_SET_URL = "https://iess3.hanchuess.com/gateway/platform/deviceNew/iotSet"
FAST_CHARGE_DISCHARGE_URL = "https://iess3.hanchuess.com/gateway/platform/remoteContrDtu/fastChargeDischarge"
DATA_POLL_MINUTES: int = 30
POWER_POLL_MINUTES: int = 10
DATA_DEV_TYPE: str = "2"
DATA_MAX_COUNT: int = 1440

# ---------------------------------------------------------------------------
# Work mode values (WORK_MODE_CMB field)
# ---------------------------------------------------------------------------
WORK_MODE_USER_DEFINED: int = 3
WORK_MODE_SELF_CONSUMPTION: int = 1

# ---------------------------------------------------------------------------
# IoT field name constants
# ---------------------------------------------------------------------------
IOT_WORK_MODE = "WORK_MODE_CMB"
IOT_CHG_PWR = "CHG_PWR_LMT"
IOT_DSCHG_PWR = "DSCHG_PWR_LMT"
IOT_GRID_CHG_SOC = "DTU_AC_CHG_SOC_LMT"
IOT_MAX_CHG_SOC = "CHG_BAT_SOC_LMT"
IOT_MIN_DSCHG_SOC = "DSCHG_BAT_SOC_LMT"
IOT_MIN_OFF_GRID_SOC = "OFF_GRID_SOC_L"

IOT_SETTINGS_KEYS: list[str] = [
    IOT_WORK_MODE,
    IOT_CHG_PWR,
    IOT_DSCHG_PWR,
    IOT_GRID_CHG_SOC,
    IOT_MAX_CHG_SOC,
    IOT_MIN_DSCHG_SOC,
    IOT_MIN_OFF_GRID_SOC,
    "TCT_START_1", "TCT_END_1",
    "TDT_START_1", "TDT_END_1",
    "TCT_START_2", "TCT_END_2",
    "TDT_START_2", "TDT_END_2",
    "TCT_START_3", "TCT_END_3",
    "TDT_START_3", "TDT_END_3",
]

# Base64-encoded X509 RSA public key used by the official app for pwd encryption.
RSA_PUBLIC_KEY_B64 = "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCVg7RFDLMGM4O98d1zWKI5RQanjci3iY4qlpgsH76fUn3GnZtqjbRk37lCQDv6AhgPNXRPpty81+g909/c4yzySKaPCcDZv7KdCRB1mVxkq+0z4EtKx9EoTXKnFSDBaYi2srdal1tM3gGOsNTDN58CzYPXnDGPX7+EHS1Mm4aVDQIDAQAB"

# AES-CBC key and IV — both confirmed from the Hanchu web app JS bundle.
AES_IV: bytes = b"9z64Qr8mZH7Pg8d1"
AES_SECRET_KEY: bytes = b"9z64Qr8mZH7Pg8d1"

TOKEN_REFRESH_HOURS: int = 1
