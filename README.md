# TailWatch S3 (starter)

MatrixPortal S3 + 128x64 HUB75 panel.

## On the CIRCUITPY drive

- `firmware/boot.py`
- `firmware/code.py`
- `prefs.json` (copy from `firmware/prefs.example.json`)
- `settings.toml` (Wi-Fi only -- copy from `firmware/settings.toml.example`; do **not** set `CIRCUITPY_WEB_API_PASSWORD`)
- `firmware/www/index.html`
- `firmware/lib/prefs.py`, `firmware/lib/sun.py`, `firmware/lib/schedule.py`, `firmware/lib/bbox.py`, `firmware/lib/urldecode.py`, `firmware/lib/tz.py`, `firmware/lib/dim.py`, `firmware/lib/hero.py`
- `firmware/lib/enrich.py`, `firmware/lib/filters.py` (on-device airline lookup + heli/mil/GA filters, issue #2: no cloud)
- `firmware/lib/logos/` (50 generated badge BMPs, ~17.7 KB total -- see `tools/gen_badges.py`)
- `firmware/lib/wifisettings.py` (settings.toml Wi-Fi writer, AP-mode provisioning, issue #11)
- `firmware/lib/setupscreen.py` (panel setup-AP credentials screen, issue #11)
- `firmware/lib/linkwatch.py` (station Wi-Fi drop detection + bounded reconnect watchdog)
- `firmware/lib/httpclient.py` (shared, always-closing adafruit_requests client pattern for the future `firmware/lib/net.py`)
- `firmware/lib/buttons.py` (hold-to-trigger button helper)
- `firmware/lib/badapple.py`, `firmware/lib/badapple_frames.py` (Bad Apple easter egg, hold UP 5s -- issue #30)
- `firmware/lib/nyan.py` (Nyan Cat easter egg; not currently wired into `firmware/code.py`)
- `firmware/lib/ota.py` (OTA firmware updates from the web UI -- issue #29)

Libraries from the CircuitPython bundle:

- `adafruit_httpserver`
- `adafruit_ntp`
- `adafruit_imageload` (decodes `firmware/lib/logos/*.bmp` badges)
- `adafruit_display_text` (setup-AP credentials screen, `firmware/lib/setupscreen.py`)
- `adafruit_requests`, `adafruit_connection_manager` (needed once `firmware/lib/net.py` starts making HTTPS requests via `firmware/lib/httpclient.py`)

`tests/` (host-side checks, e.g. `tests/test_hero.py`) is plain Python for a
computer's `python3` and is **not** copied to the CIRCUITPY drive.

## Updating files (read-only USB drive)

`firmware/boot.py` remounts CIRCUITPY writable for the firmware so the web UI
can save `/prefs.json` (and `/prefs.bak`). Side effect: in normal operation the
USB drive is **read-only** to your computer.

To update `firmware/code.py`, `firmware/lib/`, or `firmware/www/`:

1. Plug into USB, **hold the UP button**, tap RESET (or power-cycle), and keep
   holding UP about 2 s until the drive mounts.
2. The drive is now writable over USB; copy files. (Web UI prefs saves return
   503 in this mode.)
3. Tap RESET without holding anything to return to normal mode.

Do **not** hold BOOT for this: BOOT at power-up enters the ESP32-S3 ROM
bootloader, not CircuitPython.

Fallbacks: enter safe mode (press RESET, then press RESET again during the ~1 s
yellow status-LED blink); safe mode skips `firmware/boot.py` and leaves the drive
USB-writable. Or from the serial REPL: `import os; os.rename("/boot.py", "/boot.off")`
then hard reset.

`firmware/boot.py` only runs on hard reset/power-up; a soft reload (Ctrl-D,
file save) does not re-run it.

## OTA firmware updates (no USB needed)

The web UI's "Firmware update" section can update `code.py`/`lib/*`/`www/*`
over Wi-Fi, no physical access required -- useful for the second unit
(DESIGN.md sec. 5). Paste the URL of a manifest JSON file (host it
anywhere reachable, e.g. a GitHub release asset):

```json
{
  "version": "1.4.0",
  "files": [
    {"path": "code.py", "url": "https://.../code.py",
     "sha256": "<sha256 hex digest>", "size": 12345}
  ]
}
```

"Check for update" fetches and validates the manifest without changing
anything; "Apply update" re-fetches and verifies every file's checksum and
size before writing anything, then restarts. If something goes wrong after
applying, "Roll back last update" restores the previous version of every
file that update changed (one level of history). This is all pull-only --
the device fetches from the URL you give it, there is no push/hosted update
service of this project's own (issue #2: no cloud tier).

If a power cut happens mid-apply, the next boot finishes the interrupted
file swap on its own (`firmware/lib/ota.py:recover()`, same crash-safe
`.new`/`.bak` dance as the Wi-Fi settings writer) rather than leaving a
mixed set of old/new files. There is no automatic "this update won't boot,
revert" detection yet -- if an update leaves the device unreachable over
Wi-Fi, recover with the USB procedure above (or a full reflash) and roll
back from there.

## Behavior

- If an existing board's `settings.toml` has `CIRCUITPY_WEB_API_PASSWORD`, delete
  that line and hard reset. Otherwise Web Workflow holds port 80, the TailWatch
  UI prints "http start failed", and the filesystem is exposed on the LAN.
- Local UI: `http://<s3-ip>/` after it joins Wi-Fi, or `http://tailwatch-XXXX.local/`
  (same `XXXX` suffix as the setup AP name, so two units on one LAN never
  collide) if your network supports mDNS/Bonjour and the board's CircuitPython
  build includes the `mdns` module -- if not, `firmware/lib/mdnsadv.py` prints
  nothing extra and the IP-based URL above still works
- Prefs saved on device (`/prefs.json`)
- Sleep blanks the panel (`brightness = 0`)
- Night mode: off / fixed hours / after local sunset
- Day / night / max brightness sliders
- Filters stored: `hide_heli`, `hide_ga`, `hide_mil`
- 10 miles each way → OpenSky bbox (printed to serial until `firmware/lib/net.py` is wired)
- No cloud API -- OpenSky is called directly from the device; hero selection, filters, and airline badges all run on-device (`firmware/lib/hero.py`, `firmware/lib/filters.py`, `firmware/lib/enrich.py`, `firmware/lib/logos/`)
- If Wi-Fi drops, TailWatch retries the join for ~4 min (serial shows `wifi:` lines), moves the web UI to the new IP, and otherwise reboots into the setup AP.
- Hold the UP button for 5s for a Bad Apple!! easter egg (24s, plays without interrupting the web UI or ADS-B poll; hold UP again to stop it early).

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
leaves the filesystem read-only to `firmware/code.py`; a save attempted then
returns 503 and the device does not reboot.

## Next

1. ~~`firmware/lib/net.py`: OpenSky `/api/states/all` HTTPS client (bbox + `extended=1`)~~ -- done (issue #26)
2. ~~Draw the card with `displayio` / `terminalio` (`firmware/lib/card.py`)~~ -- done (issue #27)
3. ~~Wire `firmware/code.py`'s poll loop: net → filters → hero → enrich → card~~ -- done (issues #26, #27); `route`/`type`/`city`/`phase` stay blank, no on-device data source for them yet
4. ~~AP-mode first-boot if `CIRCUITPY_WIFI_SSID` is empty~~ -- done (issue #11)
5. Multi-aircraft card cycling (up to 5 jets, 12s each, no map) -- open (issue #20)
