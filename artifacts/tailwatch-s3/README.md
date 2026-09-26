# TailWatch S3 (starter)

MatrixPortal S3 + 128x64 HUB75 panel.

## On the CIRCUITPY drive

- `boot.py`
- `code.py`
- `prefs.json` (copy from `prefs.example.json`)
- `settings.toml` (Wi-Fi only -- copy from `settings.toml.example`; do **not** set `CIRCUITPY_WEB_API_PASSWORD`)
- `www/index.html`
- `lib/prefs.py`, `lib/sun.py`, `lib/schedule.py`, `lib/bbox.py`, `lib/urldecode.py`, `lib/tz.py`, `lib/dim.py`, `lib/hero.py`
- `lib/enrich.py`, `lib/filters.py` (on-device airline lookup + heli/mil/GA filters, issue #2: no cloud)
- `lib/logos/` (50 generated badge BMPs, ~17.7 KB total -- see `tools/gen_badges.py`)
- `lib/wifisettings.py` (settings.toml Wi-Fi writer, AP-mode provisioning, issue #11)
- `lib/setupscreen.py` (panel setup-AP credentials screen, issue #11)
- `lib/linkwatch.py` (station Wi-Fi drop detection + bounded reconnect watchdog)
- `lib/httpclient.py` (shared, always-closing adafruit_requests client pattern for the future `lib/net.py`)

Libraries from the CircuitPython bundle:

- `adafruit_httpserver`
- `adafruit_ntp`
- `adafruit_imageload` (decodes `lib/logos/*.bmp` badges)
- `adafruit_display_text` (setup-AP credentials screen, `lib/setupscreen.py`)
- `adafruit_requests`, `adafruit_connection_manager` (needed once `lib/net.py` starts making HTTPS requests via `lib/httpclient.py`)

`tests/` (host-side checks, e.g. `tests/test_hero.py`) is plain Python for a
computer's `python3` and is **not** copied to the CIRCUITPY drive.

## Updating files (read-only USB drive)

`boot.py` remounts CIRCUITPY writable for the firmware so the web UI can save
`/prefs.json` (and `/prefs.bak`). Side effect: in normal operation the USB drive
is **read-only** to your computer.

To update `code.py`, `lib/`, or `www/`:

1. Plug into USB, **hold the UP button**, tap RESET (or power-cycle), and keep
   holding UP about 2 s until the drive mounts.
2. The drive is now writable over USB; copy files. (Web UI prefs saves return
   503 in this mode.)
3. Tap RESET without holding anything to return to normal mode.

Do **not** hold BOOT for this: BOOT at power-up enters the ESP32-S3 ROM
bootloader, not CircuitPython.

Fallbacks: enter safe mode (press RESET, then press RESET again during the ~1 s
yellow status-LED blink); safe mode skips `boot.py` and leaves the drive
USB-writable. Or from the serial REPL: `import os; os.rename("/boot.py", "/boot.off")`
then hard reset.

`boot.py` only runs on hard reset/power-up; a soft reload (Ctrl-D, file save)
does not re-run it.

## Behavior

- If an existing board's `settings.toml` has `CIRCUITPY_WEB_API_PASSWORD`, delete
  that line and hard reset. Otherwise Web Workflow holds port 80, the TailWatch
  UI prints "http start failed", and the filesystem is exposed on the LAN.
- Local UI: `http://<s3-ip>/` after it joins Wi-Fi
- Prefs saved on device (`/prefs.json`)
- Sleep blanks the panel (`brightness = 0`)
- Night mode: off / fixed hours / after local sunset
- Day / night / max brightness sliders
- Filters stored: `hide_heli`, `hide_ga`, `hide_mil`
- 10 miles each way → OpenSky bbox (printed to serial until `lib/net.py` is wired)
- No cloud API -- OpenSky is called directly from the device; hero selection, filters, and airline badges all run on-device (`lib/hero.py`, `lib/filters.py`, `lib/enrich.py`, `lib/logos/`)
- If Wi-Fi drops, TailWatch retries the join for ~4 min (serial shows `wifi:` lines), moves the web UI to the new IP, and otherwise reboots into the setup AP.

## First-time / new Wi-Fi setup

If `CIRCUITPY_WIFI_SSID` is empty, or the device can't join it, TailWatch
starts its own setup access point:

1. The panel shows four lines: `WIFI SETUP`, the AP name `TailWatch-XXXX`,
   the AP password (`pw xxxxxxxx`), and `192.168.4.1`. The same line is
   printed to serial.
2. On your phone or laptop, join `TailWatch-XXXX` with that password.
3. Open `http://192.168.4.1/`. The Wi-Fi form is shown above the regular
   prefs form, with a note that setup mode is active.
4. Enter your home network's SSID and password (or tick "Open network") and
   tap **Save Wi-Fi & restart**. TailWatch writes `/settings.toml` and hard
   resets to join it.
5. Reconnect your phone to your normal Wi-Fi; find the device's new address
   on serial or in your router's device list.

If the saved credentials are wrong, or that network isn't reachable, the
device comes back up as the `TailWatch-XXXX` setup AP, so there's always an
in-field way to recover. With no SSID configured at all, it stays in setup
mode indefinitely; with an SSID configured but unreachable, it retries the
join automatically after about 10 minutes of no setup-page activity.

Wi-Fi saves need a normal boot (not booted with UP held) since that mode
leaves the filesystem read-only to `code.py`; a save attempted then returns
503 and the device does not reboot.

## Next

1. `lib/net.py`: implement `poll_card()` as an HTTPS GET to OpenSky's `/api/states/all` (bbox + `extended=1`)
2. Draw the returned card with `displayio` / `terminalio` (`lib/card.py`)
3. Wire `code.py`'s poll loop: `net.poll_card()` → `filters.apply()` → `hero.select()` → `card.draw()`
4. ~~AP-mode first-boot if `CIRCUITPY_WIFI_SSID` is empty~~ -- done (issue #11)
