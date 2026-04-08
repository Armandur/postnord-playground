#!/usr/bin/env python3
"""PostNord Track & Trace API v7 - terminal tester."""

import argparse
import json
import os
import sys

import urllib.request
import urllib.parse
import urllib.error

API_KEY_FILE = os.path.join(os.path.dirname(__file__), "api.key")
BASE_URL = "https://api2.postnord.com/rest/shipment/v7/trackandtrace/id/{id}/public"
TRACKING_URL_BASE = "https://api2.postnord.com/rest/shipment/v1/tracking/{country}/{id}"


def load_api_key(provided: str | None) -> str:
    if provided:
        return provided
    if os.path.isfile(API_KEY_FILE):
        key = open(API_KEY_FILE).read().strip()
        if key:
            return key
    print(
        "Ingen API-nyckel hittad. Ange med --apikey eller spara i api.key.",
        file=sys.stderr,
    )
    sys.exit(1)


def track(shipment_id: str, api_key: str, locale: str = "sv") -> dict:
    params = urllib.parse.urlencode({"apikey": api_key, "locale": locale})
    url = BASE_URL.format(id=urllib.parse.quote(shipment_id)) + "?" + params
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return {"error": e.code, "detail": json.loads(body)}
        except json.JSONDecodeError:
            return {"error": e.code, "detail": body}


def get_tracking_url(shipment_id: str, api_key: str, country: str, language: str = "sv") -> str | None:
    params = urllib.parse.urlencode({"apikey": api_key, "language": language})
    url = TRACKING_URL_BASE.format(
        country=urllib.parse.quote(country),
        id=urllib.parse.quote(shipment_id),
    ) + "?" + params
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            return data.get("url")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"\nTracking-URL misslyckades (HTTP {e.code}):")
        try:
            print(json.dumps(json.loads(body), indent=2, ensure_ascii=False))
        except json.JSONDecodeError:
            print(body)
        return None


def fmt_address(addr: dict) -> str:
    parts = [addr.get("street1"), addr.get("street2"), addr.get("postCode"), addr.get("city"), addr.get("country")]
    return ", ".join(p for p in parts if p)


def print_delivery_point(label: str, point: dict) -> None:
    if not point:
        return
    name = point.get("displayName") or point.get("name") or ""
    addr = fmt_address(point.get("address", {}))
    loc_type = point.get("locationType") or point.get("servicePointType") or ""
    parts = [name, addr, f"[{loc_type}]" if loc_type else ""]
    print(f"  {label}: {', '.join(p for p in parts if p)}")
    hours = point.get("openingHours", [])
    if hours:
        days = {
            "monday": "Mån", "tuesday": "Tis", "wednesday": "Ons",
            "thursday": "Tor", "friday": "Fre", "saturday": "Lör", "sunday": "Sön",
        }
        for h in hours:
            open_days = "/".join(sv for en, sv in days.items() if h.get(en))
            times = f"{h.get('openFrom', '')}-{h.get('openTo', '')}"
            if h.get("openFrom2"):
                times += f", {h['openFrom2']}-{h.get('openTo2', '')}"
            if open_days:
                print(f"    Öppet {open_days}: {times}")


