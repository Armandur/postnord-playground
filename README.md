# PostNord Home Assistant Integration

Ett projekt med två delar:
1. **`track.py`** — CLI-verktyg för att testa PostNords API direkt i terminalen
2. **`custom_components/postnord/`** — Home Assistant-integration för att spåra paket i HA

---

## Home Assistant-integrationen

### Funktioner

- Spårar PostNord-paket per användare/person i Home Assistant
- En sensor per paket med fullständig spårningsdata som attribut
- Automatisk uppdatering (standard var 30:e minut, konfigurerbart ner till 5 min)
- Levererade paket arkiveras direkt (inga fler API-anrop)
- Identifierar leveranstyp automatiskt: `SERVICE_POINT`, `PARCEL_BOX`, `HOME`, `MAILBOX`
- Dynamiska ikoner baserat på leveranstyp × status
- Brevutdelningssensor: visar nästa utdelningsdag för ett postnummer
- Stöder inmatning av sändningsnummer **eller** fullständiga PostNord-spårnings-URL:er
- **HA-tjänster** för att lägga till/ta bort paket direkt från dashboard utan att gå in i Inställningar
- HACS-kompatibel

### Installation

1. Kopiera mappen `custom_components/postnord/` till din HA config-mapp:
   ```
   /config/custom_components/postnord/
   ```
