# TailWatch — Design Document for Coding Agents

Status: implementable MVP  
Hardware target: Adafruit MatrixPortal S3 + indoor P2 SMD1515 128×64 HUB75 panel  
Companion: none -- the device calls OpenSky directly and assembles cards on-device (see issue #2; no cloud API)  
Existing starter: `firmware/` (`code.py`, `lib/*`, `www/index.html`, `prefs.example.json`)

This document is the spec. Do not invent product scope beyond it. Prefer small, working slices over frameworks.

---

## 1. Goal

A wall display that shows **one live aircraft card** for traffic near a user-configured GPS point, without requiring a subscription app.

Two physical units will exist (owner + friend). Each unit owns its own lat/lon and display prefs on-device, and assembles its own flight cards and badges locally (issue #2: no cloud tier). OpenSky (or compatible ADS-B) is the position source.

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
| Panel power | External 5.0 V bench/PSU, **direct to the panel's own power input**, ~3 A measured full white (~15 W), budget 4–5 A |
| S3 power | USB-C only (board + logic) — its screw terminals are output-only, never a power input (see footgun below). Can share the panel's PSU via a second USB-C feed; do not wire the panel 5 V onto the S3's screw terminals |
| Wiring | HUB75 data from S3; panel 5 V/GND from PSU **wired to the panel itself**; common ground optional if noise appears |
| S3 power cable | Bare-wire-to-USB-C pigtail (5V, 3–5 A), spliced onto the same PSU as the panel rather than a second USB-C brick (see footgun note below) |

Firmware must never assume USB can power the LEDs.

**Known footgun (confirmed on hardware):** the MatrixPortal S3 has its own 5V/GND screw
terminals next to the HUB75 connector -- these are **output only**, wired straight to the
board's USB-C 5V rail, and exist so the board can drive a *small* panel with no external
supply at all. Landing the external PSU's barrel-to-terminal adapter on *those* terminals
instead of the *panel's own* power input looks correct but isn't: the panel ends up
entirely dependent on USB, and unplugging USB-C kills it even though a beefy external
supply is nominally connected. There is no actual backfeed in this case -- the panel
simply never had independent power. Always verify the PSU leads land on the panel's own
power pads/terminal, never the MatrixPortal's screw lugs.

**Powering both from one supply.** The S3's screw terminals being output-only doesn't
mean the board must run off a separate USB-C wall charger -- it means the board has to
be fed through its USB-C port specifically, same as always, just sourced from the same
PSU as the panel instead of a second brick. Land the PSU's 5V/GND leads on a small
junction (splice or terminal block) with two branches out of it: one straight to the
panel's own power input (as above, carries the bulk of the current), and one through a
**bare-wire-to-USB-C pigtail cable** into the MatrixPortal's USB-C port. That pigtail is
passive -- two wires to VBUS/GND, no PD negotiation -- so it presents the same fixed 5V
the board would see from any USB-C charger. Size the PSU for the panel's worst-case draw
plus the board's (well under 1A even with Wi-Fi active); the panel dominates the budget
either way. See the table above for a specific cable.

## 4. Architecture

```
[Phone browser]
    |  http://<s3-ip>/  or 192.168.4.1  (prefs only)
[MatrixPortal S3]
    |  firmware/lib/net.py: GET /api/states/all?lamin&lomin&lamax&lomax&extended=1
    |  (OpenSky token optional, only to raise the anonymous rate limit)
[OpenSky / ADS-B]
    + on-device firmware/lib/hero.py, firmware/lib/filters.py, firmware/lib/enrich.py, firmware/lib/logos/
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
  "api": "https://opensky-network.org/api",
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
- `tz_offset_min` + `us_dst` used for sleep/fixed night windows (firmware/lib/tz.py, fixed US DST rule only); sunset uses lat/lon solar math (UTC timestamps)

Apply prefs immediately on save except Wi-Fi credentials (Wi-Fi stays in `settings.toml` for MVP).

### Bounding box

```
dlat = nm / 69.0
dlon = nm / (69.0 * cos(lat_rad))
lamin, lamax = lat ± dlat
lomin, lomax = lon ± dlon
```

Existing helper: `firmware/lib/bbox.py`.

### Schedule

Existing helpers: `firmware/lib/sun.py`, `firmware/lib/schedule.py`.

Every ~1 s (or on prefs save):

1. If sleep window → `display.brightness = 0`, skip network poll
2. Else if night → `min(brightness_night, brightness_max)`
3. Else → `min(brightness_day, brightness_max)`

Dimming is done by scaling draw colours (`firmware/lib/dim.py` Dimmer). `display.brightness` is on/off on rgbmatrix, so it stays 1.0 while awake and 0.0 only for the black sleep state (blank group).

NTP at boot (UTC into RTC). The RTC and `sun.py` stay UTC. `schedule.py` computes local time as UTC + `tz_offset_min` (+60 min under the fixed US DST rule when `us_dst`) via `firmware/lib/tz.py`. No tz database: only the fixed US rule is supported.

**Clock-trust gate (issue #11).** NTP can fail (no internet yet, AP mode, a
flaky router), and after `microcontroller.reset()` the RTC may hold either a
real time it kept across the reset, or CircuitPython's built-in epoch
(commonly 2000-01-01). `firmware/lib/schedule.py:clock_trusted(ts=None)` returns true
if NTP has synced this boot (`set_clock_synced(True)`, called by `firmware/code.py`'s
`sync_clock()`), or if `ts` (default `time.time()`) is already
`>= MIN_TRUSTED_TS` (2024-01-01T00:00Z) -- the RTC-survived-reset case.
`sleeping()` and `night()` return `False` when the clock isn't trusted
(never blank the panel or apply night dimming on a bogus timestamp);
`brightness()` then falls through to `min(brightness_day, brightness_max)`.
`GET /api/status` exposes both `clock_synced` and `clock_trusted` so the web
UI can show a "clock not set" banner.

## 7. Local web UI

Static files in `/www`. Server: `adafruit_httpserver` on port 80. Web Workflow
(CIRCUITPY_WEB_API_PASSWORD) must stay disabled -- it also binds port 80 and
exposes the filesystem.

| Route | Method | Purpose |
|---|---|---|
| `/` | GET | `firmware/www/index.html` |
| `/api/prefs` | GET | current JSON minus `token`, plus `token_set` (`firmware/lib/prefs.py:public()`) |
| `/api/prefs` | POST | form or JSON merge → save → apply brightness (station mode only) |
| `/api/status` | GET | `{mode, ip, ssid, ap_ssid, networks, clock_synced, clock_trusted, rebooting, wifi_drops}` -- never a password |
| `/api/wifi` | POST | JSON or form `{ssid, password, open}` → `firmware/lib/wifisettings.py` → `/settings.toml` → hard reset (§ AP mode below) |

All `/api/*` routes require `Host` to be the device's own current address;
POSTs also require a same-origin `Origin`/`Referer`, else `403` (`firmware/lib/reqguard.py`,
issue #14). Reaching the UI by a DNS name instead of its IP therefore returns
403 on every `/api/*` call -- the UI is documented as `http://<ip>/`, not a
hostname.

UI fields must match the schema in §6 (already drafted in `firmware/www/index.html`).

MVP discovery: print IPv4 on serial and on the LED (`SETUP 192.168.x.x`) if no card yet. mDNS `tailwatch.local` is a stretch goal (CircuitPython support is uneven).

### AP mode (first boot, issue #11)

If `CIRCUITPY_WIFI_SSID` is empty, or joining it fails (two 10 s
`wifi.radio.connect()` attempts, ~20 s total):

- Scan for nearby networks first (`wifi.radio.start_scanning_networks()`,
  before `stop_station()` -- the radio can't scan once it's AP-only), for the
  UI's SSID datalist and to pick whichever of channels 1/6/11 has the fewest
  networks.
- Start a **WPA2, password-protected** AP `TailWatch-XXXX` (last two MAC
  bytes), `wifi.radio.start_ap(ssid, pw, channel=…, authmode=[WPA2, PSK],
  max_connections=2)`. The password is 8 random characters from a 32-symbol
  alphabet (no `l`/`o`/`0`/`1`), generated fresh every boot with
  `os.urandom`, never persisted, and only shown on the panel (and serial) --
  not open, because `POST /api/wifi` can repoint the device at another
  network, so being able to read the password proves you're standing at
  the device.
- Serve the same UI at `wifi.radio.ipv4_address_ap` (normally
  `192.168.4.1`); the Wi-Fi form is shown above the regular prefs form.
- Prefs save still writes `/prefs.json`, but the dimmer/brightness path is
  skipped in AP mode (`display.brightness = 1.0`, fixed `0x707070` setup
  text via `firmware/lib/setupscreen.py`, so a slider at 0 or a sleep window can't
  hide the password).
- No NTP attempt in AP mode (there is no internet).
- `POST /api/wifi` is the **only** allow-listed `settings.toml` writer
  (`firmware/lib/wifisettings.py`): it reads just `ssid`, `password`, `open` from the
  body (JSON or form; the body parser never reads the query string for this
  route, so a password can't leak into a URL/log), validates them, and
  rewrites just the two `CIRCUITPY_WIFI_*` keys via a `.new` →
  `path`↔`.bak` → rename swap (crash-safe; `recover()` finishes an
  interrupted swap on the next boot). Everything else in `settings.toml` is
  kept, and the previous file survives as `settings.toml.bak`. Wi-Fi is
  deliberately **not** part of the `/prefs.json` schema (§6).
  - On success: `{ok, ssid, rebooting: true}`, then
    `microcontroller.reset()` about 3 s later (after the reply flushes).
    The hard reset re-runs `firmware/boot.py` (remounts read-write) and the
    CircuitPython supervisor, which re-reads `settings.toml` and auto-joins;
    if the new credentials are wrong the device comes back up as the setup
    AP, so there's always an in-field recovery path.
  - `ValueError` (bad SSID/password) → 400 with the message; `OSError`
    (booted with UP held, filesystem read-only) → 503, same pattern as
    `/api/prefs`, and the device does not reboot.
- **Idle retry.** If an SSID *is* configured (e.g. the router was
  rebooting), the device reboots to retry the join after 600 s with no
  `/api/*` request. The setup page polls `/api/status` every 60 s while in
  AP mode, which keeps the device up while someone has it open. With no
  SSID configured at all, the device stays in AP mode indefinitely.

Hold BOOT 5 s to clear Wi-Fi settings is a stretch goal.

**Captive-portal auto-pop (issue #21).** A plain setup AP with no DNS/HTTP
tricks leaves a joining phone/laptop's own network stack unable to tell
there's anything to sign in to -- its captive-portal detection probes just
time out (AP mode has no internet to resolve or reach anything real), so the
OS never auto-launches a sign-in browser and the user has to already know to
browse to `192.168.4.1`. Two pieces make that auto-pop instead, both AP-mode
only:

- **DNS hijack** (`firmware/lib/captiveportal.py`, `CaptiveDNS`): a UDP responder
  bound to `:53` on the AP-mode `socketpool.SocketPool`, polled once per main
  loop tick (`captive_dns.poll()`, non-blocking). It answers every class-IN
  A or ANY query with the AP's own IPv4 address, and every other query type
  (AAAA, HTTPS/SVCB, ...) with a NOERROR/no-answer reply so the resolver
  falls through to an A query instead of stalling. It is not a general
  resolver -- there's nothing upstream to forward anything to -- and drops
  anything malformed or multi-question rather than guess at it. This is what
  makes the OS's captive-portal probe hostnames (e.g. Apple's
  `captive.apple.com`) resolve to this device at all.
- **HTTP redirects for the known OS probe paths** (`firmware/code.py`,
  `CAPTIVE_CHECK_PATHS` / `captive_redirect`): Android (`/generate_204`,
  `/gen_204`), Apple (`/hotspot-detect.html`,
  `/library/test/success.html`), Windows (`/connecttest.txt`, `/ncsi.txt`,
  `/redirect`), and Firefox (`/success.txt`), registered only
  `if ap_mode`. Each OS actually expects one specific "you have real
  internet" response (Android: bare 204; Apple: one exact HTML string;
  Windows: specific plain-text bodies) and treats *anything else* as "there's
  a portal here" -- so a redirect to `http://<host>/` is enough to trigger
  that path; trying to instead mimic each OS's exact expected success body
  would be more code for the same result and would have to be kept in sync
  with OS behavior that can change.

Together: DNS hijack gets the probe request to this device; the redirect
response is what makes the OS conclude a portal is present and open its
sign-in browser to it.

### Wi-Fi drop recovery (station mode)

Once joined as a station, `firmware/lib/linkwatch.py:LinkWatch` (`firmware/code.py`, station mode
only; `link = None` in AP mode) watches for a dropped link and re-joins it,
because CircuitPython's own retries are limited and `adafruit_httpserver`
otherwise keeps a listening socket bound to the address that just went away:

- Checks `wifi.radio` every 2 s. A drop waits 10 s (grace period, so
  CircuitPython's own few retries can run first), then makes up to 6
  reconnect attempts with gaps 10 / 20 / 30 / 60 / 60 / 60 s between them (about
  4 minutes total from the drop).
- Recovered (its own `connect()`, or the radio recovering on its own) or the
  IP changed while up (DHCP lease change) both fire an "up" event; either way
  `firmware/code.py` restarts the HTTP server (`restart_http()`) on the current host
  address. This covers a listening socket gone stale on the old interface even
  when the IP didn't change, at the cost of one rebind (`adafruit_httpserver`
  4.x sets `SO_REUSEADDR`, so rebinding port 80 works).
- If all 6 reconnects fail, `firmware/code.py` calls `microcontroller.reset()`: the boot
  then fails the ~20 s join and falls back to the setup AP (§ AP mode above),
  which itself reboots to retry after `AP_IDLE_RETRY_S` idle. A long router
  outage becomes a bounded retry loop with an always-recoverable device.
- `server.poll()` is skipped entirely while the link is down (a dead socket
  would otherwise log an error every pass), and NTP / the ADS-B poll are
  gated the same way. The brightness schedule keeps running while offline.
- The web UI server is also restarted whenever it isn't running and the link
  is up (retried every 30 s), and after 5 consecutive `server.poll()`
  exceptions (a fresh start clears the counter). Both apply in AP mode too.
- Serial lines (the Wi-Fi password is never stored or printed):
  - `wifi: link lost (ip was X); first reconnect in 10 s`
  - `wifi: reconnect n/6 to SSID`
  - `wifi: reconnect n/6 failed: <err>`
  - `wifi: link up, ip X unchanged|(was Y) (<why>)`
  - `wifi: still down after 6 reconnects (N s); hard reset`

Known blocking: each reconnect attempt can block for up to 10 s (pausing the
dimmer schedule), and the UI is unreachable during an outage anyway.

## 8. On-device card assembly (was "Cloud API")

Superseded by issue #2: there is no server. `firmware/lib/net.py` (issue #26)
calls OpenSky's `/api/states/all` directly with the device's own bbox
(`firmware/lib/bbox.py`) and `extended=1`, then `firmware/lib/filters.py`,
`firmware/lib/hero.py`, and `firmware/lib/enrich.py` assemble a card with this
same shape on-device, in `firmware/code.py:poll_card()`, for `firmware/lib/card.py`
(issue #27, **to build**) to render. `route`/`type`/`city`/`phase` are not
populated yet -- nothing on-device currently supplies flight-route,
aircraft-type, or airport/phase data for a raw ADS-B state vector, only what
OpenSky itself sends (position/altitude/speed/track/category); they're left
`""` rather than invented, pending a real data source. `prefs.api`/`prefs.token`
(an OpenSky account, not a "cloud API" of ours) are only needed if OpenSky's
anonymous rate limit proves too low in practice; `prefs.token`, when set, is
sent as `Authorization: Bearer <token>`.

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
`firmware/lib/net.py` returns `None`/raises rather than an HTTP error code; `firmware/lib/hero.py`
treats a failed poll as "no fresh candidates" (see `Hero.expired()`), not as
"the hero left the box".

Hero aircraft selection (on-device, `firmware/lib/hero.py`; see issue #2 — the S3 calls
OpenSky directly, so this runs on-device instead of on the server as originally
sketched here):

1. Positions in bbox, airborne (`on_ground` false); `firmware/lib/hero.py:candidates()`
   turns the raw OpenSky state vectors into candidate dicts, skipping ground
   traffic, rows without a position, and malformed rows.
2. Apply hide_* filters (`firmware/lib/filters.py:apply()`, on-device, issue #2; a
   filtered-out hero is treated as rule (b), "gone")
3. Prefer closest to pin; tie-break lower altitude then higher speed
   (`firmware/lib/hero.py:_rank`)
4. Enrich hex → type/reg; callsign prefix → airline + badge id (`firmware/lib/enrich.py:lookup()`,
   on-device, issue #2); route cache → OD pair + city + arriving/departing if possible
5. If enrichment missing, still return callsign + alt + spd

**`extended=1` is required.** `firmware/lib/net.py`'s OpenSky request must add
`&extended=1`, or every state vector's category comes back `None`: helicopters
are never detected (`firmware/lib/filters.py:is_heli()` only matches category 8) and
`is_ga()` falls back to the callsign-shape heuristic for everything.

**Hysteresis / hold** — the shown aircraft is tracked by ICAO hex and only
changes when one of these fires (`firmware/lib/hero.py:select()`, called each poll by
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
  current 15 s poll interval; `firmware/lib/hero.py:stale_limit()`). Either:
  - the position in the data is too old (response `time` minus
    `time_position`, or `last_contact` when that's missing), or
  - no successful poll has confirmed the hero within that limit
    (`Hero.expired(now)`, for repeated fetch failures).
  - The 90 s cap exists because a plane at 250 kt moves ~6 mi in 90 s, past
    which the card would be misleading.

When there is no current hero, the closest candidate is picked (same
tie-break as above). Distances are statute miles, matching `firmware/lib/bbox.py`
(69 mi/degree) and the prefs `nm` field, which despite its name is also miles
each way.

### Badges (was `GET /v1/logo/{id}`)

Superseded (issue #2): airline badges are no longer fetched from the cloud;
everything below is baked into `firmware/lib/logos/<key>.bmp` at build time, one file
per `firmware/lib/enrich.py:AIRLINES` entry plus a generic fallback (`_unk.bmp`), all
4-bit indexed BMP (`adafruit_imageload.load()` / `displayio.OnDiskBitmap()`,
one badge in RAM at a time). No PNG, no network round-trip, no server.

Two build tools produce `firmware/lib/logos/`, and both can coexist:

- `tools/gen_badges.py` (host-only, stdlib-only, Pillow-free): draws
  non-trademarked 24×24 letter-mark badges (IATA/ICAO code, hand-drawn 3×5
  font, 3-color palette — index 0 black, 1 tile background, 2 mark color;
  354 bytes each). This is every airline's badge by default and remains the
  fallback for any airline the next tool hasn't covered.
- `tools/convert_logos.py` (host-only, needs Pillow + cairosvg for SVG
  sources — issue #18): converts a real sourced logo image
  (`tools/logo_sources/<key>.{svg,png,...}`) into the same BMP container,
  fit to its own aspect ratio (longest side ≤ 48 px, the sec. 9 slot budget,
  not forced square), with an 8-color palette lerped from black (index 0) to
  that airline's existing `AIRLINES` accent color (index 7) instead of the
  source's own brand color — several official brand hex values (UPS's,
  Lufthansa's) are near-black and unreadable against the panel's black
  background, while `AIRLINES`'s colors were already picked to be legible
  there. The extra palette steps (vs. the letter-mark's 3) are what keep a
  logo's thin strokes and antialiasing from collapsing into a blob at this
  size; `firmware/lib/dim.py`'s `scale_palette()` rescales a palette of any length the
  same way, so night-mode dimming needs no changes for either badge type.

Priority is automatic and needs no runtime code: `firmware/lib/enrich.py:badge_path()`
is a direct `firmware/lib/logos/<key>.bmp` path lookup with no separate resolution
step, so whichever tool last wrote that file is what loads. The two tools
stay consistent via `tools/logo_sources/sources.json`, a manifest
`{icao: source_filename}` that `convert_logos.py` writes and `gen_badges.py`
reads (`real_logo_keys()`) so that re-running `gen_badges.py` alone never
overwrites or prunes a real logo — it just skips those keys. Re-running
`convert_logos.py` (`--dir tools/logo_sources`) after `gen_badges.py` is what
actually re-asserts a real logo's priority if a key's letter-mark badge was
ever regenerated in between.

As of this writing, 49 of the 49 `AIRLINES` entries have a real logo. 13 of
the initial issue #18 pass (American, United, Southwest, JetBlue, FedEx, UPS,
Air Canada, British Airways, Lufthansa, KLM, Emirates, Qatar Airways, Turkish)
came from Simple Icons (CC0-licensed simplified brand marks,
`cdn.jsdelivr.net/npm/simple-icons`) and go through `convert_logos.py`'s
silhouette mode (single-color glyph, tinted to the `AIRLINES` accent). The
remaining 36 (the initial pass's Air France and Delta, plus the 34 sourced
afterward: Alaska, Spirit, Frontier, Allegiant, Hawaiian, Sun Country, Avelo,
Breeze, SkyWest, Envoy, Republic, Endeavor, PSA, Mesa, Horizon, Piedmont,
GoJet, Air Wisconsin, CommutAir, Cape Air, Atlas Air, ABX Air, ATI, Kalitta,
Polar Air Cargo, Amerijet, Omni Air Intl, National, NetJets, Flexjet, WestJet,
Aeromexico, Viva Aerobus, Volaris) came from `img.logo.dev/<domain>?format=png`
(a per-carrier domain lookup, using
logo.dev's publishable demo token documented on their own site — no account
of ours) and go through the *photo* mode instead: these are raster marks
that carry their own real brand colors, so (unlike the silhouette batch)
they keep the source's colors rather than the `AIRLINES` accent tint. This
is the first real exercise of `convert_photo()`; its docstring's "no such
source is committed yet" is now stale. Every domain was verified to actually
resolve to that airline's own site (or logo.dev's cached asset for it)
before use — three of the issue's guessed domains turned out wrong or dead
and were swapped for the real one: Omni Air International's actual site is
`oai.aero`, not `omniairintl.com` (parked/IIS-default); National Airlines
(N8/NCR)'s is `nationalairlines.com`, not `nationalair.com` (a same-named,
unrelated business); ATI/Air Transport International (8C/ATN)'s is
`airtransport.cc`, not `atiacmi.com` (unreachable) or the `atiaviation.com`
near-miss (a different, unrelated "ATI Aviation Services"). Horizon Air's
`horizonair.com` legitimately resolves to the same Alaska Airlines "Eskimo"
mark Alaska itself uses — Horizon retired its independent brand in 2011 and
now flies co-branded as "Alaska Horizon" — so reusing that art for `qxe` is
correct, not a scraping error.

Air France and Delta moved from the initial Simple Icons pass to
logo.dev/photo mode on a later review of all 15 (user-flagged). Two distinct
problems turned up, and the same review deliberately checked all 15 against
both, not just re-examining the one flagged carrier:

- **Wrong mark**: Simple Icons' `afr.svg` was just the loose diagonal accent
  slash with no wordmark or color cue, tinted to a plain blue that doesn't
  match Air France's actual red/navy branding — on its own it didn't read as
  Air France's mark at all. `airfrance.com`'s logo.dev fetch (the same slash
  plus the "AIRFRANCE" wordmark, in the airline's real red) replaced it; the
  wordmark all but disappears at the 48 px badge size (it's a thin,
  small-relative-to-the-icon typeface that photo mode's 8-step quantizing
  washes out — a known photo-mode limitation, see `convert_photo()`'s
  docstring), but the red slash alone is already a correct, recognizable
  improvement over the old shape and color.
- **Wordmark lockup squeezed illegible**: silhouette mode fits a source to
  its own aspect ratio at longest-side-48px, so a *wide* source — a full
  wordmark, or a wordmark+icon lockup — collapses to a sliver instead of
  shrinking evenly. Simple Icons' `dal.svg` is Delta's full "DELTA" wordmark
  next to the widget triangle, which came out **48×8px**: five letters in an
   8px-tall strip, illegible on the actual LED panel regardless of how
  accurate the shapes are. `delta.com`'s logo.dev fetch is the widget
  triangle alone (no wordmark) and converts at a proper 48×48 — that
  replaced it.

The other 13 Simple Icons silhouettes were checked the same way — rendered
against a logo.dev fetch of the same airline, and their badge's actual output
aspect ratio/height checked as a fast signal for a hidden wordmark-lockup
problem (the `dal` failure mode: a single-digit output height from a source
with letterforms in it). None of the other 13 have that shape (heights range
28–48px; the two shortest, FedEx at 13px and JetBlue at 16px, are inherently
wordmark-only brands with no separate icon mark to substitute, and both are
still legible at that height — nowhere near `dal`'s 8px). All 13 were judged
fine as plausible, correctly-shaped, legible versions of the real mark and
left untouched. All 49 files together are a little over 50 KB; on the
board's 512-byte FAT clusters that's comfortably inside the 8 MB flash.

One more carrier was swapped after this review: `swa` (Southwest) was still
on its Simple Icons silhouette (a monochrome heart, tinted to Southwest's
`AIRLINES` yellow) because logo.dev's fetch for `southwest.com` came back
bad/near-blank. Wikimedia Commons — a 403/rate-limited dead end during the
original 34-carrier sourcing push — was reachable on a later attempt and had
Southwest's real 2014-logo SVG, which turned out to have the tri-color heart
(blue/red/yellow gradient triangles) as separate `<path>` elements from the
"Southwest" wordmark text; cropping to just the heart paths gave a real,
correctly-colored icon-only mark instead of another wordmark-lockup risk.
It needed two things the pipeline didn't have yet: forcing "photo" mode on
an `.svg` source (detect_mode() assumes `.svg` means the single-color
silhouette path, wrong here since this source keeps its own 3 brand colors),
and 16 palette steps instead of the default 8 (the gradient's yellow/orange
end washed out to a muddy tan at 8 — median-cut quantization needs the extra
resolution when a small-area color region has to share the palette with two
much larger ones). Both are now first-class: `convert_logos.py --mode/--steps`
flags, and `tools/logo_sources/sources.json` entries can be either a bare
filename (the common case, mode/steps both default) or
`{"file": ..., "mode": ..., "steps": ...}` when a source needs an override —
recorded automatically the first time it's given one, so a later plain
`--dir` re-run reproduces it without repeating the flags.

Sources tried that did *not* pan out, for the next carrier that needs one:
Simple Icons only covers the first 15 (it's a general tech/consumer brand
set, not an airline-specific one — none of the remaining 34 appear in it);
`github.com/gilbarbara/logos` is the same kind of tech-brand set and has no
airline matches either; `worldvectorlogo.com` 403s every page (search and
logo, several query shapes tried, several browser user-agents) behind a
Cloudflare bot challenge; `svgrepo.com` 403s behind a Vercel bot checkpoint;
`cdn.brandfetch.io/<domain>` now 302-redirects to a "client ID required"
notice — the old unauthenticated quick-logo trick is dead; `img.logo.dev`
*without* a token 401s, but `?token=<their published demo token>&format=png`
works well and was this batch's actual source.

**Licensing**: this is the project owner's personal, non-commercial build
(issue #18). The owner has explicitly decided not to pursue trademark
clearance for shipping real airline logos on it, overriding sec. 2's
original "no airline trademark artwork" non-goal for this reason alone —
that is a stated project decision, not legal advice, and not something this
repo attempts to justify further. The letter-mark generator is kept
specifically so any fork or reuse that does care about that can drop back to
it (delete `tools/logo_sources/sources.json`, or the individual keys in it,
and re-run `tools/gen_badges.py`) without losing badge coverage for any
airline.

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
| `firmware/lib/prefs.py` | load/save/clamp/form merge | exists |
| `firmware/lib/sun.py` | sunrise/sunset | exists |
| `firmware/lib/schedule.py` | sleep/night/brightness | exists |
| `firmware/lib/bbox.py` | OpenSky box | exists |
| `firmware/lib/dim.py` | colour-scale dimming + sleep blank | exists |
| `firmware/lib/tz.py` | UTC offset + fixed US DST rule | exists |
| `firmware/lib/urldecode.py` | percent-decode form bodies | exists |
| `firmware/lib/buttons.py` | hold-to-trigger button helper | exists |
| `firmware/lib/nyan.py` | easter egg animation | exists |
| `firmware/lib/hero.py` | hero-aircraft selection + hysteresis (on-device, issue #2) | exists |
| `firmware/lib/enrich.py` | callsign → airline name + badge key/path, on-device (issue #2) | exists |
| `firmware/lib/filters.py` | on-device hide_heli / hide_mil / hide_ga (issue #2; §10) | exists |
| `firmware/www/index.html` | settings UI | exists |
| `firmware/code.py` | matrix, Wi-Fi join / setup-AP fallback, station reconnect watchdog, web UI server (auto-restart), NTP, dimmer schedule; poll_card() wires firmware/lib/net.py → filters → hero → enrich into a real card (issue #26) | exists |
| `firmware/lib/linkwatch.py` | station Wi-Fi drop detection, bounded reconnect (6 tries, ~4 min), then hard reset into setup AP | exists |
| `firmware/lib/httpclient.py` | shared adafruit_requests Session, 4 s timeout, 8 s/32 KB body cap, always-close get_json() for firmware/lib/net.py | exists |
| `firmware/lib/captiveportal.py` | AP-mode captive-portal DNS responder (issue #21; §7 AP mode) | exists |
| `firmware/lib/card.py` | render 128×64 card | **to build** (issue #27) |
| `firmware/lib/net.py` | HTTPS GET nearby, extended=1, optional bearer token (§8; issue #26) | exists |

### Display card (128×64)

Layout (pixel budget):

```
+------------------+----------------------------+
| up to 48×48      | Airline                     |
| badge            | FLIGHT  ROUTE               |
+------------------+ TYPE                        |
| city / phase                               |
| ALT  SPD  TRK                              |
+--------------------------------------------+
```

- Badge: local `firmware/lib/logos/<key>.bmp`, loaded via `adafruit_imageload.load()`
  or `displayio.OnDiskBitmap()` (§8, issue #2). Up to **48×48**: a real
  sourced carrier logo (`tools/convert_logos.py`, issue #18) where one exists
  (49/49 `AIRLINES` entries, as of this writing), else a generated 24×24
  letter-mark (`tools/gen_badges.py`) — still the fallback for the generic
  `_unk` badge and for any airline added to `AIRLINES` before a real logo is
  sourced for it. See §8 Badges for the licensing note and how the two
  coexist. Register
  one badge palette in `firmware/lib/dim.py` and overwrite its colours on each hero
  swap (`Dimmer.add_palette` only ever adds, so swapping badges by adding a
  fresh palette every poll would leak memory) — note a real logo's palette
  is longer (8 entries) than a letter-mark's (3), so this still-to-build
  wiring needs to size that registered palette to the badge actually loaded
  (e.g. re-registering per swap) rather than assume a fixed length
- Font: `terminalio.FONT` or a bundled 5×7 / 6×12 bitmap font
- Colors: white text, dim gray labels, badge as-is
- Sleep: empty group / brightness 0
- No data: `NO TRAFFIC` + local time
- Error: `NO LINK` (do not crash the HTTP server)

`bit_depth=4` (set via `BIT_DEPTH` in `firmware/code.py`); 3 gives only 7 lit levels per channel. Do not use 6+ for MVP.

### Poll loop

- `server.poll()` every iteration
- ADS-B poll every 15 s when not sleeping
- Outbound HTTP only via `firmware/lib/httpclient.py` (4 s per-socket-op timeout, 8 s body budget, response always closed; worst-case stall ~16 s); keep last good card
- Skip NTP/poll and `server.poll()` while `LinkWatch` reports the link down
- Never block the UI server for more than one poll

## 10. Filters

On-device (`firmware/lib/filters.py`, issue #2 — no server blocklist). Heuristic MVP,
documented as imperfect:

- **Helicopter (`is_heli`):** true only when OpenSky's ADS-B emitter
  `category == 8` (Rotorcraft). This field is state-vector index 17 and is
  only populated when the `/states/all` request includes `&extended=1`
  (`firmware/lib/net.py`, issue #26) — without it every category is `None` and no
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
  2. Callsign prefix in `firmware/lib/enrich.py:AIRLINES` → not GA (covers e.g. FedEx
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
- OpenSky token (optional, only to raise the anonymous rate limit) lives in `/prefs.json` on-device. It is write-only: `token` is never present in a `GET`/`POST` `/api/prefs` response, only a `token_set` boolean (`firmware/lib/prefs.py:public()`, `firmware/lib/reqguard.py`, issue #14)
- All `/api/*` routes require `Host` to match the device's own current address (blocks DNS rebinding); POSTs also require a same-origin `Origin` (or `Referer` if no `Origin`), or a `403` (blocks CSRF from another site the LAN browser has open) -- `firmware/lib/reqguard.py`, checked by `firmware/code.py:_guard()`
- CIRCUITPY is writable; do not put secrets in git

## 12. Implementation order (coding agent)

Do these PRs/slices in order. Each slice must run on hardware or have a clear mock.

1. ~~**Harden existing prefs + UI**~~ — done (issues #4, #5)
2. **Card renderer** — `firmware/lib/card.py`, hardcoded style card on 128×64 -- **to build** (issue #27)
3. ~~**Schedule live**~~ — done (issue #7); ~~**Brightness dimming**~~ — done (issue #8)
4. ~~**OpenSky HTTPS client**~~ — done (issue #26): `firmware/lib/net.py` hits OpenSky's `/api/states/all` directly with bbox + `extended=1`, optional bearer token; parses JSON via `firmware/lib/httpclient.py`
5. ~~**Lookup tables + badges**~~ — done (issue #10: `firmware/lib/enrich.py`, `firmware/lib/filters.py`, `firmware/lib/logos/`)
6. ~~**Hero selection**~~ — done (issue #9: `firmware/lib/hero.py`)
7. **AP fallback** — if no Wi-Fi (issue #11, in progress)
8. ~~**Wire it together**~~ — done for the data half (issue #26): `firmware/code.py:poll_card()` calls `firmware/lib/net.py` → `firmware/lib/filters.py` → `firmware/lib/hero.py` → `firmware/lib/enrich.py` and assembles a real card dict. Still missing `firmware/lib/card.py` (issue #27) to actually render it -- `code.py` prints the card to serial but the LED matrix still shows the placeholder group.

Do not start a rewrite in ESP-IDF unless CircuitPython HTTPS + HTTP server cannot coexist. If it cannot, port modules 1:1 to Arduino/ESP-IDF and keep this spec.

## 13. Acceptance tests

Host-side tests are plain Python 3 (stdlib only, no pytest) and are not copied
to CIRCUITPY. Run them all from the repo root:

```
for f in tests/test_*.py; do python3 "$f" || exit 1; done
```

`tests/test_code_*.py` run the real `firmware/code.py` under fake CircuitPython modules
(`board`, `wifi`, `displayio`, `adafruit_httpserver`, ...) with a simulated
clock: they check control flow and serial output, not the panel or the radio.

### 13.1 Automated (host-side)

| Behavior (spec §) | Test |
|---|---|
| Pin (lat/lon/nm) saved from the web form survives a fresh `load()` (the reboot); a second unit sets a different pin through the same code path, no firmware fork (§5, §6) | `tests/test_prefs.py` |
| `/prefs.bak` written on save and used when `/prefs.json` is corrupt; clamps: `nm` 1–50, brightness 0–1 and ≤ `brightness_max`, `tz_offset_min` −720..840, unknown `night_mode` → `sunset`, legacy `timezone` dropped; lat/lon/HH:MM fields validated with a default fallback (§6, issue #15) | `tests/test_prefs.py`, `tests/test_prefs_validation.py` |
| Form POST: missing checkbox = `false`; JSON POST: partial merge, booleans as-is, unparseable numbers / unknown keys ignored; write-only `token` merge rules (§6, issue #14) | `tests/test_prefs.py`, `tests/test_prefs_token.py` |
| Bbox matches the §6 formula (10 mi at 30N 95W; 5 mi friend pin); existing cos(lat) floor of 0.2 above ~78.5° | `tests/test_bbox.py` |
| Sleep window → brightness 0 (wraps midnight, end exclusive, start == end means off, CST and CDT) (§6 Schedule) | `tests/test_schedule.py` |
| Fixed night hours or after local sunset → night slider, capped by `brightness_max`; `night_mode=off` → day level; fixed US DST rule boundaries (§6 Schedule) | `tests/test_schedule.py` |
| Clock-trust gate: default-epoch RTC never blanks or night-dims; NTP-synced or ≥ 2024 RTC applies the schedule (§6, issue #11) | `tests/test_schedule_clock.py` |
| Dimmer: level 0 → blank group + `display.brightness = 0.0`; wake restores the awake group at 1.0; palettes rescaled from base colours (no compounding) with the min-visible floor (§6) | `tests/test_dim.py` |
| `firmware/code.py`: in a sleep window the panel level is 0.0 and no ADS-B poll runs; awake, the poll's bbox comes from the saved pin (§6, §9 Poll loop) | `tests/test_code_schedule.py` |
| `firmware/code.py` setup AP: no SSID → WPA2 `TailWatch-XXXX`, 8-char password from the 32-symbol alphabet, fresh each boot, printed once, quietest of channels 1/6/11, UI on 192.168.4.1, no NTP, stays up indefinitely; SSID configured but unreachable → two join attempts, AP, reboot after `AP_IDLE_RETRY_S` idle (§7 AP mode) | `tests/test_code_apmode.py` |
| `settings.toml` Wi-Fi writer: validation, form parsing, TOML escaping, other keys kept, crash-safe swap + `recover()` (§7 AP mode) | `tests/test_wifisettings.py` |
| `CaptiveDNS._build`: A/ANY query answered with the AP's IP, AAAA gets NOERROR/no-answer, malformed packets dropped, transaction ID echoed (§7 AP mode, issue #21) | `tests/test_captiveportal.py` |
| `firmware/code.py` AP mode: a DNS query fed to the poll loop gets answered with the AP's own IP; captive-check HTTP routes (`/generate_204`, `/hotspot-detect.html`, ...) registered only in AP mode (§7 AP mode, issue #21) | `tests/test_code_apmode.py` |
| LinkWatch: grace period, 6 bounded reconnects then give-up, self-recovery, IP change while up, radio errors count as down, password never printed (§7 Wi-Fi drop recovery) | `tests/test_linkwatch.py` |
| `firmware/code.py` link handling: drop + rejoin on a new IP moves the UI server; gives up → hard reset; 5 consecutive `server.poll()` errors restart the server; no `server.poll()` while down (§7 Wi-Fi drop recovery) | `tests/test_code_linkwatch.py` |
| Outbound HTTP: one Session reused, timeout passed, response always closed, non-200 + `Retry-After`, mid-body error, 8 s / 32 KB caps (§9 Poll loop) | `tests/test_httpclient.py` |
| Hero: candidate parsing (ground / no-position / malformed skipped; `states: null` → no candidates), closest + tie-break, hysteresis rules (a)(b)(c), no flapping, `Hero.expired()` (§8) | `tests/test_hero.py` |
| Filters heli / mil / GA and `apply()` on hero candidates; airline prefix lookup; badges committed, current, and decodable (§8 Badges, §10) | `tests/test_enrich_filters.py` |
| Local-UI same-origin guard: Host must match the device's address on every `/api/*` route; POSTs also require a same-origin Origin/Referer, else 403 (§11, issue #14) | `tests/test_reqguard.py` |
| `firmware/lib/net.py`: URL has the right path/bbox/`extended=1`, no token → no `Authorization` header, a token → `Bearer <token>` (stripped), a trailing slash on `prefs.api` doesn't double up, every `httpclient.get_json` failure (`HTTPStatusError` incl. `retry_after`, `OSError`/`RuntimeError`/`TimeoutError`/`ValueError`) propagates unchanged rather than getting swallowed (§8, issue #26) | `tests/test_net.py` |
| `firmware/code.py` real poll wiring: a real state vector becomes a card with the right flight/airline/logo/hex; empty sky → `flight: null`; a 429 backs off past its `Retry-After` (no poll fires early) and keeps the last good card; any other fetch failure also keeps the last good card without crashing the loop (§8, issue #26) | `tests/test_code_poll.py` |

### 13.2 Pending (blocked on unbuilt modules or open issues)

Add a host test for each item when its code lands, not before.

- **Empty sky → `NO TRAFFIC` + local time, not a crash.** Needs `firmware/lib/card.py`
  (§12 slice 2, issue #27). The data side is done: `tests/test_hero.py` (`states: null`
  → no candidates; `select(None, [])` → `(None, "none")`) and
  `tests/test_code_poll.py` (`poll_card()` returns `flight: None` on an empty
  response) both cover it up to the point nothing renders it yet.
- **OpenSky unreachable / 429 / malformed JSON → panel `NO LINK`, last good card
  kept, web UI still answers.** The data/backoff side is done (issue #26,
  `tests/test_net.py`, `tests/test_code_poll.py`); still needs `firmware/lib/card.py`
  (issue #27, §12 slice 2) to actually show `NO LINK` on the panel instead of
  just keeping `last_card` in memory.

### 13.3 Manual, on hardware only

- Power: full-white bench draw ~15 W @ 5 V from the panel PSU; USB-C powers
  only the S3; firmware never changes the power wiring (§3).
- From a phone on the same LAN, save lat/lon at `http://<s3-ip>/`, power-cycle,
  values persist (exercises `firmware/boot.py`'s read-write remount). Booted with UP
  held, a save returns 503.
- Sleep window: panel physically dark, serial shows no `hero`/card lines (no
  poll fires while asleep). The night level is visibly distinct from gray
  labels at `BIT_DEPTH = 4`.
- Setup AP: panel shows `WIFI SETUP` / `TailWatch-XXXX` / `pw …` /
  `192.168.4.1`; a phone joins with that password; "Save Wi-Fi & restart"
  joins the new network; wrong credentials come back up as the setup AP.
- Wi-Fi drop: reboot the router; serial shows `wifi:` lines and the UI is
  reachable at the (possibly new) IP afterward; an outage over ~4 min ends in
  a hard reset into the setup AP.
- Web Workflow off: no `CIRCUITPY_WEB_API_PASSWORD`; the UI binds port 80
  (no `http start failed`).
- After `firmware/lib/net.py` / `firmware/lib/card.py`: a real OpenSky poll returns categories
  (`extended=1`); card and badge are legible on the 128×64 panel; `NO LINK`
  with the uplink unplugged.

## 14. Repo / files

Only what is actually copied to the CIRCUITPY drive lives under `firmware/`
(`code.py`, `lib/`, `www/`, `settings.toml.example`, `prefs.example.json`).
Everything host-only -- build tools, tests, this spec -- lives at the repo
root instead.

```
firmware/code.py
firmware/settings.toml.example
firmware/prefs.example.json
firmware/www/index.html
firmware/lib/prefs.py
firmware/lib/sun.py
firmware/lib/schedule.py
firmware/lib/bbox.py
firmware/lib/dim.py
firmware/lib/hero.py
firmware/lib/enrich.py        # new (issue #2: on-device airline lookup)
firmware/lib/filters.py       # new (issue #2: on-device heli/mil/ga filters)
firmware/lib/logos/*.bmp       # new, generated (issue #2: on-device badges, not fetched;
                       #   issue #18: real logo where sourced, else letter-mark)
firmware/lib/card.py          # new (issue #27, to build)
firmware/lib/net.py           # new (issue #26)
firmware/lib/wifisettings.py  # new (issue #11: AP-mode settings.toml Wi-Fi writer)
firmware/lib/setupscreen.py   # new (issue #11: panel setup-AP credentials screen)
firmware/lib/linkwatch.py     # new (station Wi-Fi drop detection + bounded reconnect)
firmware/lib/httpclient.py    # new (shared, always-closing adafruit_requests client for firmware/lib/net.py)
firmware/lib/captiveportal.py # new (issue #21: AP-mode captive-portal DNS responder)
tools/gen_badges.py     # new, host-only (generates firmware/lib/logos/*.bmp letter-marks)
tools/convert_logos.py  # new, host-only (issue #18: real logos -> firmware/lib/logos/*.bmp)
tools/logo_sources/     # new (issue #18: sourced logo images + sources.json manifest)
tests/test_enrich_filters.py    # host-only
tests/test_hero.py              # host-only
tests/test_prefs.py             # host-only (prefs round trip, .bak, clamps, merge rules)
tests/test_prefs_validation.py  # host-only (issue #15: lat/lon/HH:MM validation)
tests/test_prefs_token.py       # host-only (issue #14: write-only token merge rules)
tests/test_reqguard.py          # host-only (issue #14: same-origin guard)
tests/test_bbox.py              # host-only (sec. 6 bbox formula)
tests/test_dim.py               # host-only (colour dimming + sleep blank)
tests/test_schedule.py          # host-only (sleep/night windows, US DST, sunset)
tests/test_schedule_clock.py    # host-only (issue #11 clock-trust gate)
tests/test_wifisettings.py      # host-only (issue #11)
tests/test_linkwatch.py         # host-only
tests/test_httpclient.py        # host-only
tests/test_code_linkwatch.py    # host-only (runs firmware/code.py with fake CircuitPython modules)
tests/test_code_schedule.py     # host-only (firmware/code.py sim: sleep skips poll, bbox from prefs)
tests/test_code_apmode.py       # host-only (firmware/code.py sim: setup-AP fallback, captive DNS + redirects)
tests/test_captiveportal.py     # host-only (issue #21: CaptiveDNS._build wire format)
tests/test_net.py               # host-only (issue #26: firmware/lib/net.py URL/auth/error propagation)
tests/test_code_poll.py         # host-only (issue #26: firmware/code.py sim, real net -> filters -> hero -> enrich wiring)
firmware/lib/reqguard.py      # new (issue #14: same-origin/CSRF guard)
DESIGN.md            # this file
README.md
```

## 15. Coding rules for the agent

- CircuitPython-compatible: no f-string heavy deps, no `pathlib` assumptions that fail on CP
- Avoid large allocations in the poll path
- Do not add Google/FlightRadar scraped APIs
- Do not commit tokens
- Match existing helper APIs rather than renaming without cause
- When unsure of MatrixPortal pin names, use `board.MTX_*` as in current `firmware/code.py`
- Update README with any new library bundle names

## 16. Reference context

- Product look: airline logo, flight number, city pair, aircraft type, arriving/departing city
- Open data: OpenSky Network state vectors in a bbox
- Enrichment later: FlightAware AeroAPI (paid, server-only)
- Starter firmware already serves `/api/prefs` and computes brightness/sleep/sunset
