from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, CONF_HOST, EVENT_HOMEASSISTANT_STOP
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN, DEFAULT_PORT
from . import ApexConfigEntry
from .apex_ip_client import CloudpowerClient, ApexConnectionError

_LOGGER = logging.getLogger(__name__)

"""Enable the power stage to be switched on and off to save power"""
class ApexPowerStage(SwitchEntity):
    def __init__(self, config_entry: ApexConfigEntry, client: CloudpowerClient):
        self._entry = config_entry
        self._client = client
        self._is_on = None 

        self._attr_unique_id = f"{config_entry.entry_id}_power"
        self._attr_has_entity_name = True
        self._attr_name = "Power"


    @property
    def is_on(self) -> bool:
        return self._is_on

    async def async_update(self) -> None:
        standby = await self._client.get_standby()
        self._is_on = not standby

    async def async_turn_off(self) -> None:
        await self._client.set_standby(True)
        self._is_on = False 
        self.async_write_ha_state()

    async def async_turn_on(self) -> None:
        await self._client.set_standby(False)
        self._is_on = True
        self.async_write_ha_state()

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

    switch = ApexPowerStage(entry, client)

    async_add_entities([switch])
