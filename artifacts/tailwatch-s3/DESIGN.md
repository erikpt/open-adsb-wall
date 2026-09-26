# TailWatch — Design Document for Coding Agents

Status: implementable MVP  
Hardware target: Adafruit MatrixPortal S3 + indoor P2 SMD1515 128×64 HUB75 panel  
Companion: none -- the device calls OpenSky directly and assembles cards on-device (see issue #2; no cloud API)  
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
    |  lib/net.py: GET /api/states/all?lamin&lomin&lamax&lomax&extended=1
    |  (OpenSky token optional, only to raise the anonymous rate limit)
[OpenSky / ADS-B]
    + on-device lib/hero.py, lib/filters.py, lib/enrich.py, lib/logos/
```

No cloud tier (issue #2): each device polls OpenSky directly with its own
bbox and assembles/filters/enriches the card locally.

**On device (everything; no cloud copy of anything):** GPS, radius, brightness, sleep, night mode, filters, OpenSky token (optional), positions (fetched live, never persisted), enrichment tables, badges.

## 5. Device identity (two units)

- Each unit's `/prefs.json` (lat/lon, filters, OpenSky token) is entirely local -- nothing is shared or centrally stored, so there's no cross-device isolation to get wrong
- Same firmware image on both units
- Optional `device_id` printed on serial at boot for support

Provisioning MVP: owner pastes token + API URL in the local settings page. No account system required for two devices.

## 6. Preferences (on-device)

File: `/prefs.json` with `/prefs.bak` on write.

```json
{
  "lat": 30.0000,
  "lon": -95.0000,
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

Dimming is done by scaling draw colours (`lib/dim.py` Dimmer). `display.brightness` is on/off on rgbmatrix, so it stays 1.0 while awake and 0.0 only for the black sleep state (blank group).

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

## 8. On-device card assembly (was "Cloud API")

Superseded by issue #2: there is no server. `lib/net.py` (to build) calls
OpenSky's `/api/states/all` directly with the device's own bbox (`lib/bbox.py`)
and `extended=1`, then `lib/hero.py`, `lib/filters.py`, and `lib/enrich.py`
assemble a card with this same shape on-device, for `lib/card.py` to render.
`prefs.api`/`prefs.token` (an OpenSky account, not a "cloud API" of ours) are
only needed if OpenSky's anonymous rate limit proves too low in practice.

Card shape (assembled on-device, not an HTTP response):

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
Fetch failure (OpenSky unreachable, rate-limited, or malformed response):
`lib/net.py` returns `None`/raises rather than an HTTP error code; `lib/hero.py`
treats a failed poll as "no fresh candidates" (see `Hero.expired()`), not as
"the hero left the box".

Hero aircraft selection (on-device, `lib/hero.py`; see issue #2 — the S3 calls
OpenSky directly, so this runs on-device instead of on the server as originally
sketched here):

1. Positions in bbox, airborne (`on_ground` false); `lib/hero.py:candidates()`
   turns the raw OpenSky state vectors into candidate dicts, skipping ground
   traffic, rows without a position, and malformed rows.
2. Apply hide_* filters (`lib/filters.py:apply()`, on-device, issue #2; a
   filtered-out hero is treated as rule (b), "gone")
3. Prefer closest to pin; tie-break lower altitude then higher speed
   (`lib/hero.py:_rank`)
4. Enrich hex → type/reg; callsign prefix → airline + badge id (`lib/enrich.py:lookup()`,
   on-device, issue #2); route cache → OD pair + city + arriving/departing if possible
5. If enrichment missing, still return callsign + alt + spd

**`extended=1` is required.** `lib/net.py`'s OpenSky request must add
`&extended=1`, or every state vector's category comes back `None`: helicopters
are never detected (`lib/filters.py:is_heli()` only matches category 8) and
`is_ga()` falls back to the callsign-shape heuristic for everything.

**Hysteresis / hold** — the shown aircraft is tracked by ICAO hex and only
changes when one of these fires (`lib/hero.py:select()`, called each poll by
the `Hero` class):

- **(a) Closer.** A challenger must be at least 20 % closer *and* at least
  0.5 mi closer than the current hero, and the current hero must have been
  shown for at least 30 s (`SWITCH_RATIO`, `MIN_GAP_MI`, `MIN_DWELL_S`).
  - 20 %: at 15 s polls a jet at ~250 kt covers ~1.2 mi/poll; in a 10 mi box,
    20 % of a typical 5 mi distance is ~1 mi, comfortably above OpenSky's
    position-delay jitter (~0.3–0.4 mi), so noise alone can't trigger a swap.
  - Swapping back needs the old hero to become ~36 % closer than it was,
    which takes real movement, not noise — so a switch does not bounce back.
  - 0.5 mi minimum: near the pin, 20 % is smaller than position noise, so an
    absolute floor is also required.
  - 30 s = two polls at the 15 s poll interval, so the card stays up long
    enough to read; it has no effect once polls are >= 30 s.
- **(b) Gone.** The hero's hex is absent from a *successful* OpenSky
  response: it left the box, landed (`on_ground`), was filtered out, or went
  out of coverage.
- **(c) Too old.** Limit is `3 * poll_s`, clamped to 30–90 s (45 s at the
  current 15 s poll interval; `lib/hero.py:stale_limit()`). Either:
  - the position in the data is too old (response `time` minus
    `time_position`, or `last_contact` when that's missing), or
  - no successful poll has confirmed the hero within that limit
    (`Hero.expired(now)`, for repeated fetch failures).
  - The 90 s cap exists because a plane at 250 kt moves ~6 mi in 90 s, past
    which the card would be misleading.

When there is no current hero, the closest candidate is picked (same
tie-break as above). Distances are statute miles, matching `lib/bbox.py`
(69 mi/degree) and the prefs `nm` field, which despite its name is also miles
each way.

### Badges (was `GET /v1/logo/{id}`)

Superseded (issue #2): airline badges are no longer fetched from the cloud.
`tools/gen_badges.py` (host-only, stdlib-only, Pillow-free generator) bakes 50
24×24, 4-bit indexed BMP tiles into `lib/logos/<key>.bmp` at build time, one per
`lib/enrich.py:AIRLINES` entry plus a generic fallback (`_unk.bmp`). All 50
badges together are 17,700 bytes (354 bytes each); on the board's 512-byte
FAT clusters that's ~25 KB, comfortably inside the 8 MB flash. Only one badge
is loaded into RAM at a time (~288 bytes). `lib/enrich.py:badge_path()` maps a
lookup to its file path; `lib/card.py` loads it with `adafruit_imageload.load()`
or `displayio.OnDiskBitmap()`. No PNG, no network round-trip, no server.

### Rate limits

No shared cache: each device polls independently with its own bbox (the two
owners' units are in different cities, so a shared cache never had a hit
anyway -- see issue #2). Do not call `states/all` without a bbox. Honor
OpenSky's rate limits and non-commercial terms; `prefs.token` (optional
OpenSky account credentials) raises the anonymous limit if needed. Badges
need no cache: they are static files already on the drive.

## 9. Firmware modules

| Module | Role | Status |
|---|---|---|
| `lib/prefs.py` | load/save/clamp/form merge | exists |
| `lib/sun.py` | sunrise/sunset | exists |
| `lib/schedule.py` | sleep/night/brightness | exists |
| `lib/bbox.py` | OpenSky box | exists |
| `lib/dim.py` | colour-scale dimming + sleep blank | exists |
| `lib/tz.py` | UTC offset + fixed US DST rule | exists |
| `lib/urldecode.py` | percent-decode form bodies | exists |
| `lib/buttons.py` | hold-to-trigger button helper | exists |
| `lib/nyan.py` | easter egg animation | exists |
| `lib/hero.py` | hero-aircraft selection + hysteresis (on-device, issue #2) | exists |
| `lib/enrich.py` | callsign → airline name + badge key/path, on-device (issue #2) | exists |
| `lib/filters.py` | on-device hide_heli / hide_mil / hide_ga (issue #2; §10) | exists |
| `www/index.html` | settings UI | exists |
| `code.py` | matrix, HTTP, poll loop | stub |
| `lib/card.py` | render 128×64 card | **to build** |
| `lib/net.py` | HTTPS GET nearby (must pass `extended=1`; §8) | **to build** |

### Display card (128×64)

Layout (pixel budget):

```
+------------------+----------------------------+
| 24×24 badge      | Airline                     |
|                  | FLIGHT  ROUTE               |
+------------------+ TYPE                        |
| city / phase                               |
| ALT  SPD  TRK                              |
+--------------------------------------------+
```

- Badge: local `lib/logos/<key>.bmp` (24×24, 4-bit indexed), loaded via
  `adafruit_imageload.load()` or `displayio.OnDiskBitmap()` (§8, issue #2).
  Register one badge palette in `lib/dim.py` and overwrite its colours on
  each hero swap (`Dimmer.add_palette` only ever adds, so swapping badges by
  adding a fresh palette every poll would leak memory)
- Font: `terminalio.FONT` or a bundled 5×7 / 6×12 bitmap font
- Colors: white text, dim gray labels, badge as-is
- Sleep: empty group / brightness 0
- No data: `NO TRAFFIC` + local time
- Error: `NO LINK` (do not crash the HTTP server)

`bit_depth=4` (set via `BIT_DEPTH` in `code.py`); 3 gives only 7 lit levels per channel. Do not use 6+ for MVP.

### Poll loop

- `server.poll()` every iteration
- ADS-B poll every 15 s when not sleeping
- Timeouts on HTTP (5–8 s); keep last good card
- Never block the UI server for more than one poll

## 10. Filters

On-device (`lib/filters.py`, issue #2 — no server blocklist). Heuristic MVP,
documented as imperfect:

- **Helicopter (`is_heli`):** true only when OpenSky's ADS-B emitter
  `category == 8` (Rotorcraft). This field is state-vector index 17 and is
  only populated when the `/states/all` request includes `&extended=1`
  (`lib/net.py`, **to build**) — without it every category is `None` and no
  helicopter is ever detected. Category values: 0 no info, 1 no category info,
  2 Light, 3 Small, 4 Large, 5 High Vortex, 6 Heavy, 7 High Perf, 8 Rotorcraft,
  9 Glider, 10 Lighter-than-air, 11 Parachutist, 12 Ultralight, 14 UAV.
- **Military (`is_mil`):** the aircraft's ICAO 24-bit hex address against
  `MIL_RANGES`, a 32-entry table copied from readsb's `isMilRange()`
  (`wiedehopf/readsb` `aircraft.c`, commit 3b5368a — the same list tar1090
  uses), plus three US military callsign designators (`RCH`, `CNV`, `PAT`).
  The US range is `ADF7C8–AFFFFF`: US civil N-number registrations fill
  `A00001–ADF7C7` (N99999 = ADF7C7, 915,399 addresses), so everything above
  that in the US block is non-civil. Canada is `C20000–C3FFFF`. Known limit:
  the US range also holds some non-military federal aircraft.
- **GA (`is_ga`):** rules applied in order —
  1. Helicopter or military → not GA (keeps the three toggles independent).
  2. Callsign prefix in `lib/enrich.py:AIRLINES` → not GA (covers e.g. FedEx
     Caravan feeders, which fly as category 2 Light).
  3. Category 2, 9, 10, 11, 12, or 14 → GA.
  4. Category 4, 5, or 6 (airliner-sized) → not GA.
  5. Otherwise, GA only if the callsign is not airline-style (a bare tail
     number like `N123AB`, or no callsign at all).

  Known limit: a helicopter that never broadcasts a category shows as not a
  helicopter (falls through to the GA/airline heuristics instead).

`hidden(c, prefs)` returns `"heli"`, `"mil"`, `"ga"`, or `None`; `apply(cands,
prefs)` (used in the hero poll path, §8 step 2) returns the candidate list
unchanged when no filter is enabled. If `hide_ga` is true in a 10-mile
Magnolia box, the board may be empty often (Hooks GA). Default `hide_ga: false`.

## 11. Security

- No cloud tier, so no device/cloud token to manage (issue #2)
- Local UI has no auth in MVP (LAN trust). Do not expose the S3 port to WAN
- OpenSky token (optional, only to raise the anonymous rate limit) lives in `/prefs.json` on-device; `GET /api/prefs` must not echo it back (issue #14, open)
- CIRCUITPY is writable; do not put secrets in git

## 12. Implementation order (coding agent)

Do these PRs/slices in order. Each slice must run on hardware or have a clear mock.

1. ~~**Harden existing prefs + UI**~~ — done (issues #4, #5)
2. **Card renderer** — `lib/card.py`, hardcoded style card on 128×64 -- **to build**
3. ~~**Schedule live**~~ — done (issue #7); ~~**Brightness dimming**~~ — done (issue #8)
4. **OpenSky HTTPS client** — `lib/net.py`: `poll_card()` hits OpenSky's `/api/states/all` directly with bbox + `extended=1`, optional token; parse JSON -- **to build**
5. ~~**Lookup tables + badges**~~ — done (issue #10: `lib/enrich.py`, `lib/filters.py`, `lib/logos/`)
6. ~~**Hero selection**~~ — done (issue #9: `lib/hero.py`)
7. **AP fallback** — if no Wi-Fi (issue #11, in progress)
8. **Wire it together** — `code.py`'s poll loop calls `lib/net.py` → `lib/filters.py` → `lib/hero.py` → `lib/card.py`, replacing the current stub  

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
lib/dim.py
lib/hero.py
lib/enrich.py        # new (issue #2: on-device airline lookup)
lib/filters.py       # new (issue #2: on-device heli/mil/ga filters)
lib/logos/*.bmp       # new, generated (issue #2: on-device badges, not fetched)
lib/card.py          # new
lib/net.py           # new
tools/gen_badges.py  # new, host-only (generates lib/logos/*.bmp)
tests/test_enrich_filters.py  # new, host-only
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
