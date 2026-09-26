import time
import json
import os
import board
import microcontroller
import displayio
import framebufferio
import rgbmatrix
import wifi
import socketpool
import rtc
import adafruit_ntp
from adafruit_httpserver import Server, Request, Response, Status, GET, POST

from prefs import load, apply_form
from urldecode import unquote_plus
from schedule import sleeping, brightness, set_clock_synced, clock_synced, clock_trusted
from bbox import box
from dim import Dimmer, min_visible
import wifisettings

displayio.release_displays()

# rgbmatrix color depth. DESIGN.md caps MVP at 3-4; 4 gives 15 lit levels per
# channel (3 gives 7), which the color-scaling dimmer in lib/dim.py needs for
# the night slider to stay visibly distinct from gray labels. Drop to 3 if the
# panel flickers or the HTTP server gets sluggish on real hardware.
BIT_DEPTH = 4

matrix = rgbmatrix.RGBMatrix(
    width=128,
    height=64,
    bit_depth=BIT_DEPTH,
    rgb_pins=[
        board.MTX_R1, board.MTX_G1, board.MTX_B1,
        board.MTX_R2, board.MTX_G2, board.MTX_B2,
    ],
    addr_pins=[
        board.MTX_ADDRA, board.MTX_ADDRB, board.MTX_ADDRC,
        board.MTX_ADDRD, board.MTX_ADDRE,
    ],
    clock_pin=board.MTX_CLK,
    latch_pin=board.MTX_LAT,
    output_enable_pin=board.MTX_OE,
    tile=1,
    serpentine=False,
    doublebuffer=True,
)
display = framebufferio.FramebufferDisplay(matrix, auto_refresh=True)

# Placeholder content until lib/card.py exists: a 1 px white frame plus
# white / gray / amber bars, all drawn through one palette so the dimmer can
# rescale it. Deliberately sparse -- a full-white panel is ~15 W.
PLACEHOLDER_COLORS = (
    0x000000,  # 0 background
    0xFFFFFF,  # 1 white (frame + top bar): card text
    0x999999,  # 2 gray (middle bar): card labels
    0xFF7900,  # 3 amber (bottom bar): accent
)


def _make_placeholder():
    w, h = display.width, display.height
    bmp = displayio.Bitmap(w, h, len(PLACEHOLDER_COLORS))
    for x in range(w):
        bmp[x, 0] = 1
        bmp[x, h - 1] = 1
    for y in range(h):
        bmp[0, y] = 1
        bmp[w - 1, y] = 1
    for idx, y0 in ((1, 14), (2, 29), (3, 44)):
        for y in range(y0, y0 + 6):
            for x in range(8, w - 8):
                bmp[x, y] = idx
    pal = displayio.Palette(len(PLACEHOLDER_COLORS))
    group = displayio.Group()
    group.append(displayio.TileGrid(bmp, pixel_shader=pal))
    return group, pal


placeholder_group, placeholder_pal = _make_placeholder()
display.root_group = placeholder_group
dimmer = Dimmer(display, placeholder_group, displayio.Group(), floor=min_visible(BIT_DEPTH))
dimmer.add_palette(placeholder_pal, PLACEHOLDER_COLORS)

prefs = load()
dimmer.apply(brightness(prefs))
print("brightness", dimmer.level)

# ---- Network bring-up: join as a station, else fall back to a setup AP ----
# DESIGN.md sec. 7: "CIRCUITPY_WIFI_SSID empty or join fails for 20 s".
JOIN_ATTEMPTS = 2
JOIN_TIMEOUT_S = 10          # 2 x 10 s ~= the 20 s budget
AP_IDLE_RETRY_S = 600        # AP + configured SSID: reboot to retry after 10 min without UI traffic
AP_TEXT_COLOR = 0x707070     # fixed mid-gray setup text (dimmer not used in AP mode)
RESET_DELAY_S = 3.0          # let the POST /api/wifi response flush before resetting
NTP_RETRY_S = 300            # station mode, clock not yet synced
NTP_RESYNC_S = 86400         # station mode, daily re-sync for RTC drift
PW_ALPHABET = "abcdefghijkmnpqrstuvwxyz23456789"  # 32 chars, no l/o/0/1


def join_station():
    """(joined, configured_ssid). Never prints the password."""
    ssid = str(os.getenv("CIRCUITPY_WIFI_SSID") or "")
    if not ssid:
        return False, ""
    if wifi.radio.ipv4_address is not None:
        return True, ssid  # CircuitPython already auto-joined from settings.toml
    pw = str(os.getenv("CIRCUITPY_WIFI_PASSWORD") or "")
    for i in range(JOIN_ATTEMPTS):
        try:
            wifi.radio.connect(ssid, pw, timeout=JOIN_TIMEOUT_S)
            return True, ssid
        except Exception as e:  # ConnectionError (no AP / auth failed), ValueError (bad pw length)
            print("wifi join %d/%d failed: %s" % (i + 1, JOIN_ATTEMPTS, e))
    return False, ssid


