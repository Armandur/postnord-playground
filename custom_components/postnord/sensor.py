"""PostNord sensor entities."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_ARCHIVED,
    ATTR_COUNTRY,
    ATTR_DELIVERY_DATE,
    ATTR_DELIVERY_TYPE,
    ATTR_ETA,
    ATTR_ETA_TIMESTAMP,
    ATTR_IS_DELAYED,
    ATTR_LAST_EVENT,
    ATTR_OWNER,
    ATTR_PICKUP_LOCATION,
    ATTR_PUBLIC_ETA,
    ATTR_RISK_FOR_DELAY,
    ATTR_SENDER,
    ATTR_SERVICE,
    ATTR_STATUS_BODY,
    ATTR_STATUS_HEADER,
    ATTR_TRACKING_ID,
    ATTR_TRACKING_URL,
    CONF_COUNTRY,
    CONF_DISPLAY_NAME,
    CONF_OWNER,
    CONF_PACKAGES,
    CONF_POSTAL_CODE,
    CONF_TRACKING_ID,
    DEFAULT_COUNTRY,
    DELIVERY_TYPE_HOME,
    DELIVERY_TYPE_MAILBOX,
    DELIVERY_TYPE_PARCEL_BOX,
    DELIVERY_TYPE_SERVICE_POINT,
    DOMAIN,
)
from .coordinator import MailboxCoordinator, PackageData, PostNordCoordinator

_LOGGER = logging.getLogger(__name__)

# (delivery_type, status) → icon
# Evaluated in order; first match wins.
_ICON_RULES: list[tuple[str | None, str | None, str]] = [
    # Delivered — universal
    (None, "DELIVERED", "mdi:package-variant-closed-check"),
    # Delayed — universal (checked before delivery-type specific)
    (None, "_DELAYED_", "mdi:clock-alert-outline"),
    # Service point
    (DELIVERY_TYPE_SERVICE_POINT, "AVAILABLE_FOR_PICKUP", "mdi:store-marker"),
    (DELIVERY_TYPE_SERVICE_POINT, "IN_TRANSIT", "mdi:truck-delivery"),
    (DELIVERY_TYPE_SERVICE_POINT, "EN_ROUTE", "mdi:truck-delivery"),
    # Parcel box
    (DELIVERY_TYPE_PARCEL_BOX, "AVAILABLE_FOR_PICKUP", "mdi:mailbox-open-up"),
    (DELIVERY_TYPE_PARCEL_BOX, "IN_TRANSIT", "mdi:truck-fast"),
    (DELIVERY_TYPE_PARCEL_BOX, "EN_ROUTE", "mdi:truck-fast"),
    # Home delivery
    (DELIVERY_TYPE_HOME, "IN_TRANSIT", "mdi:truck-delivery-outline"),
    (DELIVERY_TYPE_HOME, "EN_ROUTE", "mdi:truck-delivery-outline"),
    # Letter / mailbox delivery
    (DELIVERY_TYPE_MAILBOX, "DELIVERED", "mdi:mailbox"),
    (DELIVERY_TYPE_MAILBOX, "IN_TRANSIT", "mdi:email-fast-outline"),
    (DELIVERY_TYPE_MAILBOX, "EN_ROUTE", "mdi:email-fast-outline"),
]


def _resolve_icon(data: PackageData) -> str:
    for rule_type, rule_status, icon in _ICON_RULES:
        # Delayed pseudo-status
        if rule_status == "_DELAYED_":
            if data.is_delayed:
                return icon
            continue
        type_match = rule_type is None or rule_type == data.delivery_type
        status_match = rule_status is None or rule_status == data.status
        if type_match and status_match:
            return icon
    return "mdi:package-variant"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinators = hass.data[DOMAIN][entry.entry_id]
    package_coordinator: PostNordCoordinator = coordinators["packages"]
    mailbox_coordinator: MailboxCoordinator | None = coordinators.get("mailbox")

    entities: list[SensorEntity] = [
        PostNordSensor(package_coordinator, pkg, entry.entry_id)
        for pkg in entry.options.get(CONF_PACKAGES, [])
    ]

    if mailbox_coordinator is not None:
        postal_code = entry.data.get(CONF_POSTAL_CODE, "")
        entities.append(PostNordMailboxSensor(mailbox_coordinator, postal_code, entry.entry_id))

    async_add_entities(entities)


class PostNordSensor(CoordinatorEntity[PostNordCoordinator], SensorEntity):
    """One sensor per tracked package."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PostNordCoordinator,
        pkg_config: dict[str, Any],
        entry_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._tracking_id = pkg_config[CONF_TRACKING_ID]
        self._display_name = pkg_config.get(CONF_DISPLAY_NAME) or self._tracking_id
        self._owner = pkg_config.get(CONF_OWNER, "")
        self._country = pkg_config.get(CONF_COUNTRY, DEFAULT_COUNTRY)
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_{self._tracking_id}"
        self._attr_name = self._display_name

    @property
    def _data(self) -> PackageData | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._tracking_id)

    @property
    def state(self) -> str:
        if self._data is None:
            return "UNKNOWN"
        return self._data.status

    @property
    def icon(self) -> str:
        if self._data is None:
            return "mdi:package-variant"
        return _resolve_icon(self._data)

    @property
    def available(self) -> bool:
        # Available as long as coordinator has run at least once (stale data is OK)
        return self.coordinator.last_update_success or self._data is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self._data
        if d is None:
            return {ATTR_TRACKING_ID: self._tracking_id}
        return {
            ATTR_TRACKING_ID: d.tracking_id,
            ATTR_OWNER: d.owner,
            ATTR_TRACKING_URL: d.tracking_url,
            ATTR_STATUS_HEADER: d.status_header,
            ATTR_STATUS_BODY: d.status_body,
            ATTR_ETA: d.eta,
            ATTR_PUBLIC_ETA: d.public_eta,
            ATTR_ETA_TIMESTAMP: d.eta_timestamp,
            ATTR_DELIVERY_DATE: d.delivery_date,
            ATTR_RISK_FOR_DELAY: d.risk_for_delay,
            ATTR_IS_DELAYED: d.is_delayed,
            ATTR_SENDER: d.sender,
            ATTR_SERVICE: d.service,
            ATTR_DELIVERY_TYPE: d.delivery_type,
            ATTR_PICKUP_LOCATION: d.pickup_location,
            ATTR_LAST_EVENT: d.last_event,
            ATTR_COUNTRY: d.country,
            ATTR_ARCHIVED: d.archived,
        }


class PostNordMailboxSensor(CoordinatorEntity[MailboxCoordinator], SensorEntity):
    """Sensor showing the next mailbox delivery date for a postal code."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:mailbox"

    def __init__(
        self,
        coordinator: MailboxCoordinator,
        postal_code: str,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._postal_code = postal_code
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_mailbox_{postal_code}"
        self._attr_name = f"Postlåda {postal_code}"

    @property
    def state(self) -> str | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.next_delivery

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self.coordinator.data
        if d is None:
            return {"postal_code": self._postal_code}
        return {
            "postal_code": d.postal_code,
            "city": d.city,
            "last_delivery": d.last_delivery,
            "next_delivery": d.next_delivery,
        }