2. Starta om Home Assistant
3. Gå till **Inställningar → Integrationer → Lägg till → PostNord**
4. Ange din PostNord API-nyckel (skaffa på [developer.postnord.com](https://developer.postnord.com))
5. Ange postnummer om du vill ha brevutdelningssensorn (valfritt)

### Lägga till paket

**Alternativ 1 — Via dashboard (rekommenderas):**
Använd `postnord.add_package`-tjänsten direkt från Lovelace (se Dashboard-avsnittet nedan). Kräver att du sätter upp ett script och två input_text-hjälpare en gång.

**Alternativ 2 — Via integrationsmenyn:**
Gå till **Konfigurera** på integrationssidan → **Lägg till paket**.

I textfältet kan du klistra in (ett per rad):
- Sändningsnummer: `UO553662591SE`
- Hela PostNord-spårnings-URL:er: `https://tracking.postnord.com/se/?id=24896bc2:...`

Du kan blanda format fritt och lägga till flera paket på en gång.

### HA-tjänster

Integrationen registrerar två tjänster som kan anropas från Lovelace-knappar, automatiseringar och scripts:

#### `postnord.add_package`

| Parameter | Typ | Beskrivning |
|---|---|---|
| `tracking_id` | str (krävs) | Sändningsnummer eller PostNord-spårnings-URL |
| `owner` | str (valfri) | Vems paket, t.ex. "Rasmus" |
| `country` | str (valfri) | `SE` / `NO` / `FI` / `DK` (standard: `SE`) |

#### `postnord.remove_package`

| Parameter | Typ | Beskrivning |
|---|---|---|
| `tracking_id` | str (krävs) | Sändningsnumret som ska sluta spåras |

Tjänsterna syns också i **Utvecklarverktyg → Tjänster** i HA.

---

## Dashboard-setup (rekommenderat)

För att din sambo (eller du) ska kunna lägga till paket direkt från dashboarden utan att gå in i Inställningar:

### Steg 1: Skapa input_text-hjälpare

Gå till **Inställningar → Enheter & tjänster → Hjälpare → Lägg till → Text** och skapa:

| Namn | Entitets-ID |
|---|---|
| Nytt sändningsnummer | `input_text.postnord_ny_forsandelse` |
| Ägare | `input_text.postnord_agare` |

### Steg 2: Skapa ett script

Gå till **Inställningar → Automatiseringar → Scripts → Lägg till → YAML-läge** och klistra in:

```yaml
alias: "PostNord: Lägg till paket"
sequence:
  - service: postnord.add_package
    data:
      tracking_id: "{{ states('input_text.postnord_ny_forsandelse') }}"
      owner: "{{ states('input_text.postnord_agare') }}"
  - service: input_text.set_value
    target:
      entity_id: input_text.postnord_ny_forsandelse
    data:
      value: ""
mode: single
icon: mdi:package-variant-plus
```

### Steg 3: Installera auto-entities (rekommenderas)

Installera [auto-entities](https://github.com/thomasloven/lovelace-auto-entities) via HACS. Det gör att paketlistan uppdateras automatiskt utan att du behöver redigera något i Lovelace när nya paket läggs till.

### Steg 4: Lägg till Lovelace-vyn

Se filen `lovelace-dashboard.yaml` i repot för komplett YAML. Kortversionen:

```yaml
# Inmatningsfält
- type: entities
  title: Lägg till paket
  entities:
    - entity: input_text.postnord_ny_forsandelse
      name: Sändningsnummer eller URL
    - entity: input_text.postnord_agare
      name: Vems paket?

# Knapp
- type: button
  name: Lägg till paket
  icon: mdi:plus-circle-outline
  tap_action:
    action: call-service
    service: script.postnord_lagg_till_paket

# Alla aktiva paket (kräver auto-entities)
- type: custom:auto-entities
  filter:
    include:
      - integration: postnord
        attributes:
          postnord_sensor_type: package
    exclude:
      - state: DELIVERED
      - state: RETURNED
      - state: EXPIRED
      - state: unavailable
      - state: unknown
  sort:
    method: attribute
    attribute: eta_timestamp
    numeric: true
  card:
    type: entities
    title: Pågående paket
  show_empty: false
```

### API-rate limits

| API | Max anrop/dag |
|-----|--------------|
| Track & Trace By ID V7 | 3 000 000 |
| Track Shipment URL | 350 000 |
| Delivery schedule (portal) | — (publik) |

Med standardinställningen (30 min) och 100 aktiva paket: ~4 800 anrop/dag — långt under gränsen.

---

## Sensorernas attribut

Varje paketsensor (`sensor.postnord_<ID>`) exponerar följande attribut:

| Attribut | Typ | Beskrivning |
|---|---|---|
| `postnord_sensor_type` | str | Alltid `"package"` — används för att filtrera i auto-entities |
| `tracking_id` | str | Sändningsnumret |
| `owner` | str | Fritext, t.ex. "Rasmus" |
| `tracking_url` | str \| None | Klickbar spårnings-URL |
| `status_header` | str | Kort statustext, t.ex. "Försändelsen transporteras" |
| `status_body` | str | Längre beskrivning av status |
| `eta` | str \| None | Beräknad leverans (ISO 8601) |
| `public_eta` | str \| None | Publik ETA |
| `eta_timestamp` | int \| None | ETA som Unix-timestamp (för sortering i Lovelace) |
| `delivery_date` | str \| None | Faktiskt leveransdatum (ISO 8601) |
| `risk_for_delay` | bool | PostNords eget fördröjningsflagga |
| `is_delayed` | bool | `True` om `risk_for_delay` ELLER om ETA passerats utan leverans |
| `sender` | str | Avsändarens namn, t.ex. "Jula Sverige AB" |
| `service` | str | Tjänstenamn, t.ex. "Varubrev 1:a-klass" |
| `delivery_type` | str | `SERVICE_POINT` / `PARCEL_BOX` / `HOME` / `MAILBOX` / `UNKNOWN` |
| `pickup_location` | str \| None | Namn + adress på ombud/utlämningsställe |
| `last_event` | str \| None | Senaste händelse (tid, beskrivning, plats) |
| `country` | str | Landkod: `SE`, `NO`, `FI`, `DK` |
| `archived` | bool | `True` = paketet är levererat, pollas inte längre |

> **OBS om booleaner i auto-entities:** auto-entities anropar `.startsWith()` på alla filtervärden och kraschar om värdet är ett booleskt `true`/`false`. Filtrera därför **aldrig** på `archived`, `is_delayed` eller `risk_for_delay` i auto-entities. Använd istället state-baserade filter (se kortexemplen nedan).

### Möjliga statusvärden (state)

Dessa kommer direkt från PostNords API:

| Status | Betydelse |
|---|---|
| `INFORMED` | Avisering mottagen |
| `EN_ROUTE` | På väg |
| `IN_TRANSIT` | Under transport |
| `AVAILABLE_FOR_PICKUP` | Redo för uthämtning |
| `DELIVERED` | Levererat |
| `RETURNED` | Returnerat |
| `EXPIRED` | Utgånget |

### Brevutdelningssensor

Skapad om postnummer angavs vid konfiguration. Entitets-ID genereras av HA från namnet "Postlåda {postnummer}" — svenska tecken konverteras, så det faktiska ID:t kan bli t.ex. `sensor.postlada_87140`. Kontrollera det faktiska ID:t under **Inställningar → Enheter & tjänster → Entiteter**.

| Attribut | Beskrivning |
|---|---|
| `postnord_sensor_type` | Alltid `"mailbox"` — används för att exkludera i auto-entities-filter |
| `postal_code` | Postnummer |
| `city` | Ort |
| `last_delivery` | Senaste utdelningsdatum |
| `next_delivery` | Nästa utdelningsdatum |

---

## Lovelace-kort

### Krav

Kortexemplen använder antingen inbyggda HA-kort (inga krav) eller populära HACS-frontenddtillägg:
- **[Mushroom Cards](https://github.com/piitaya/lovelace-mushroom)** — moderna, snygga kort
- **[auto-entities](https://github.com/thomasloven/lovelace-auto-entities)** — visar entiteter dynamiskt baserat på filter

---

### Kort 1: Enkelt paket med klickbar spårningslänk (inbyggt)

Fungerar på alla HA-installationer via `markdown`-kortet:

```yaml
type: markdown
content: >
  ## {{ state_attr('sensor.uo553662591se', 'status_header') }}

  {{ state_attr('sensor.uo553662591se', 'status_body') }}

  | | |
  |---|---|
  | **Avsändare** | {{ state_attr('sensor.uo553662591se', 'sender') }} |
  | **Tjänst** | {{ state_attr('sensor.uo553662591se', 'service') }} |
  | **Senaste** | {{ state_attr('sensor.uo553662591se', 'last_event') }} |

  [🔗 Spåra paketet]({{ state_attr('sensor.uo553662591se', 'tracking_url') }})
```

---

### Kort 2: Klickbart entitetskort (inbyggt)

```yaml
type: entity
entity: sensor.uo553662591se
name: Jula-paket
tap_action:
  action: more-info
```

> **Obs:** `tap_action: url` med Jinja2-template fungerar inte i HA:s inbyggda kort — URL:en URL-kodas istället för att renderas. Använd `more-info` (detaljpanelen visar spårningslänken) eller `markdown`-kortet (Kort 1) för en klickbar länk.

---

### Kort 3: Mushroom template-kort (kräver Mushroom)

```yaml
type: custom:mushroom-template-card
primary: "{{ state_attr('sensor.uo553662591se', 'status_header') }}"
secondary: >
  {% set sender = state_attr('sensor.uo553662591se', 'sender') %}
  {% set eta = state_attr('sensor.uo553662591se', 'eta') %}
  {% if sender %}{{ sender }}{% endif %}
  {%- if sender and eta %} · {% endif %}
  {%- if eta %}{{ eta[:10] }}{% endif %}
icon: mdi:package-variant
icon_color: >
  {% if state_attr('sensor.uo553662591se', 'is_delayed') %}red
  {% elif states('sensor.uo553662591se') == 'AVAILABLE_FOR_PICKUP' %}green
  {% else %}blue{% endif %}
tap_action:
  action: more-info
```

> **Obs:** `tap_action: url` med Jinja2-template fungerar inte i mushroom-template-card — mallen URL-kodas istället för att renderas. Använd `more-info` (detaljpanelen innehåller spårningslänken) eller Kort 1 (`markdown`) för en direkt länk.

---

### Kort 4: Alla aktiva paket — rik vy med Mushroom (kräver auto-entities + Mushroom)

Visar alla aktiva paket som mushroom-template-cards med dynamisk ikon, färg, avsändare och beräknat leveransdatum. Sorteras automatiskt på närmast ETA. Försenade paket markeras i rött.

```yaml
type: custom:auto-entities
filter:
  include:
    - integration: postnord
      attributes:
        postnord_sensor_type: package
      options:
        type: custom:mushroom-template-card
        primary: >
          {{ state_attr(entity, 'status_header') or state_attr(entity, 'tracking_id') }}
        secondary: >
          {% set sender = state_attr(entity, 'sender') %}
          {% set eta = state_attr(entity, 'eta') %}
          {% if sender %}{{ sender }}{% endif %}
          {%- if sender and eta %} · {% endif %}
          {%- if eta %}{{ eta[:10] }}{% endif %}
        icon: >
          {% set s = states(entity) %}
          {% set d = state_attr(entity, 'delivery_type') %}
          {% if s == 'DELIVERED' %}mdi:package-variant-closed-check
          {% elif state_attr(entity, 'is_delayed') %}mdi:clock-alert-outline
          {% elif d == 'SERVICE_POINT' and s == 'AVAILABLE_FOR_PICKUP' %}mdi:store-marker
          {% elif d == 'PARCEL_BOX' and s == 'AVAILABLE_FOR_PICKUP' %}mdi:mailbox-open-up
          {% elif d == 'MAILBOX' %}mdi:email-fast-outline
          {% elif d == 'HOME' %}mdi:truck-delivery-outline
          {% else %}mdi:truck-delivery{% endif %}
        icon_color: >
          {% if state_attr(entity, 'is_delayed') %}red
          {% elif states(entity) == 'AVAILABLE_FOR_PICKUP' %}green
          {% else %}blue{% endif %}
        tap_action:
          action: more-info
  exclude:
    - state: DELIVERED
    - state: RETURNED
    - state: EXPIRED
    - state: unavailable
    - state: unknown
sort:
  method: attribute
  attribute: eta_timestamp
  numeric: true
card:
  type: vertical-stack
card_param: cards
show_empty: false
```

#### Enklare alternativ utan Mushroom (inbyggt)

Om du inte har Mushroom installerat fungerar detta enkla alternativ:

```yaml
type: custom:auto-entities
filter:
  include:
    - integration: postnord
      attributes:
        postnord_sensor_type: package
  exclude:
    - state: DELIVERED
    - state: RETURNED
    - state: EXPIRED
    - state: unavailable
    - state: unknown
sort:
  method: attribute
  attribute: eta_timestamp
  numeric: true
card:
  type: entities
  title: Aktiva paket
show_empty: false
```

---

### Kort 5: Grupperat per leveranstyp (kräver auto-entities)

`delivery_type` är en sträng och fungerar i auto-entities. Brevutdelningssensorn filtreras automatiskt bort eftersom den inte har dessa delivery_type-värden.

```yaml
type: vertical-stack
cards:
  - type: custom:auto-entities
    filter:
      include:
        - integration: postnord
          attributes:
            delivery_type: SERVICE_POINT
      exclude:
        - state: DELIVERED
    card:
      type: entities
      title: Uthämtning på ombud
      icon: mdi:store-marker
    show_empty: false

  - type: custom:auto-entities
    filter:
      include:
        - integration: postnord
          attributes:
            delivery_type: MAILBOX
      exclude:
        - state: DELIVERED
    card:
      type: entities
      title: Brevlådepost
      icon: mdi:mailbox
    show_empty: false

  - type: custom:auto-entities
    filter:
      include:
        - integration: postnord
          attributes:
            delivery_type: HOME
      exclude:
        - state: DELIVERED
    card:
      type: entities
      title: Hemleverans
      icon: mdi:truck-delivery-outline
    show_empty: false
```

---

### Kort 6: Levererade paket (kräver auto-entities)

```yaml
type: custom:auto-entities
filter:
  include:
    - integration: postnord
      attributes:
        postnord_sensor_type: package
      state: DELIVERED
card:
  type: entities
  title: Levererade paket
  icon: mdi:package-variant-closed-check
show_empty: false
```

> **OBS:** Det går inte att filtrera på `is_delayed: true` i auto-entities (boolean-krasch). Försenade paket visas automatiskt med ⚠️-ikonen i den aktiva listan.

---

### Kort 7: Brevutdelning (inbyggt)

Kontrollera det faktiska entitets-ID:t under **Inställningar → Enheter & tjänster → Entiteter** — HA konverterar svenska tecken (t.ex. `sensor.postlada_87140`).

```yaml
type: glance
title: Brevlåda
entities:
  - entity: sensor.postlada_87140   # Byt mot ditt faktiska entitets-ID
    name: Nästa utdelning
    icon: mdi:mailbox
```

---

### Kort 8: Paket per person (kräver auto-entities)

`owner` är en sträng och fungerar som filter.

```yaml
type: custom:auto-entities
filter:
  include:
    - integration: postnord
      attributes:
        postnord_sensor_type: package
        owner: Rasmus
  exclude:
    - state: DELIVERED
    - state: RETURNED
    - state: EXPIRED
card:
  type: entities
  title: Rasmus paket
show_empty: false
```

---

### Automation: Avisering när paket levererats

```yaml
alias: PostNord – paket levererat
trigger:
  - platform: state
    entity_id:
      - sensor.uo553662591se
    to: DELIVERED
action:
  - service: notify.mobile_app_din_telefon
    data:
      title: "📦 Paket levererat!"
      message: >
        {{ state_attr(trigger.entity_id, 'status_header') }}
        Avsändare: {{ state_attr(trigger.entity_id, 'sender') }}
```

---

## CLI-verktyget (`track.py`)

Används för att testa och utforska PostNords API direkt i terminalen.

```bash
# Spåra ett paket
python track.py --apikey DIN_NYCKEL UO553662591SE

# Visa rå JSON
python track.py --apikey DIN_NYCKEL --raw UO553662591SE

# Visa utan spårnings-URL
python track.py --apikey DIN_NYCKEL --no-url UO553662591SE

# Visa nästa brevutdelning för ett postnummer
python track.py delivery 87140

# API-nyckel kan sparas i filen api.key (gitignorerad)
python track.py UO553662591SE
```

---

## Projektstruktur

```
postnord-playground/
├── track.py                              # CLI-testverktyg
├── api.key                               # Din API-nyckel (gitignorerad)
├── hacs.json                             # HACS-metadata
├── lovelace-dashboard.yaml               # Komplett dashboard-YAML med instruktioner
└── custom_components/
    └── postnord/
        ├── __init__.py                   # Integrationens setup/unload
        │                                 # + tjänsterna add_package / remove_package
        ├── manifest.json                 # HA-metadata
        ├── const.py                      # Alla konstanter och nyckelnamn
        ├── api.py                        # Async HTTP-klient (aiohttp)
        │                                 # + parse_tracking_input() för URL-tolkning
        ├── coordinator.py                # DataUpdateCoordinator
        │                                 # PostNordCoordinator – paketspårning
        │                                 # MailboxCoordinator – brevutdelning
        ├── sensor.py                     # PostNordSensor + PostNordMailboxSensor
        ├── config_flow.py                # ConfigFlow + OptionsFlow (meny-baserat)
        ├── services.yaml                 # Tjänstedefinitioner (syns i Utvecklarverktyg)
        ├── strings.json                  # UI-strängar (kanonisk källa)
        └── translations/
            ├── sv.json                   # Svenska
            └── en.json                   # Engelska
```

### Nyckeldesignbeslut

**Arkivering av levererade paket:** När ett paket får status `DELIVERED` sätts `archived = True` i koordinatorns cache. Paketet pollas aldrig mer — data fryses vid senast kända tillstånd. Sensorn finns kvar tills användaren manuellt tar bort paketet via Inställningar → Konfigurera.

**URL-tolkning:** `parse_tracking_input()` i `api.py` extraherar sändningsnummer från PostNords obfuskerade URL-format. Mönstret: `?id=prefix:seg1:hash:seg2:hash:hash:hash:seg3` → ID = `(seg1 + seg2 + seg3).upper()`. Verifierat mot tre riktiga paket.

**Leveranstypsdetektering** (prioritetsordning):
1. `items[].isPlacedInRetailParcelBox` → `PARCEL_BOX`
2. `deliveryPoint.servicePointType` finns → `SERVICE_POINT`
3. Tjänstnamn innehåller nyckelord → `SERVICE_POINT` / `MAILBOX` / `HOME`
4. Fallback → `UNKNOWN` (hanteras alltid, påverkar bara ikon)

**Ikonmatris:** Ikonen beräknas från `delivery_type × status` (se `sensor.py:_ICON_RULES`). Fördröjda paket (`is_delayed=True`) åsidosätter övriga regler.

**`postnord_sensor_type`-attributet:** Båda sensortyperna exponerar ett strängattribut `postnord_sensor_type` (`"package"` eller `"mailbox"`). Det används uteslutande för att filtrera i auto-entities-kort. Bakgrunden: auto-entities anropar `.startsWith()` på alla filtervärden och kraschar på booleaner (`true`/`false`), och entity_id-baserad glob-filtrering är opålitlig eftersom HA konverterar svenska tecken i namn (t.ex. `Postlåda` → `postlada`). Strängattribut är den enda robusta lösningen.

**Alternativflöde:** Menybaserat med fyra val: Lägg till paket / Ta bort paket / Ändra intervall / Ändra postnummer. Ändringar triggar automatisk reload av integrationen via `update_listener`.

---

## För AI-agenter som arbetar med detta repo

### Viktiga filer att läsa

- `track.py` — referensimplementation med alla API-anropsformat och svarsfältnamn
- `custom_components/postnord/const.py` — alla konstantnamn, ändra aldrig direkt i andra filer
- `custom_components/postnord/coordinator.py` — `PackageData`-dataklassen definierar sensorns datamodell

### Vanliga uppgifter

**Lägga till en ny HA-tjänst:**
1. Definiera schema och handler i `__init__.py` (se `_register_services()`)
2. Lägg till beskrivning i `services.yaml`

**Lägga till ett nytt sensorattribut:**
1. Lägg till konstant i `const.py`: `ATTR_NYTT = "nytt"`
2. Lägg till fältet i `PackageData` dataclass i `coordinator.py`
3. Populera fältet i `_parse_shipment()` i `coordinator.py`
4. Exponera attributet i `extra_state_attributes` i `sensor.py`

**Lägga till ny leveranstyp:**
1. Lägg till konstant i `const.py`: `DELIVERY_TYPE_X = "X"`
2. Lägg till detekteringslogik i `_detect_delivery_type()` i `coordinator.py`
3. Lägg till ikonregel i `_ICON_RULES` i `sensor.py`

**Lägga till nytt API-anrop:**
1. Implementera async-metod i `PostNordApiClient` i `api.py`
2. Anropa från `coordinator.py`

**Ändra alternativflödet:**
- Alla steg definieras i `config_flow.py` i `PostNordOptionsFlow`
- Menyalternativen i `async_step_init()` måste matcha metodnamnen `async_step_<val>()`
- Strängar för nya steg läggs till i `strings.json` och båda `translations/*.json`

### API-endpoints

| Endpoint | Beskrivning | Nyckel krävs |
|---|---|---|
| `GET https://api2.postnord.com/rest/shipment/v7/trackandtrace/id/{id}/public` | Spårningsdata | Ja |
| `GET https://api2.postnord.com/rest/links/v1/tracking/{country}/{id}` | Spårnings-URL | Ja |
| `GET https://portal.postnord.com/api/sendoutarrival/closest?postalCode={kod}` | Brevutdelningsschema | Nej |

Parametrar: `apikey`, `locale` (sv/no/fi/da), `language`, `country` (SE/NO/FI/DK).

API-svarstruktur: `TrackingInformationResponse.shipments[0]` innehåller all spårningsdata. Se `track.py:print_result()` för en komplett utskrift av alla fält.
