# TailWatch — Design Document for Coding Agents

Status: implementable MVP  
Hardware target: Adafruit MatrixPortal S3 + indoor P2 SMD1515 128×64 HUB75 panel  
Companion: optional Cloudflare Worker (or small VPS) for ADS-B enrichment  
Existing starter: `artifacts/tailwatch-s3/` (`code.py`, `lib/*`, `www/index.html`, `prefs.example.json`)

This document is the spec. Do not invent product scope beyond it. Prefer small, working slices over frameworks.

---

## 1. Goal

A wall display that shows **one live aircraft card** for traffic near a user-configured GPS point, without requiring a subscription app.

Two physical units will exist (owner + friend). Each unit owns its own lat/lon and display prefs on-device. A shared cloud API supplies flight cards and logos. OpenSky (or compatible ADS-B) is the position source.

## 2. Non-goals (MVP)

- Multi-aircraft list or map on the LED panel
- On-device SQLite of the global fleet
- Captive-portal polish matching consumer routers
- Official airline trademark licensing (use simple letter marks / public-domain style sprites)
- Bonjour across the internet
- Driving more than one 128×64 panel
- Pi Pico / Pi Zero in v1 (allowed later; do not block S3-only path)

## 3. Hardware and power

| Piece | Spec |
|---|---|
| Controller | Adafruit MatrixPortal S3 (ESP32-S3, USB-C, HUB75, Wi-Fi) |
| Panel | P2-1515, 128×64, 256×128 mm, 1/32 scan, HUB75 |
| Panel power | External 5.0 V bench/PSU, **direct to panel**, ~3 A measured full white (~15 W), budget 4–5 A |
| S3 power | USB-C only (board + logic). Do not back-feed USB from panel 5 V |
| Wiring | HUB75 data from S3; panel 5 V/GND from PSU; common ground optional if noise appears |

Firmware must never assume USB can power the LEDs.

## 4. Architecture

```
[Phone browser]
    |  http://<s3-ip>/  or 192.168.4.1  (prefs only)
[MatrixPortal S3]
    |  GET /v1/nearby?lat&lon&nm   Authorization: Bearer <token>
    |  GET /v1/logo/<id>           raw 16×16 RGB565
[Cloud API: CF Worker or Linode]
    |  cached cell poll
[OpenSky / ADS-B]
    + local lookup tables (aircraft type, airline prefix, airports)
```

**On device (source of truth):** GPS, radius, brightness, sleep, night mode, filters, API URL, token.  
**In cloud (shared, stateless except cache):** positions, enrichment, logos.  
**Never store friend lat/lon as the only copy in the cloud** — cloud may see lat/lon as query params for a fetch, and may cache a grid cell, but the device prefs file wins after reboot.

## 5. Device identity (two units)

- `device_token` stored in `/prefs.json` on each S3
- Cloud validates token (rate-limit per token)
- Tokens do not share prefs
- Same firmware image on both units
- Optional `device_id` printed on serial at boot for support

Provisioning MVP: owner pastes token + API URL in the local settings page. No account system required for two devices.

## 6. Preferences (on-device)

File: `/prefs.json` with `/prefs.bak` on write.

```json
{
  "lat": 30.2094,
  "lon": -95.7508,
  "nm": 10,
  "hide_heli": true,
  "hide_ga": false,
  "hide_mil": true,
  "brightness_day": 0.70,
  "brightness_night": 0.18,
  "brightness_max": 1.00,
  "night_mode": "sunset",
  "night_start": "21:00",
  "night_end": "06:30",
  "sleep_enabled": true,
  "sleep_start": "23:00",
  "sleep_end": "06:30",
  "tz_offset_min": -360,
  "us_dst": true,
  "api": "https://api.example.com",
  "token": ""
}
```

Rules:

- `nm` is miles **in each direction** (square bbox), clamp 1–50
- brightness fields 0.0–1.0; day/night clamped to `brightness_max`
- `night_mode`: `off` | `fixed` | `sunset`
- sleep and night mode are independent: sleep blanks the panel; night only dims
- booleans from HTML checkboxes: missing key on POST means `false`
- JSON POSTs are partial merges: omitted keys (including booleans) keep their stored value; JSON booleans are used as-is
- `tz_offset_min` + `us_dst` used for sleep/fixed night windows (lib/tz.py, fixed US DST rule only); sunset uses lat/lon solar math (UTC timestamps)

Apply prefs immediately on save except Wi-Fi credentials (Wi-Fi stays in `settings.toml` for MVP).

### Bounding box

