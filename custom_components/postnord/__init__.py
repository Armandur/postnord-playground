"""PostNord integration for Home Assistant."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import PostNordApiClient, parse_tracking_input
from .const import (
    CONF_API_KEY,
    CONF_COUNTRY,
    CONF_DISPLAY_NAME,
    CONF_OWNER,
    CONF_PACKAGES,
    CONF_POSTAL_CODE,
    CONF_TRACKING_ID,
    DEFAULT_COUNTRY,
    DOMAIN,
    SUPPORTED_COUNTRIES,
)
from .coordinator import MailboxCoordinator, PostNordCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]

SERVICE_ADD_PACKAGE = "add_package"
SERVICE_REMOVE_PACKAGE = "remove_package"

_ADD_PACKAGE_SCHEMA = vol.Schema(
    {
        vol.Required("tracking_id"): cv.string,
        vol.Optional("owner", default=""): cv.string,
        vol.Optional("country", default=DEFAULT_COUNTRY): vol.In(SUPPORTED_COUNTRIES),
    }
)

_REMOVE_PACKAGE_SCHEMA = vol.Schema(
    {
        vol.Required("tracking_id"): cv.string,
    }
)


def _get_first_entry(hass: HomeAssistant) -> ConfigEntry | None:
    """Return the first (and typically only) PostNord config entry."""
    entries = hass.config_entries.async_entries(DOMAIN)
    return entries[0] if entries else None


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

    # Register services once (guard against multiple config entries)
    if not hass.services.has_service(DOMAIN, SERVICE_ADD_PACKAGE):
        _register_services(hass)

    return True


def _register_services(hass: HomeAssistant) -> None:
    """Register postnord.add_package and postnord.remove_package services."""

    async def handle_add_package(call: ServiceCall) -> None:
        raw = call.data["tracking_id"].strip()
        tracking_id = parse_tracking_input(raw)
        owner = call.data.get("owner", "").strip()
        country = call.data.get("country", DEFAULT_COUNTRY)

        if not tracking_id:
            _LOGGER.error("postnord.add_package: could not parse tracking ID from %r", raw)
            return

        current_entry = _get_first_entry(hass)
        if current_entry is None:
            _LOGGER.error("postnord.add_package: no PostNord config entry found")
            return

        packages = list(current_entry.options.get(CONF_PACKAGES, []))
        if any(p[CONF_TRACKING_ID] == tracking_id for p in packages):
            _LOGGER.warning(
                "postnord.add_package: %s is already being tracked", tracking_id
            )
            return

        packages.append(
            {
                CONF_TRACKING_ID: tracking_id,
                CONF_DISPLAY_NAME: tracking_id,
                CONF_OWNER: owner,
                CONF_COUNTRY: country,
            }
        )
        hass.config_entries.async_update_entry(
            current_entry,
            options={**current_entry.options, CONF_PACKAGES: packages},
        )
        _LOGGER.info("postnord.add_package: added %s (owner=%r)", tracking_id, owner)

    async def handle_remove_package(call: ServiceCall) -> None:
        raw = call.data["tracking_id"].strip()
        tracking_id = parse_tracking_input(raw)

        current_entry = _get_first_entry(hass)
        if current_entry is None:
            return

        packages = [
            p
            for p in current_entry.options.get(CONF_PACKAGES, [])
            if p[CONF_TRACKING_ID] != tracking_id
        ]
        hass.config_entries.async_update_entry(
            current_entry,
            options={**current_entry.options, CONF_PACKAGES: packages},
        )
        _LOGGER.info("postnord.remove_package: removed %s", tracking_id)

    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_PACKAGE,
        handle_add_package,
        schema=_ADD_PACKAGE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE_PACKAGE,
        handle_remove_package,
        schema=_REMOVE_PACKAGE_SCHEMA,
    )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    # Remove services when the last entry is unloaded
    if not hass.data.get(DOMAIN):
        for service in (SERVICE_ADD_PACKAGE, SERVICE_REMOVE_PACKAGE):
            hass.services.async_remove(DOMAIN, service)

    return unloaded


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration when options change (e.g. packages added/removed)."""
    await hass.config_entries.async_reload(entry.entry_id)
