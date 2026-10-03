import time
import json
import os
import gc
import board
import microcontroller
import displayio
import framebufferio
import rgbmatrix
import wifi
import socketpool
import rtc
import adafruit_ntp
from adafruit_httpserver import Server, Request, Response, Status, GET, POST, Redirect

from prefs import load, apply_form, public
from urldecode import unquote_plus
from schedule import sleeping, brightness, set_clock_synced, clock_synced, clock_trusted
from tz import local_minutes
from dim import Dimmer, min_visible
import wifisettings
import httpclient
import reqguard
import net
import filters
import enrich
from hero import Hero, candidates as hero_candidates
from card import Card
from captiveportal import CaptiveDNS
from linkwatch import LinkWatch, UP as LINK_UP

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

card_widget = Card()  # issue #27: owns the real card's displayio.Group
display.root_group = card_widget.group
dimmer = Dimmer(display, card_widget.group, displayio.Group(), floor=min_visible(BIT_DEPTH))
card_widget.show_message("NO TRAFFIC")  # shown until the first poll completes

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
HTTP_FAIL_LIMIT = 5          # consecutive server.poll() exceptions -> restart the server
HTTP_RETRY_S = 30            # server failed to start: retry this often
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

# Station mode only: re-join after a Wi-Fi drop and move the web UI to the
# new address (lib/linkwatch.py). AP mode has its own idle-reboot retry.
link = None
if not ap_mode:
    link = LinkWatch(
        wifi.radio, cfg_ssid,
        lambda: str(os.getenv("CIRCUITPY_WIFI_PASSWORD") or ""),
        host, connect_timeout=JOIN_TIMEOUT_S,
    )

pool = socketpool.SocketPool(wifi.radio)
_ntp = None

# AP mode only (issue #21): answer every DNS query with our own IP so a
# joining phone/laptop's captive-portal detection probes resolve to us
# instead of timing out (there's no internet to resolve anything for real),
# which is what makes the OS auto-pop its sign-in browser -- see the
# CAPTIVE_CHECK_PATHS routes below for the HTTP side of that handshake.
captive_dns = None
if ap_mode:
    try:
        captive_dns = CaptiveDNS(pool, host)
    except Exception as e:
        print("captiveportal: DNS start failed", e)  # setup still reachable at the AP's own IP


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


def _guard(request, write):
    """403 Response if the request isn't same-origin for this device, else None.
    Reads the global `host`, so it follows LinkWatch IP changes and AP mode."""
    h = request.headers  # adafruit_httpserver Headers: case-insensitive .get
    why = reqguard.check(h.get("Host"), h.get("Origin"), h.get("Referer"), host, write)
    if why is None:
        return None
    print("api 403:", why)
    return _json(request, {"error": "forbidden: " + why}, 403, "Forbidden")


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
    bad = _guard(request, False)
    if bad:
        return bad
    _touch()
    return _json(request, public(load()))


def post_prefs(request: Request):
    global prefs
    bad = _guard(request, True)
    if bad:
        return bad
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
    return _json(request, public(prefs))


def get_status(request: Request):
    bad = _guard(request, False)
    if bad:
        return bad
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
        "wifi_drops": link.drops if link is not None else 0,  # station outages since boot
    })


def post_wifi(request: Request):
    """Allow-listed {ssid, password, open} -> /settings.toml, then hard reset."""
    global reset_at
    bad = _guard(request, True)
    if bad:
        return bad
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


# AP mode only (issue #21): known captive-portal detection probe paths.
# Each OS expects a specific exact response (Android: 204 + empty body,
# Apple: 200 + one exact HTML string, Windows: specific plain-text bodies)
# and treats *anything else* as "there's a portal" -- so redirecting these
# to the setup page, rather than trying to impersonate the expected body, is
# what makes the OS auto-launch its captive sign-in browser here instead of
# just flagging "limited connectivity" and leaving the user to find the IP.
CAPTIVE_CHECK_PATHS = (
    "/generate_204", "/gen_204",                            # Android
    "/hotspot-detect.html", "/library/test/success.html",   # Apple
    "/connecttest.txt", "/ncsi.txt", "/redirect",           # Windows
    "/success.txt",                                          # Firefox
)