```
dlat = nm / 69.0
dlon = nm / (69.0 * cos(lat_rad))
lamin, lamax = lat ± dlat
lomin, lomax = lon ± dlon
```

Existing helper: `lib/bbox.py`.

### Schedule

Existing helpers: `lib/sun.py`, `lib/schedule.py`.

Every ~1 s (or on prefs save):

1. If sleep window → `display.brightness = 0`, skip network poll
2. Else if night → `min(brightness_night, brightness_max)`
3. Else → `min(brightness_day, brightness_max)`

NTP at boot (UTC into RTC). The RTC and `sun.py` stay UTC. `schedule.py` computes local time as UTC + `tz_offset_min` (+60 min under the fixed US DST rule when `us_dst`) via `lib/tz.py`. No tz database: only the fixed US rule is supported.

## 7. Local web UI

Static files in `/www`. Server: `adafruit_httpserver` on port 80. Web Workflow
(CIRCUITPY_WEB_API_PASSWORD) must stay disabled -- it also binds port 80 and
exposes the filesystem.

| Route | Method | Purpose |
|---|---|---|
| `/` | GET | `www/index.html` |
| `/api/prefs` | GET | current JSON |
| `/api/prefs` | POST | form or JSON merge → save → apply brightness |

UI fields must match the schema in §6 (already drafted in `www/index.html`).

MVP discovery: print IPv4 on serial and on the LED (`SETUP 192.168.x.x`) if no card yet. mDNS `tailwatch.local` is a stretch goal (CircuitPython support is uneven).

### AP mode (first boot)

If `CIRCUITPY_WIFI_SSID` empty or join fails for 20 s:

- Start AP `TailWatch-XXXX` (last 4 of MAC)
- Serve the same UI at `192.168.4.1`
- Prefs save still writes `/prefs.json`
- Wi-Fi SSID/password write to `settings.toml` is optional in MVP; if too risky on live CIRCUITPY, collect Wi-Fi in prefs and document a manual `settings.toml` step

Hold BOOT 5 s to clear Wi-Fi settings is a stretch goal.

## 8. Cloud API

Base URL from `prefs.api`. HTTPS only.

### `GET /v1/nearby`

Query: `lat` `lon` `nm`  
Optional: `hide_heli` `hide_ga` `hide_mil`  
Header: `Authorization: Bearer <token>`

Response (always small):

```json
{
  "ok": true,
  "flight": "ASA331",
  "airline": "Alaska",
  "logo": "asa",
  "route": "PDX-LAX",
  "type": "737 MAX 9",
  "city": "Portland Intl",
  "phase": "arriving",
  "alt": 11200,
  "spd": 342,
  "track": 175,
  "hex": "a1b2c3",
  "age_s": 8
}
```

Empty sky: `ok: true`, `flight: null`.  
Errors: HTTP 401/429/502 with `{"ok": false, "error": "..."}`.

Hero aircraft selection (server):

1. Positions in bbox, airborne (`on_ground` false)
2. Apply hide_* filters
3. Prefer closest to pin; tie-break lower altitude then higher speed
4. Enrich hex → type/reg; callsign prefix → airline + logo id; route cache → OD pair + city + arriving/departing if possible
5. If enrichment missing, still return callsign + alt + spd

### `GET /v1/logo/{id}`

Raw 16×16 RGB565 little-endian (512 bytes) or a documented alternative the S3 already decodes. No PNG on the device.

### Caching

Snap lat/lon to a grid (~10 mi) so two nearby devices share one OpenSky fetch. TTL 10–15 s for positions, hours for hex→type, forever for logos.

Do not call `states/all` without a bbox. Honor OpenSky rate limits and non-commercial terms. Store OpenSky credentials only on the server.

### Worker vs VPS

MVP: Cloudflare Worker + KV/R2 is enough for two devices. Linode if FlightAware AeroAPI + SQLite is added later. Coding agent should define a clean interface (`nearby(lat,lon,nm,filters) → card`) so the backend can be swapped.

## 9. Firmware modules

| Module | Role | Status |
|---|---|---|
| `lib/prefs.py` | load/save/clamp/form merge | exists |
| `lib/sun.py` | sunrise/sunset | exists |
| `lib/schedule.py` | sleep/night/brightness | exists |
| `lib/bbox.py` | OpenSky box | exists |
| `www/index.html` | settings UI | exists |
| `code.py` | matrix, HTTP, poll loop | stub |
| `lib/card.py` | render 128×64 card | **to build** |
| `lib/net.py` | HTTPS GET nearby + logo | **to build** |
| `lib/filters.py` | local filter if API returns a list | optional |

