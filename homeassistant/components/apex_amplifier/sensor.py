
from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity 
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, CONF_HOST, EVENT_HOMEASSISTANT_STOP, UnitOfTemperature
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN, DEFAULT_PORT
from . import ApexConfigEntry
from .apex_ip_client import CloudpowerClient, ApexConnectionError

_LOGGER = logging.getLogger(__name__)

"""Report the temperature of the hottest module in the amplifier"""
class ApexHottestModule(SensorEntity):
    _attr_has_entity_name = True
    _attr_native_unit_of_measure = UnitOfTemperature.CELSIUS
    def __init__(self, config_entry: ApexConfigEntry, client: CloudpowerClient):
        self._entry = config_entry
        self._client = client
        self._temperature = None 

        self._attr_unique_id = f"{config_entry.entry_id}_temp"
        self._attr_name = "Temp"

    @property
    def native_value(self) -> float:
        return self._temperature

    async def async_update(self) -> None:
        temperature = await self._client.get_module_temperature()
        self._temperature = temperature

async def async_setup_entry(hass: HomeAssistant, entry: ApexConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> bool:
    host = entry.data[CONF_HOST]
    manager = hass.data[DOMAIN]["manager"]
    client = CloudpowerClient(host, manager)

    try:
        status = await client.get_amplifier_status(timeout=10.0)
        if not status:
            _LOGGER.error(f"Apex {host}:{DEFAULT_PORT} returned error status")
        else:
            _LOGGER.debug("Successfully connected to Apex at %s:%s", host, DEFAULT_PORT)
    except (ApexConnectionError, TimeoutError, OSError) as err:
        _LOGGER.error(
            "Failed to connect to Apex at %s:%s: %s", host, DEFAULT_PORT, err
        )
        await client.stop()
        raise ConfigEntryNotReady(
            f"Unable to connect to Apex amplifier at {host}:{DEFAULT_PORT}"
        ) from err

    entry.runtime_data = client

    sensor = ApexHottestModule(entry, client)

    async_add_entities([sensor])
