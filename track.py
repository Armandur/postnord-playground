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
        if s.get("deliveryDate"):
            print(f"Levererad        : {s['deliveryDate']}")

        consignor = s.get("consignor", {})
        if consignor.get("name"):
            print(f"Avsändare : {consignor['name']}")

        consignee = s.get("consignee", {})
        addr = consignee.get("address", {})
        if addr.get("city"):
            print(f"Till      : {addr.get('postCode', '')} {addr['city']}")

        service = s.get("service", {})
        if service.get("name"):
            print(f"Tjänst    : {service['name']}")

        items = s.get("items", [])
        for item in items:
            print(f"\n  Kolli {item.get('itemId')}")
            print(f"  Status: {item.get('status')} / {item.get('eventStatus')}")
            item_status = item.get("statusText", {})
            if item_status.get("header"):
                print(f"          {item_status['header']}")

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
    parser.add_argument("--raw", action="store_true", help="Skriv ut rå JSON")
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


if __name__ == "__main__":
    main()
