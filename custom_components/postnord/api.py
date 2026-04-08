"""Async PostNord API client."""
from __future__ import annotations

import urllib.parse
from typing import Any

import aiohttp


TRACK_URL = "https://api2.postnord.com/rest/shipment/v7/trackandtrace/id/{id}/public"
TRACKING_LINK_URL = "https://api2.postnord.com/rest/links/v1/tracking/{country}/{id}"
MAILBOX_URL = "https://portal.postnord.com/api/sendoutarrival/closest"


class PostNordApiError(Exception):
    """Raised when the PostNord API returns an error."""


class PostNordApiClient:
    """Thin async wrapper around the PostNord REST APIs."""

    def __init__(self, session: aiohttp.ClientSession, api_key: str) -> None:
        self._session = session
        self._api_key = api_key

    async def async_track(self, tracking_id: str, locale: str = "sv") -> dict[str, Any]:
        """Fetch tracking data for a shipment ID."""
        params = {"apikey": self._api_key, "locale": locale}
        url = TRACK_URL.format(id=urllib.parse.quote(tracking_id, safe=""))
        try:
            async with self._session.get(url, params=params) as resp:
                if resp.status >= 400:
                    body = await resp.text()
                    raise PostNordApiError(f"HTTP {resp.status}: {body[:200]}")
                return await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise PostNordApiError(str(err)) from err

    async def async_get_tracking_url(
        self,
        tracking_id: str,
        country: str,
        language: str = "sv",
    ) -> str | None:
        """Return the public tracking URL for a shipment, or None on failure."""
        params = {"apikey": self._api_key, "language": language}
        url = TRACKING_LINK_URL.format(
            country=urllib.parse.quote(country, safe=""),
            id=urllib.parse.quote(tracking_id, safe=""),
        )
        try:
            async with self._session.get(url, params=params) as resp:
                if resp.status >= 400:
                    return None
                data = await resp.json(content_type=None)
                return data.get("url")
        except aiohttp.ClientError:
            return None

    async def async_get_mailbox_schedule(self, postal_code: str) -> dict[str, Any]:
        """Return the next mailbox delivery schedule for a postal code."""
        try:
            async with self._session.get(
                MAILBOX_URL, params={"postalCode": postal_code}
            ) as resp:
                if resp.status >= 400:
                    body = await resp.text()
                    raise PostNordApiError(f"HTTP {resp.status}: {body[:200]}")
                return await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise PostNordApiError(str(err)) from err


def parse_tracking_input(raw: str) -> str:
    """Extract a tracking ID from a raw ID string or a PostNord tracking URL.

    PostNord tracking URLs use an obfuscated ?id= parameter of the form:
        prefix:seg1:hash:seg2:hash:hash:hash:seg3
    where the tracking ID = seg1 + seg2 + seg3 (uppercased).
    Verified against three real examples with IDs:
        00773501646404126891, 25077649482SE, UO553662591SE
    """
    raw = raw.strip()
    if not raw:
        return ""
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme in ("http", "https"):
        qs = urllib.parse.parse_qs(parsed.query)
        if "shipmentId" in qs:
            return qs["shipmentId"][0].upper()
        if "id" in qs:
            parts = qs["id"][0].split(":")
            if len(parts) == 8:
                return (parts[1] + parts[3] + parts[7]).upper()
        # Unknown URL format — return the full URL stripped; coordinator will fail gracefully
        return raw
    return raw.upper()