def print_result(data: dict) -> None:
    resp = data.get("TrackingInformationResponse", {})

    faults = resp.get("compositeFault", {}).get("faults", [])
    if faults:
        print("\n-- FEL --")
        for f in faults:
            print(f"  {f.get('faultCode')}: {f.get('explanationText')}")
        return

    shipments = resp.get("shipments", [])
    if not shipments:
        print("Inga försändelser hittades.")
        return

    for s in shipments:
        print(f"\n=== Försändelse {s.get('shipmentId')} ===")
        status = s.get("status", "-")
        status_text = s.get("statusText", {})
        print(f"Status    : {status}")
        if status_text.get("header"):
            print(f"            {status_text['header']}")
        if status_text.get("body"):
            print(f"            {status_text['body']}")

        if s.get("estimatedTimeOfArrival"):
            print(f"Beräknad leverans: {s['estimatedTimeOfArrival']}")
        if s.get("publicTimeOfArrival"):
            print(f"Publik ETA       : {s['publicTimeOfArrival']}")
        if s.get("deliveryDate"):
            print(f"Levererad        : {s['deliveryDate']}")
        if s.get("riskForDelay"):
            print("  ! Risk för försening")

        consignor = s.get("consignor", {})
        if consignor.get("name"):
            print(f"Avsändare : {consignor['name']}")

        consignee = s.get("consignee", {})
        consignee_name = consignee.get("name", "")
        consignee_addr = fmt_address(consignee.get("address", {}))
        if consignee_name or consignee_addr:
            print(f"Mottagare : {', '.join(p for p in [consignee_name, consignee_addr] if p)}")

        service = s.get("service", {})
        if service.get("name"):
            print(f"Tjänst    : {service['name']}")

        # Leveranspunkter
        requested = s.get("requestedDeliveryPoint", {})
        actual = s.get("deliveryPoint", {})
        destination = s.get("destinationDeliveryPoint", {})
        if requested or actual or destination:
            print("\n-- Leveranspunkter --")
            print_delivery_point("Önskat ombud  ", requested)
            print_delivery_point("Faktiskt ombud", actual)
            print_delivery_point("Slutdestination", destination)

        items = s.get("items", [])
        for item in items:
            print(f"\n  Kolli {item.get('itemId')}")
            print(f"  Status: {item.get('status')} / {item.get('eventStatus')}")
            item_status = item.get("statusText", {})
            if item_status.get("header"):
                print(f"          {item_status['header']}")

            if item.get("deliveryTo"):
                print(f"  Lämnad till  : {item['deliveryTo']}")
            if item.get("deliveryToInfo"):
                print(f"  Leveransinfo : {item['deliveryToInfo']}")
            if item.get("isPlacedInRetailParcelBox"):
                print("  Placerad i paketbox")
            if item.get("bookedDeliveryDateFrom"):
                date_from = item["bookedDeliveryDateFrom"][:16]
                date_to = item.get("bookedDeliveryDateTo", "")[:16]
                print(f"  Bokad tid    : {date_from} – {date_to}")
            if item.get("deliveryDate"):
                print(f"  Levererad    : {item['deliveryDate'][:16]}")
            if item.get("stoppedInCustoms"):
                print("  ! Stoppad i tull")

            events = item.get("events", [])
            if events:
                print(f"  Händelser ({len(events)}):")
                for ev in events:
                    loc = ev.get("location", {})
                    place = loc.get("displayName") or loc.get("name") or loc.get("city") or ""
                    print(f"    {ev.get('eventTime', '')[:16]}  {ev.get('eventDescription', '')}  {place}")


def main() -> None:
    parser = argparse.ArgumentParser(description="PostNord Track & Trace terminal")
    parser.add_argument("--apikey", "-k", help="PostNord API-nyckel (32 tecken)")
    parser.add_argument("--locale", "-l", default="sv", choices=["sv", "en", "no", "da", "fi"])
    parser.add_argument("--country", "-c", default="SE", choices=["SE", "NO", "FI", "DK"],
                        help="Land för tracking-URL (standard: SE)")
    parser.add_argument("--raw", action="store_true", help="Skriv ut rå JSON")
    parser.add_argument("--no-url", dest="no_url", action="store_true",
                        help="Hämta inte tracking-URL")
    parser.add_argument("id", nargs="?", help="Sändnings- eller kolli-ID")
    args = parser.parse_args()

    api_key = load_api_key(args.apikey)

    if args.id:
        shipment_id = args.id
    else:
        shipment_id = input("Ange sändnings-ID: ").strip()
        if not shipment_id:
            print("Inget ID angivet.", file=sys.stderr)
            sys.exit(1)

    data = track(shipment_id, api_key, args.locale)

    if args.raw or "error" in data:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print_result(data)
        if not args.no_url:
            tracking_url = get_tracking_url(shipment_id, api_key, args.country, args.locale)
            if tracking_url:
                print(f"\nTracking-URL: {tracking_url}")


if __name__ == "__main__":
    main()