def scan_networks(limit=12):
    """([{ssid, rssi}] strongest first, quietest of channels 1/6/11). Station must be up."""
    best = {}
    load_by_ch = {1: 0, 6: 0, 11: 0}
    try:
        for n in wifi.radio.start_scanning_networks():
            if n.channel in load_by_ch:
                load_by_ch[n.channel] += 1
            if n.ssid and (n.ssid not in best or n.rssi > best[n.ssid]):
                best[n.ssid] = n.rssi
    except Exception as e:
        print("scan", e)
    try:
        wifi.radio.stop_scanning_networks()
    except Exception:
        pass
    nets = sorted(best.items(), key=lambda kv: -kv[1])[:limit]
    chan = min((1, 6, 11), key=lambda c: load_by_ch[c])
    return [{"ssid": s, "rssi": r} for s, r in nets], chan


def start_setup_ap():
    """Start WPA2 AP TailWatch-XXXX with a fresh random password. Returns
    (ap_ssid, ap_password, host_ip, networks)."""
    nets, chan = scan_networks()  # scan first: ESP32-S3 can't scan once AP-only
    try:
        wifi.radio.stop_station()  # stop STA retries so the radio stays on the AP channel
    except Exception as e:
        print("stop_station", e)
    mac = wifi.radio.mac_address
    ap_ssid = "TailWatch-%02X%02X" % (mac[-2], mac[-1])
    ap_pw = "".join(PW_ALPHABET[b & 31] for b in os.urandom(8))
    wifi.radio.start_ap(
        ap_ssid,
        ap_pw,
        channel=chan,
        authmode=[wifi.AuthMode.WPA2, wifi.AuthMode.PSK],
        max_connections=2,
    )
    host_ip = str(wifi.radio.ipv4_address_ap or "192.168.4.1")
    return ap_ssid, ap_pw, host_ip, nets


def show_setup_screen(lines):
    from setupscreen import build  # lazy: only AP mode pays for adafruit_display_text
    display.root_group = build(lines, AP_TEXT_COLOR)
    display.brightness = 1.0  # never blank the setup screen (dimmer is bypassed in AP mode)


wifisettings.recover()  # finish an interrupted settings.toml swap before reading it
sta_ok, cfg_ssid = join_station()
ap_mode = not sta_ok
ap_ssid = ""
networks = []
if ap_mode:
    try:
        ap_ssid, ap_pw, host, networks = start_setup_ap()
    except Exception as e:
        print("AP start failed", e, "- rebooting in 60 s")
        time.sleep(60)
        microcontroller.reset()
    print("SETUP: join Wi-Fi %s password %s, open http://%s/" % (ap_ssid, ap_pw, host))
    try:
        show_setup_screen(("WIFI SETUP", ap_ssid, "pw " + ap_pw, host))
    except Exception as e:  # missing adafruit_display_text etc.: serial still has it
        print("setup screen", e)
else:
    host = str(wifi.radio.ipv4_address)

pool = socketpool.SocketPool(wifi.radio)
_ntp = None


def sync_clock():
    """NTP -> RTC (UTC). Marks the clock trusted for lib/schedule.py on success."""
    global _ntp
    try:
        if _ntp is None:
            _ntp = adafruit_ntp.NTP(pool, tz_offset=0, socket_timeout=5)
        rtc.RTC().datetime = _ntp.datetime
        set_clock_synced(True)
        print("ntp ok", time.time())
        return True
    except Exception as e:
        print("ntp failed", e)
        return False


if not ap_mode:  # no uplink in AP mode: skip the timeout
    sync_clock()
if not clock_trusted():
    print("clock not set: sleep/night schedule paused, day brightness")

reset_at = None                # monotonic deadline for microcontroller.reset()
last_api = time.monotonic()    # last /api/* request (AP idle-retry timer)


def _touch():
    global last_api
    last_api = time.monotonic()


def _json(request, obj, code=200, reason="OK"):
    return Response(request, json.dumps(obj), content_type="application/json",
                    status=Status(code, reason))


def _read_form(request, include_query=True):
    """(form dict, is_json); form is None for an unparseable JSON body."""
    form = {}
    is_json = request.headers.get("Content-Type", "").lower().startswith("application/json")
    try:
        if is_json:
            form = json.loads(request.body)
        else:
            # adafruit_httpserver splits fields but does NOT percent-decode,
            # and .get()/.items() HTML-escape values (safe=True) -- so read raw
            # values via fd[k] and decode them ourselves.
            if include_query:
                qp = request.query_params
                for k in qp:
                    form[unquote_plus(k)] = unquote_plus(qp[k])
            fd = request.form_data
            if fd is not None:
                urlenc = fd.content_type == "application/x-www-form-urlencoded"
                for k in fd:
                    v = fd[k]  # raw first value
                    if isinstance(v, bytes):
                        v = v.decode()
                    if urlenc:
                        k, v = unquote_plus(k), unquote_plus(v)
                    form[k] = v
    except Exception as e:
        print("parse", e)
        if is_json:
            form = None
    if is_json and not isinstance(form, dict):
        form = None
    return form, is_json