def captive_redirect(request: Request):
    return Redirect(request, "http://%s/" % host)


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
        if ap_mode:
            for p in CAPTIVE_CHECK_PATHS:
                srv.route(p, GET)(captive_redirect)
        srv.start(host, 80)  # station IP, or 192.168.4.1 in AP mode
    except Exception as e:
        print("http start failed", e)
        return None
    print("ui http://%s/" % host)
    return srv


server = start_http()
http_fails = 0                  # consecutive server.poll() exceptions
last_http_try = time.monotonic()


def restart_http(why):
    """Stop the web UI server (if any) and start a fresh one on `host`."""
    global server, http_fails, last_http_try
    print("http: restarting on %s (%s)" % (host, why))
    if server is not None:
        try:
            server.stop()
        except Exception as e:  # socket already dead with the old link
            print("http stop", e)
    server = None
    gc.collect()
    server = start_http()
    http_fails = 0
    last_http_try = time.monotonic()


hero = Hero(poll_s=15)  # DESIGN.md sec. 8: on-device hero selection (issue #2)

M_TO_FT = 3.280840    # OpenSky altitude is meters; the card shape is feet (DESIGN.md sec. 8)
MPS_TO_KT = 1.943844  # OpenSky velocity is m/s; the card shape is knots (DESIGN.md sec. 8)


def poll_card():
    """lib/net.py -> lib/filters.py -> lib/hero.py, assembled into a card dict.

    Raises whatever lib/net.py's OpenSky fetch raises (httpclient.HTTPStatusError
    on a non-200, OSError / RuntimeError / TimeoutError / ValueError otherwise) --
    the caller (the main loop, below) is what turns that into "keep the last
    good card" per DESIGN.md sec. 8; this function never swallows a failure or
    guesses at that policy itself. Only call it while link.state == LINK_UP
    (the main loop already gates poll_card() on that).

    route/type/city/phase are not populated: nothing on-device (no cloud tier,
    issue #2) currently supplies flight-route, aircraft-type, or airport/phase
    data for a raw ADS-B state vector -- lib/hero.py's own docstring only
    promises position/altitude/speed/track from OpenSky. Left as "" rather
    than invented, same shape DESIGN.md sec. 8's card documents either way.
    """
    resp = net.poll(pool, prefs)
    cands = filters.apply(hero_candidates(resp, prefs["lat"], prefs["lon"]), prefs)
    c, why = hero.select(cands, time.monotonic())
    print("hero", why, c["hex"] if c else None)
    if c is None:
        return {"flight": None, "airline": "", "logo": None, "route": "", "type": "",
                "city": "", "phase": "", "alt": None, "spd": None, "track": None,
                "hex": None, "age_s": None}
    enr = enrich.lookup(c["cs"])
    return {
        "flight": c["cs"] or c["hex"],
        "airline": enr[0] if enr else "",
        "logo": enr[1] if enr else None,
        "route": "",
        "type": "",
        "city": "",
        "phase": "",
        "alt": None if c["alt"] is None else c["alt"] * M_TO_FT,
        "spd": None if c["spd"] is None else c["spd"] * MPS_TO_KT,
        "track": c["trk"],
        "hex": c["hex"],
        "age_s": c["age"],
    }


last_poll = 0
poll_backoff_until = 0   # monotonic deadline; set past a 429's Retry-After
last_card = None         # last successfully assembled card (kept across failed polls)
last_poll_ok_at = time.monotonic()  # last successful poll_card(); starts "now" for a boot grace period
last_bright = 0
last_ntp_try = time.monotonic()


def _local_hhmm():
    """"HH:MM" for DESIGN.md sec. 9's "NO TRAFFIC + local time", or None if
    the clock isn't trusted yet (schedule.clock_trusted()) -- an untrusted
    clock showing a wrong/epoch time would be worse than showing none."""
    if not clock_trusted():
        return None
    h, m = divmod(local_minutes(prefs["tz_offset_min"], prefs["us_dst"]), 60)
    return "%02d:%02d" % (h, m)


