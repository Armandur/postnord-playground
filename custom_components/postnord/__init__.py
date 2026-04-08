"""PostNord integration for Home Assistant."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import PostNordApiClient
from .const import CONF_API_KEY, CONF_POSTAL_CODE, DOMAIN
from .coordinator import MailboxCoordinator, PostNordCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up PostNord from a config entry."""
    session = async_get_clientsession(hass)
    client = PostNordApiClient(session, entry.data[CONF_API_KEY])

    package_coordinator = PostNordCoordinator(hass, entry, client)
    await package_coordinator.async_config_entry_first_refresh()

    coordinators: dict = {"packages": package_coordinator}

    postal_code = entry.data.get(CONF_POSTAL_CODE, "").strip()
    if postal_code:
        mailbox_coordinator = MailboxCoordinator(hass, client, postal_code)
        await mailbox_coordinator.async_config_entry_first_refresh()
        coordinators["mailbox"] = mailbox_coordinator

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinators

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration when options change (e.g. packages added/removed)."""
    await hass.config_entries.async_reload(entry.entry_id)
