"""DataUpdateCoordinator for PostNord package tracking."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PostNordApiClient, PostNordApiError
from .const import (
    CONF_COUNTRY,
    CONF_OWNER,
    CONF_PACKAGES,
    CONF_TRACKING_ID,
    CONF_UPDATE_INTERVAL,
    DEFAULT_COUNTRY,
    DEFAULT_UPDATE_INTERVAL,
    DELIVERY_TYPE_HOME,
    DELIVERY_TYPE_MAILBOX,
    DELIVERY_TYPE_PARCEL_BOX,
    DELIVERY_TYPE_SERVICE_POINT,
    DELIVERY_TYPE_UNKNOWN,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class PackageData:
    """Holds all tracking data for a single package."""

    tracking_id: str
    status: str
    status_header: str
    status_body: str
    eta: str | None
    public_eta: str | None
    eta_timestamp: int | None
    delivery_date: str | None
    risk_for_delay: bool
    is_delayed: bool
    sender: str
    service: str
    delivery_type: str
    tracking_url: str | None
    pickup_location: str | None
    last_event: str | None
    country: str
    owner: str
    archived: bool = False


@dataclass
class MailboxData:
    """Holds mailbox delivery schedule for a postal code."""

    postal_code: str
    city: str
    last_delivery: str | None
    next_delivery: str | None


def _detect_delivery_type(shipment: dict[str, Any]) -> str:
    """Determine delivery type from shipment data."""
    items = shipment.get("items") or []
    if any(i.get("isPlacedInRetailParcelBox") for i in items):
        return DELIVERY_TYPE_PARCEL_BOX

    for dp_key in ("deliveryPoint", "destinationDeliveryPoint", "requestedDeliveryPoint"):
        dp = shipment.get(dp_key) or {}
        if dp.get("servicePointType") or dp.get("locationType"):
            return DELIVERY_TYPE_SERVICE_POINT

    service_name = ((shipment.get("service") or {}).get("name") or "").lower()
    if any(kw in service_name for kw in ("service point", "parcel locker", "servicepoint", "ombud")):
        return DELIVERY_TYPE_SERVICE_POINT
    if any(kw in service_name for kw in ("brev", "varubrev", "letter", "mypack home")):
        return DELIVERY_TYPE_MAILBOX
    if any(kw in service_name for kw in ("hem", "home", "dörr", "door")):
        return DELIVERY_TYPE_HOME

    return DELIVERY_TYPE_UNKNOWN


def _parse_eta_timestamp(eta_str: str | None) -> int | None:
    """Parse an ISO-8601 ETA string into a Unix timestamp, or None."""
    if not eta_str:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(eta_str, fmt).replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
        except ValueError:
            continue
    # Try date-only
    try:
        dt = datetime.strptime(eta_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except ValueError:
        return None


def _fmt_address(addr: dict[str, Any]) -> str:
    parts = [addr.get("street1"), addr.get("street2"), addr.get("postCode"), addr.get("city")]
    return ", ".join(p for p in parts if p)


def _extract_pickup_location(shipment: dict[str, Any]) -> str | None:
    for key in ("deliveryPoint", "destinationDeliveryPoint"):
        dp = shipment.get(key) or {}
        name = dp.get("displayName") or dp.get("name") or ""
        addr = _fmt_address(dp.get("address") or {})
        parts = [p for p in (name, addr) if p]
        if parts:
            return ", ".join(parts)
    return None


def _extract_last_event(shipment: dict[str, Any]) -> str | None:
    items = shipment.get("items") or []
    for item in reversed(items):
        events = item.get("events") or []
        if events:
            ev = events[-1]
            loc = ev.get("location") or {}
            place = loc.get("displayName") or loc.get("name") or loc.get("city") or ""
            time = (ev.get("eventTime") or "")[:16]
            desc = ev.get("eventDescription") or ""
            parts = [p for p in (time, desc, place) if p]
            return "  ".join(parts)
    return None


def _parse_shipment(
    shipment: dict[str, Any],
    tracking_url: str | None,
    country: str,
    owner: str,
    previous: PackageData | None,
) -> PackageData:
    """Build a PackageData from a raw PostNord shipment dict."""
    status = shipment.get("status") or "UNKNOWN"
    status_text = shipment.get("statusText") or {}
    eta_str = shipment.get("estimatedTimeOfArrival") or shipment.get("publicTimeOfArrival")
    eta_ts = _parse_eta_timestamp(eta_str)

    now_ts = int(datetime.now(timezone.utc).timestamp())
    risk = bool(shipment.get("riskForDelay"))
    is_delayed = risk or (
        eta_ts is not None
        and eta_ts < now_ts
        and status not in ("DELIVERED", "RETURNED", "EXPIRED")
    )

    return PackageData(
        tracking_id=shipment.get("shipmentId") or (previous.tracking_id if previous else ""),
        status=status,
        status_header=status_text.get("header") or "",
        status_body=status_text.get("body") or "",
        eta=eta_str,
        public_eta=shipment.get("publicTimeOfArrival"),
        eta_timestamp=eta_ts,
        delivery_date=shipment.get("deliveryDate"),
        risk_for_delay=risk,
        is_delayed=is_delayed,
        sender=(shipment.get("consignor") or {}).get("name") or "",
        service=((shipment.get("service") or {}).get("name") or ""),
        delivery_type=_detect_delivery_type(shipment),
        tracking_url=tracking_url or (previous.tracking_url if previous else None),
        pickup_location=_extract_pickup_location(shipment),
        last_event=_extract_last_event(shipment),
        country=country,
        owner=owner,
        archived=(status == "DELIVERED"),
    )


class PostNordCoordinator(DataUpdateCoordinator[dict[str, PackageData]]):
    """Coordinator that polls PostNord for all configured packages."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: PostNordApiClient,
    ) -> None:
        interval_minutes = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=interval_minutes),
        )
        self._client = client
        self._entry = entry
        # In-memory cache: tracking_id → PackageData (persists across poll cycles)
        self._cache: dict[str, PackageData] = {}

    async def _async_update_data(self) -> dict[str, PackageData]:
        packages = self._entry.options.get(CONF_PACKAGES, [])
        result: dict[str, PackageData] = {}

        for pkg_cfg in packages:
            tid = pkg_cfg[CONF_TRACKING_ID]
            country = pkg_cfg.get(CONF_COUNTRY, DEFAULT_COUNTRY)
            owner = pkg_cfg.get(CONF_OWNER, "")
            previous = self._cache.get(tid)

            # Skip archived (delivered) packages — freeze data forever
            if previous and previous.archived:
                result[tid] = previous
                continue

            try:
                raw = await self._client.async_track(tid)
                resp = raw.get("TrackingInformationResponse") or {}

                faults = (resp.get("compositeFault") or {}).get("faults") or []
                if faults:
                    _LOGGER.warning(
                        "PostNord faults for %s: %s",
                        tid,
                        ", ".join(f.get("explanationText", "") for f in faults),
                    )
                    if previous:
                        result[tid] = previous
                    continue

                shipments = resp.get("shipments") or []
                if not shipments:
                    if previous:
                        result[tid] = previous
                    continue

                shipment = shipments[0]
                tracking_url = await self._client.async_get_tracking_url(tid, country)
                pkg_data = _parse_shipment(shipment, tracking_url, country, owner, previous)
                self._cache[tid] = pkg_data
                result[tid] = pkg_data

            except PostNordApiError as err:
                _LOGGER.error("Error fetching %s: %s", tid, err)
                if previous:
                    # Return stale data rather than raising, so the sensor doesn't go unavailable
                    result[tid] = previous
                else:
                    raise UpdateFailed(f"PostNord API error for {tid}: {err}") from err

        return result


class MailboxCoordinator(DataUpdateCoordinator[MailboxData | None]):
    """Coordinator that polls the PostNord mailbox delivery schedule."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: PostNordApiClient,
        postal_code: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_mailbox",
            update_interval=timedelta(hours=12),
        )
        self._client = client
        self._postal_code = postal_code

    async def _async_update_data(self) -> MailboxData | None:
        try:
            data = await self._client.async_get_mailbox_schedule(self._postal_code)
        except PostNordApiError as err:
            raise UpdateFailed(str(err)) from err

        if not data:
            return None

        return MailboxData(
            postal_code=data.get("postalCode") or self._postal_code,
            city=data.get("city") or "",
            last_delivery=data.get("delivery"),
            next_delivery=data.get("upcoming"),
        )