def get_prefs(request: Request):
    _touch()
    return Response(request, json.dumps(load()), content_type="application/json")


def post_prefs(request: Request):
    global prefs
    _touch()
    form, is_json = _read_form(request)
    if form is None:
        return _json(request, {"error": "invalid JSON body"}, 400, "Bad Request")
    try:
        prefs = apply_form(load(), form, partial=is_json)
    except OSError as e:
        print("prefs save failed", e)
        return Response(
            request,
            json.dumps({"error": "prefs storage read-only (booted with UP held?)"}),
            content_type="application/json",
            status=Status(503, "Service Unavailable"),
        )
    if not ap_mode and dimmer.apply(brightness(prefs)):
        print("brightness", dimmer.level)
    return Response(request, json.dumps(prefs), content_type="application/json")


def get_status(request: Request):
    _touch()
    return _json(request, {
        "mode": "ap" if ap_mode else "sta",
        "ip": host,
        "ssid": cfg_ssid,          # configured station SSID; the password is never returned
        "ap_ssid": ap_ssid,
        "networks": networks,      # scanned before the AP started ([] in station mode)
        "clock_synced": clock_synced(),
        "clock_trusted": clock_trusted(),
        "rebooting": reset_at is not None,
    })


def post_wifi(request: Request):
    """Allow-listed {ssid, password, open} -> /settings.toml, then hard reset."""
    global reset_at
    _touch()
    form, _ = _read_form(request, include_query=False)  # keep passwords out of URLs/logs
    if form is None:
        return _json(request, {"error": "invalid JSON body"}, 400, "Bad Request")
    try:
        ssid, pw = wifisettings.from_form(form)
        wifisettings.save(ssid, pw)
    except ValueError as e:
        return _json(request, {"error": str(e)}, 400, "Bad Request")
    except OSError as e:
        print("wifi save failed", e)
        return _json(request, {"error": "settings.toml read-only (booted with UP held?)"},
                     503, "Service Unavailable")
    print("wifi saved for", ssid, "- hard reset in", RESET_DELAY_S, "s")
    reset_at = time.monotonic() + RESET_DELAY_S
    return _json(request, {"ok": True, "ssid": ssid, "rebooting": True})


def start_http():
    """Start the web UI on port 80. Returns the Server, or None on any failure.

    Port 80 is already taken if CircuitPython's Web Workflow is enabled
    (CIRCUITPY_WEB_API_PASSWORD in settings.toml) -- keep it off.
    """
    try:
        srv = Server(pool, "/www", debug=True)
        srv.route("/api/prefs", GET)(get_prefs)
        srv.route("/api/prefs", POST)(post_prefs)
        srv.route("/api/status", GET)(get_status)
        srv.route("/api/wifi", POST)(post_wifi)
        srv.start(host, 80)  # station IP, or 192.168.4.1 in AP mode
    except Exception as e:
        print("http start failed", e)
        return None
    print("ui http://%s/" % host)
    return srv


server = start_http()


def poll_card():
    """Replace with HTTPS GET prefs['api']/v1/nearby?... later."""
    b = box(prefs["lat"], prefs["lon"], prefs["nm"])
    print("box", b)
    return {
        "flight": "NO DATA",
        "airline": "",
        "route": "",
        "type": "",
        "city": "",
        "phase": "",
    }


last_poll = 0
last_bright = 0
last_ntp_try = time.monotonic()
while True:
    if server is not None:
        try:
            server.poll()
        except Exception as e:
            print("http", e)

    now = time.monotonic()
    if reset_at is not None and now >= reset_at:
        microcontroller.reset()  # hard reset: boot.py + settings.toml re-read, fresh radio

    if ap_mode:
        # Configured network down (router rebooting, outage)? Retry it by
        # rebooting once nobody has used the setup UI for AP_IDLE_RETRY_S.
        # With no SSID configured, stay in setup mode indefinitely.
        if cfg_ssid and reset_at is None and now - last_api >= AP_IDLE_RETRY_S:
            print("setup AP idle; rebooting to retry", cfg_ssid)
            microcontroller.reset()
        time.sleep(0.05)
        continue

    prefs = load() if False else prefs  # UI save already updates global

    if now - last_ntp_try >= (NTP_RESYNC_S if clock_synced() else NTP_RETRY_S):
        last_ntp_try = now
        sync_clock()

    # Re-evaluate the schedule ~1 s (DESIGN.md sec. 6); the dimmer only touches
    # the display when the level actually changes. post_prefs applies saves
    # immediately, so the throttle never delays a slider change.
    if now - last_bright >= 1.0:
        last_bright = now
        if dimmer.apply(brightness(prefs)):
            print("brightness", dimmer.level)

    if not sleeping(prefs) and now - last_poll > 15:
        last_poll = now
        try:
            card = poll_card()
            print(card)
        except Exception as e:
            print("poll", e)

    time.sleep(0.05)
