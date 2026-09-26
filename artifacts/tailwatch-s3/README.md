# TailWatch S3 (starter)

MatrixPortal S3 + 128x64 HUB75 panel.

## On the CIRCUITPY drive

- `code.py`
- `prefs.json` (copy from `prefs.example.json`)
- `settings.toml` (Wi-Fi)
- `www/index.html`
- `lib/prefs.py`, `lib/sun.py`, `lib/schedule.py`, `lib/bbox.py`

Libraries from the CircuitPython bundle:

- `adafruit_httpserver`
- `adafruit_ntp`

## Behavior

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
