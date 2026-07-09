"""The cloudpower_amplifier integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, CONF_HOST, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv

from .apex_ip_client import CloudpowerClient, ApexConnectionError, CloudpowerManager
from .const import DOMAIN, DEFAULT_PORT

# TODO List the platforms that you want to support.
PLATFORMS: list[Platform] = [Platform.SWITCH,
                             Platform.SENSOR]

type ApexConfigEntry = ConfigEntry[CloudpowerClient]  # noqa: F821

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config) -> bool:
    """Set up the Apex Amplifier integration."""

    manager = CloudpowerManager()
    await manager.start()

    hass.data[DOMAIN] = {
        "manager": manager,
    }

    async def async_stop(event):
        """Clean up the shared network listener."""
        manager.close()

    hass.bus.async_listen_once(
        EVENT_HOMEASSISTANT_STOP,
        async_stop,
    )

    return True


# TODO Update entry annotation
async def async_setup_entry(hass: HomeAssistant, entry: ApexConfigEntry) -> bool:
    _LOGGER.info("setting up config entry")
    """Set up cloudpower_amplifier from a config entry."""

    host = entry.data[CONF_HOST]
    manager = hass.data[DOMAIN]["manager"]
    client = CloudpowerClient(host, manager)

    try:
        status = await client.get_amplifier_status()
        if not status:
            _LOGGER.error(f"Apex {host}:{DEFAULT_PORT} returned error status")
        else:
            _LOGGER.debug("Successfully connected to Apex at %s:%s", host, DEFAULT_PORT)
    except (ApexConnectionError, TimeoutError, OSError) as err:
        _LOGGER.error(
            "Failed to connect to Apex at %s:%s: %s", host, DEFAULT_PORT, err
        )
        await client.stop()  # Clean up
        raise ConfigEntryNotReady(
            f"Unable to connect to Apex amplifier at {host}:{DEFAULT_PORT}"
        ) from err

    entry.runtime_data = client

    async def _async_close_client(_event):
        await client.stop()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_close_client)
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


# TODO Update entry annotation
async def async_unload_entry(hass: HomeAssistant, entry: ApexConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)