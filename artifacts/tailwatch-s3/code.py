import time
import json
import board
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
from schedule import sleeping, brightness
from bbox import box
from dim import Dimmer, min_visible

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

pool = socketpool.SocketPool(wifi.radio)
try:
    ntp = adafruit_ntp.NTP(pool, tz_offset=0)
    rtc.RTC().datetime = ntp.datetime
except Exception as e:
    print("ntp failed", e)


def get_prefs(request: Request):
    return Response(request, json.dumps(load()), content_type="application/json")


def post_prefs(request: Request):
    global prefs
    form = {}
    is_json = request.headers.get("Content-Type", "").lower().startswith("application/json")
    try:
        if is_json:
            form = json.loads(request.body)
        else:
            # adafruit_httpserver splits fields but does NOT percent-decode,
            # and .get()/.items() HTML-escape values (safe=True) -- so read raw
            # values via fd[k] and decode them ourselves.
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
        return Response(
            request,
            json.dumps({"error": "invalid JSON body"}),
            content_type="application/json",
            status=Status(400, "Bad Request"),
        )
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
    if dimmer.apply(brightness(prefs)):
        print("brightness", dimmer.level)
    return Response(request, json.dumps(prefs), content_type="application/json")


def start_http():
    """Start the web UI on port 80. Returns the Server, or None on any failure.

    Port 80 is already taken if CircuitPython's Web Workflow is enabled
    (CIRCUITPY_WEB_API_PASSWORD in settings.toml) -- keep it off.
    """
    try:
        srv = Server(pool, "/www", debug=True)
        srv.route("/api/prefs", GET)(get_prefs)
        srv.route("/api/prefs", POST)(post_prefs)
        srv.start(str(wifi.radio.ipv4_address), 80)
    except Exception as e:
        print("http start failed", e)
        return None
    print("ui http://%s/" % wifi.radio.ipv4_address)
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
while True:
    if server is not None:
        try:
            server.poll()
        except Exception as e:
            print("http", e)

    prefs = load() if False else prefs  # UI save already updates global

    now = time.monotonic()
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
