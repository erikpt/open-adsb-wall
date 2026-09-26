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
from adafruit_httpserver import Server, Request, Response, GET, POST

from prefs import load, apply_form
from schedule import sleeping, brightness
from bbox import box

displayio.release_displays()

matrix = rgbmatrix.RGBMatrix(
    width=128,
    height=64,
    bit_depth=3,
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

prefs = load()
display.brightness = brightness(prefs)

pool = socketpool.SocketPool(wifi.radio)
try:
    ntp = adafruit_ntp.NTP(pool, tz_offset=0)
    rtc.RTC().datetime = ntp.datetime
except Exception as e:
    print("ntp failed", e)

server = Server(pool, "/www", debug=True)
try:
    server.start(str(wifi.radio.ipv4_address), 80)
    print("ui http://%s/" % wifi.radio.ipv4_address)
except Exception as e:
    print("http start failed", e)
    server = None


@server.route("/api/prefs", GET)
def get_prefs(request: Request):
    return Response(request, json.dumps(load()), content_type="application/json")


@server.route("/api/prefs", POST)
def post_prefs(request: Request):
    global prefs
    form = {}
    try:
        if request.headers.get("Content-Type", "").startswith("application/json"):
            form = json.loads(request.body)
        else:
            form = request.query_params or {}
            # application/x-www-form-urlencoded
            if request.body:
                for pair in request.body.decode().split("&"):
                    if "=" in pair:
                        k, v = pair.split("=", 1)
                        form[k] = v.replace("+", " ")
    except Exception as e:
        print("parse", e)
    prefs = apply_form(load(), form)
    display.brightness = brightness(prefs)
    return Response(request, json.dumps(prefs), content_type="application/json")


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
while True:
    if server:
        try:
            server.poll()
        except Exception as e:
            print("http", e)

    prefs = load() if False else prefs  # UI save already updates global
    br = brightness(prefs)
    display.brightness = br

    now = time.monotonic()
    if not sleeping(prefs) and now - last_poll > 15:
        last_poll = now
        try:
            card = poll_card()
            print(card)
        except Exception as e:
            print("poll", e)

    time.sleep(0.05)