def refresh_display(now):
    """NO LINK once nothing has confirmed data for hero.max_stale_s (issue #27);
    otherwise render last_card (NO TRAFFIC is just last_card's flight: None
    case, handled inside Card.show_card()). Using the same max_stale_s
    lib/hero.py already uses for "is the hero gone" keeps one staleness
    policy instead of a second timeout invented here -- and, unlike
    hero.expired() alone, this also covers "never had any data at all"
    (hero.hex stays None forever) and "OpenSky keeps returning an empty sky
    successfully" (correctly NOT a link-down state) alike. last_poll_ok_at
    starts at boot time (not None/never), so the first ~15 s before the
    first poll completes reads as a grace period, not an instant NO LINK."""
    link_down = now - last_poll_ok_at > hero.max_stale_s
    if link_down:
        card_widget.show_message("NO LINK")
        print("display NO LINK")
    elif last_card is None:  # within the boot grace period, first poll not back yet
        card_widget.show_message("NO TRAFFIC", _local_hhmm())
        print("display NO TRAFFIC")
    else:
        card_widget.show_card(last_card, dimmer, _local_hhmm())
        print("display", last_card.get("flight") or "NO TRAFFIC")
while True:
    # Skip while the station link is down: nothing can reach the UI, and a
    # dead listening socket would otherwise log an error every pass.
    if server is not None and (link is None or link.state == LINK_UP):
        try:
            server.poll()
            http_fails = 0
        except Exception as e:
            http_fails += 1
            print("http", e)
            if http_fails >= HTTP_FAIL_LIMIT:
                restart_http("%d consecutive poll errors" % http_fails)

    now = time.monotonic()
    if reset_at is not None and now >= reset_at:
        microcontroller.reset()  # hard reset: boot.py + settings.toml re-read, fresh radio

    if server is None and now - last_http_try >= HTTP_RETRY_S and (
            link is None or link.state == LINK_UP):
        restart_http("not running")

    if link is not None and reset_at is None:
        ev = link.tick()  # may block up to JOIN_TIMEOUT_S while reconnecting
        if ev is not None:
            if ev[0] == "down":
                httpclient.reset()  # pooled outbound sockets died with the link
            elif ev[0] == "up":
                host = ev[2]
                httpclient.reset()
                restart_http("wifi up" if ev[1] == ev[2] else "ip %s -> %s" % (ev[1], ev[2]))
                if not clock_synced():
                    last_ntp_try = now - NTP_RETRY_S  # retry NTP now, not in up to 5 min
            elif ev[0] == "reset":
                # Boots, fails the ~20 s join, and comes up as the setup AP,
                # which itself reboots to retry after AP_IDLE_RETRY_S idle.
                microcontroller.reset()
        now = time.monotonic()  # tick() may have blocked
    online = link is not None and link.state == LINK_UP

    if ap_mode:
        if captive_dns is not None:
            captive_dns.poll()
        # Configured network down (router rebooting, outage)? Retry it by
        # rebooting once nobody has used the setup UI for AP_IDLE_RETRY_S.
        # With no SSID configured, stay in setup mode indefinitely.
        if cfg_ssid and reset_at is None and now - last_api >= AP_IDLE_RETRY_S:
            print("setup AP idle; rebooting to retry", cfg_ssid)
            microcontroller.reset()
        time.sleep(0.05)
        continue

    prefs = load() if False else prefs  # UI save already updates global

    if online and now - last_ntp_try >= (NTP_RESYNC_S if clock_synced() else NTP_RETRY_S):
        last_ntp_try = now
        sync_clock()

    # Re-evaluate the schedule ~1 s (DESIGN.md sec. 6); the dimmer only touches
    # the display when the level actually changes. post_prefs applies saves
    # immediately, so the throttle never delays a slider change.
    if now - last_bright >= 1.0:
        last_bright = now
        if dimmer.apply(brightness(prefs)):
            print("brightness", dimmer.level)
        refresh_display(now)  # catches a hero/link going stale between polls

    if online and not sleeping(prefs) and now >= poll_backoff_until and now - last_poll > 15:
        last_poll = now
        try:
            last_card = poll_card()
            last_poll_ok_at = now
            print(last_card)
            refresh_display(now)
        except httpclient.HTTPStatusError as e:
            if e.retry_after:
                poll_backoff_until = now + e.retry_after
            print("poll http", e.status, "retry_after", e.retry_after)
        except Exception as e:
            print("poll", e)  # OSError / RuntimeError / TimeoutError / ValueError: keep last_card

    time.sleep(0.05)
