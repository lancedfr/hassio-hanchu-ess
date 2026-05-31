"""Sensor platform for Hanchu — yearly energy totals."""

from __future__ import annotations

from datetime import UTC, datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import CONF_NAME, PERCENTAGE, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import HanchuConfigEntry
from .const import CONF_SN, DOMAIN
from .coordinator import HanchuDataCoordinator, HanchuPowerCoordinator

# (key in coordinator.data, display name, icon)
_ENERGY_SENSORS: list[tuple[str, str, str]] = [
    ("load",       "Load",       "mdi:home-lightning-bolt"),
    ("generation", "Generation", "mdi:solar-power"),
    ("charge",     "Charge",     "mdi:battery-charging"),
    ("discharge",  "Discharge",  "mdi:battery-minus"),
    ("from_grid",  "From Grid",  "mdi:transmission-tower-import"),
    ("to_grid",    "To Grid",    "mdi:transmission-tower-export"),
]

# (key in coordinator.data, display name, icon)
_POWER_SENSORS: list[tuple[str, str, str]] = [
    ("solar_power",             "Solar Production Power",  "mdi:solar-power-variant"),
    ("ext_solar_power",         "AC Coupled Solar Power",  "mdi:solar-power-variant"),
    ("load_power",              "Home Usage Power",        "mdi:home-lightning-bolt"),
    ("grid_import_power",       "Grid Import Power",       "mdi:transmission-tower-import"),
    ("grid_export_power",       "Grid Export Power",       "mdi:transmission-tower-export"),
    ("battery_charge_power",    "Battery Charge Power",    "mdi:battery-charging"),
    ("battery_discharge_power", "Battery Discharge Power", "mdi:battery-minus"),
    ("battery_power",           "Battery Power",           "mdi:battery"),
]


def _device_info(entry: HanchuConfigEntry) -> dict:
    return {
        "identifiers": {(DOMAIN, entry.data[CONF_SN])},
        "name": entry.data.get(CONF_NAME, "Hanchu ESS"),
        "manufacturer": "Hanchu",
        "model": "PCS",
    }


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HanchuConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hanchu energy and power sensors from a config entry."""
    data_coordinator = entry.runtime_data.data_coordinator
    power_coordinator = entry.runtime_data.power_coordinator

    entities: list[SensorEntity] = [
        HanchuEnergySensor(data_coordinator, entry, key, name, icon)
        for key, name, icon in _ENERGY_SENSORS
    ]
    entities.extend(
        HanchuLivePowerSensor(power_coordinator, entry, key, name, icon)
        for key, name, icon in _POWER_SENSORS
    )
    entities.append(HanchuBatterySensor(power_coordinator, entry))
    async_add_entities(entities)


class HanchuEnergySensor(CoordinatorEntity[HanchuDataCoordinator], SensorEntity):
    """A single yearly energy total sensor backed by HanchuDataCoordinator."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(
        self,
        coordinator: HanchuDataCoordinator,
        entry: HanchuConfigEntry,
        key: str,
        name: str,
        icon: str,
    ) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._attr_icon = icon
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = _device_info(entry)

    @property
    def last_reset(self) -> datetime:
        """Return the start of the current year — values reset every January 1st."""
        return datetime(datetime.now().year, 1, 1, tzinfo=UTC)

    @property
    def native_value(self) -> float | None:
        """Return the current sensor value from coordinator data."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._key)


class HanchuLivePowerSensor(CoordinatorEntity[HanchuPowerCoordinator], SensorEntity):
    """A live power flow sensor (W) backed by HanchuPowerCoordinator."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT

    def __init__(
        self,
        coordinator: HanchuPowerCoordinator,
        entry: HanchuConfigEntry,
        key: str,
        name: str,
        icon: str,
    ) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._attr_icon = icon
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> float | None:
        """Return the current power value in watts."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._key)


class HanchuBatterySensor(CoordinatorEntity[HanchuPowerCoordinator], SensorEntity):
    """Battery state-of-charge sensor, updated every 5 minutes."""

    _attr_has_entity_name = True
    _attr_name = "Home Battery"
    _attr_icon = "mdi:battery"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator: HanchuPowerCoordinator, entry: HanchuConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_battery_soc"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> float | None:
        """Return battery SOC as a percentage (0–100)."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("battery_soc")
