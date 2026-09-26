# TailWatch S3 (starter)

MatrixPortal S3 + 128x64 HUB75 panel.

## On the CIRCUITPY drive

- `boot.py`
- `code.py`
- `prefs.json` (copy from `prefs.example.json`)
- `settings.toml` (Wi-Fi only -- copy from `settings.toml.example`; do **not** set `CIRCUITPY_WEB_API_PASSWORD`)
- `www/index.html`
- `lib/prefs.py`, `lib/sun.py`, `lib/schedule.py`, `lib/bbox.py`, `lib/urldecode.py`, `lib/tz.py`, `lib/dim.py`

Libraries from the CircuitPython bundle:

- `adafruit_httpserver`
- `adafruit_ntp`

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
- 10 miles each way → OpenSky-style bbox (printed to serial until the cloud API is wired)

## Next

1. Point `api` at the Cloudflare/Linode worker
2. Implement `poll_card()` as HTTPS GET `/v1/nearby`
3. Draw the returned card with `displayio` / `terminalio`
4. AP-mode first-boot if `CIRCUITPY_WIFI_SSID` is empty