### Display card (128×64)

Layout (pixel budget):

```
+------------------+----------------------------+
| 16×16 logo       | Airline                     |
|                  | FLIGHT  ROUTE               |
+------------------+ TYPE                        |
| city / phase                               |
| ALT  SPD  TRK                              |
+--------------------------------------------+
```

- Font: `terminalio.FONT` or a bundled 5×7 / 6×12 bitmap font
- Colors: white text, dim gray labels, logo as-is
- Sleep: empty group / brightness 0
- No data: `NO TRAFFIC` + local time
- Error: `NO LINK` (do not crash the HTTP server)

`bit_depth=3` or `4` is enough. Do not use depth 6+ on this panel for MVP.

### Poll loop

- `server.poll()` every iteration
- ADS-B poll every 15 s when not sleeping
- Timeouts on HTTP (5–8 s); keep last good card
- Never block the UI server for more than one poll

## 10. Filters

Heuristic MVP (document as imperfect):

- helicopter: OpenSky category rotorcraft / type prefix `H` / known heli ICAO types
- military: hex or callsign on a small blocklist file on the server
- GA: not in airline-prefix table and not airliner type prefixes (`B73`, `B78`, `A32`, `E17`, …)

If `hide_ga` is true in a 10-mile Magnolia box, the board may be empty often (Hooks GA). Default `hide_ga: false`.

## 11. Security

- Device token required for cloud
- Local UI has no auth in MVP (LAN trust). Do not expose the S3 port to WAN
- No OpenSky password on the S3
- CIRCUITPY is writable; do not put secrets in git

## 12. Implementation order (coding agent)

Do these PRs/slices in order. Each slice must run on hardware or have a clear mock.

1. **Harden existing prefs + UI** — POST from `application/x-www-form-urlencoded` reliably; checkbox false when unchecked; backup file; serial log of saved JSON  
2. **Card renderer** — hardcoded Alaska/PDX-LAX style card on 128×64  
3. **Schedule live** — sliders change brightness immediately; sleep blanks panel; sunset path uses saved lat/lon  
4. **HTTPS client** — `poll_card()` hits `prefs.api` with token + lat/lon/nm; parse JSON; render  
5. **Logo fetch + cache** — one logo in memory; 404 → letter avatar  
6. **Cloud Worker** — token check, bbox, OpenSky, pick hero, return card JSON; empty-sky path  
7. **Lookup tables** — airline prefixes + airport names + a few logos  
8. **AP fallback** — if no Wi-Fi  
9. **Second device** — second token, confirm prefs isolated  

Do not start a rewrite in ESP-IDF unless CircuitPython HTTPS + HTTP server cannot coexist. If it cannot, port modules 1:1 to Arduino/ESP-IDF and keep this spec.

## 13. Acceptance tests

- Full-white bench test previously ~15 W @ 5 V; firmware must not change power wiring
- Save lat/lon from phone on same LAN; reboot; values persist
- 10 mi box print/serial matches formula in §6
- Sleep window: panel dark, no nearby requests
- After sunset (or forced `night_mode=fixed`): brightness equals night slider, ≤ max
- Two tokens cannot read each other’s saved device prefs (none stored as owner data in MVP)
- Invalid API: panel shows `NO LINK`, settings page still loads
- Empty bbox: `NO TRAFFIC`, not a crash
- Friend can set a different pin without firmware fork

## 14. Repo / files

Keep under `artifacts/tailwatch-s3/` unless the agent is given another root.

```
code.py
settings.toml.example
prefs.example.json
www/index.html
lib/prefs.py
lib/sun.py
lib/schedule.py
lib/bbox.py
lib/card.py          # new
lib/net.py           # new
DESIGN.md            # this file
README.md
```

Cloud worker may live in `artifacts/tailwatch-api/` when started.

## 15. Coding rules for the agent

- CircuitPython-compatible: no f-string heavy deps, no `pathlib` assumptions that fail on CP
- Avoid large allocations in the poll path
- Do not add Google/FlightRadar scraped APIs
- Do not commit tokens
- Match existing helper APIs rather than renaming without cause
- When unsure of MatrixPortal pin names, use `board.MTX_*` as in current `code.py`
- Update README with any new library bundle names

## 16. Reference context

- Product look: airline logo, flight number, city pair, aircraft type, arriving/departing city
- Open data: OpenSky Network state vectors in a bbox
- Enrichment later: FlightAware AeroAPI (paid, server-only)
- Starter firmware already serves `/api/prefs` and computes brightness/sleep/sunset
