"""Host simulation of code.py's main loop with fake CircuitPython modules:
drop Wi-Fi, bring it back on a new IP, and check the web UI server moves.

Run: python3 tests/sim_code_link.py   (from the tailwatch-s3 root)
"""
import io
import os
import runpy
import sys
import time as _time
import types
from contextlib import redirect_stdout

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "firmware", "lib"))
CODE = os.path.join(ROOT, "firmware", "code.py")


class Reset(Exception):
    pass


class Stop(Exception):
    pass


class World:
    def __init__(self):
        self.t = 0.0
        self.end = 1e9
        self.events = {}         # time -> callable(world)
        self.starts = []         # (t, host) per Server.start
        self.stops = 0
        self.poll_raises = False
        self.resets = []
        self.connects = []
        self.join_ip = None
        self.dns_queries = []    # [(bytes, addr)] fed to the next recvfrom_into
        self.dns_sent = []       # [(bytes, addr)] captured from CaptiveDNS.sendto
        self.dns_socket = None   # the most recently created fake UDP socket
        self.routes = []         # [(path, method)] registered via Server.route


W = World()


def fake_modules():
    m = {}

    def mod(name, **kw):
        x = types.ModuleType(name)
        for k, v in kw.items():
            setattr(x, k, v)
        m[name] = x
        return x

    class Any:
        def __init__(self, *a, **k):
            self.width, self.height = 128, 64
            self.brightness = 1.0
            self.root_group = None

        def __getattr__(self, n):
            return Any()

        def __call__(self, *a, **k):
            return Any()

    class Bitmap:
        def __init__(self, w, h, n):
            self.d = {}

        def __setitem__(self, k, v):
            self.d[k] = v

    class Palette(list):
        def __init__(self, n):
            super().__init__([0] * n)

    class Group(list):
        hidden = False

    mod("board", **{n: object() for n in (
        "MTX_R1 MTX_G1 MTX_B1 MTX_R2 MTX_G2 MTX_B2 MTX_ADDRA MTX_ADDRB "
        "MTX_ADDRC MTX_ADDRD MTX_ADDRE MTX_CLK MTX_LAT MTX_OE").split()})

    def reset():
        W.resets.append(W.t)
        raise Reset()

    mod("microcontroller", reset=reset)
    mod("displayio", release_displays=lambda: None, Bitmap=Bitmap, Palette=Palette,
        Group=Group, TileGrid=lambda *a, **k: object())
    mod("framebufferio", FramebufferDisplay=Any)
    mod("rgbmatrix", RGBMatrix=Any)

    class Radio:
        connected = True
        ipv4_address = "192.168.1.50"
        ipv4_address_ap = None
        mac_address = b"\x00\x01\x02\x03\x04\x05"

        def connect(self, ssid, pw, timeout=None):
            W.connects.append((W.t, ssid))
            W.t += 1.0 if W.join_ip else float(timeout or 10)
            if not W.join_ip:
                raise ConnectionError("No network with that ssid")
            self.connected = True
            self.ipv4_address = W.join_ip

    W.radio = Radio()
    mod("wifi", radio=W.radio)

    class FakeUDPSocket:
        def __init__(self):
            self.blocking = True
            self.bound = None
            self.sent = []       # [(bytes, addr)]

        def setblocking(self, flag):
            self.blocking = flag

        def bind(self, addr):
            self.bound = addr

        def recvfrom_into(self, buf):
            if not W.dns_queries:
                raise OSError("no data")
            data, addr = W.dns_queries.pop(0)
            buf[:len(data)] = data
            return len(data), addr

        def sendto(self, data, addr):
            self.sent.append((data, addr))
            W.dns_sent.append((data, addr))

    class FakePool:
        AF_INET = 0
        SOCK_DGRAM = 1

        def __init__(self, radio):
            pass

        def socket(self, family, type_):
            sock = FakeUDPSocket()
            W.dns_socket = sock
            return sock

    mod("socketpool", SocketPool=FakePool)

    class RTC:
        datetime = None

    mod("rtc", RTC=RTC)

    class NTP:
        def __init__(self, *a, **k):
            pass

        @property
        def datetime(self):
            raise OSError("no ntp in sim")

    mod("adafruit_ntp", NTP=NTP)

    class Server:
        def __init__(self, pool, root, debug=False):
            self.stopped = True

        def route(self, path, method):
            W.routes.append((path, method))
            return lambda f: f

        def start(self, host, port):
            W.starts.append((W.t, host))
            self.stopped = False

        def stop(self):
            W.stops += 1
            self.stopped = True

        def poll(self):
            if W.poll_raises:
                raise OSError(9, "EBADF")
            return "no_request"

    class Redirect:
        def __init__(self, request, url, **kw):
            self.url = url

    mod("adafruit_httpserver", Server=Server, Request=object, Response=object,
        Status=lambda *a: a, GET="GET", POST="POST", Redirect=Redirect)
    return m


def run(events, end):
    W.__init__()
    W.events = dict(events)
    W.end = end
    mods = fake_modules()
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    real_mono, real_sleep = _time.monotonic, _time.sleep

    def mono():
        return W.t

    def sleep(s):
        W.t += s
        for at in sorted(list(W.events)):
            if W.t >= at:
                W.events.pop(at)(W)
        if W.t >= W.end:
            raise Stop()

    _time.monotonic, _time.sleep = mono, sleep
    os.environ["CIRCUITPY_WIFI_SSID"] = "HomeNet"
    os.environ["CIRCUITPY_WIFI_PASSWORD"] = "hunter2-secret"
    # net.py binds `import httpclient` once at import time, so it must be
    # re-imported every run too, or a later run's fake httpclient silently
    # never takes effect (it'd still call the first run's closed-over fake).
    # hero/filters/enrich hold no cross-run state but are evicted alongside
    # it for the same reason, cheaply, in case that ever changes.
    for name in ("linkwatch", "httpclient", "net", "hero", "filters", "enrich"):
        if name not in mods:  # a fake_modules() override may supply its own
            sys.modules.pop(name, None)
    buf = io.StringIO()
    outcome = None
    try:
        with redirect_stdout(buf):
            runpy.run_path(CODE, run_name="__main__")
    except Stop:
        outcome = "stop"
    except Reset:
        outcome = "reset"
    finally:
        _time.monotonic, _time.sleep = real_mono, real_sleep
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return outcome, buf.getvalue()


def drop(w):
    w.radio.connected = False
    w.radio.ipv4_address = None


def test_drop_and_rejoin_new_ip():
    def back(w):
        w.join_ip = "192.168.1.77"

    outcome, out = run({100: drop, 130: back}, 300)
    assert outcome == "stop", (outcome, out[-800:])
    hosts = [h for _, h in W.starts]
    assert hosts[0] == "192.168.1.50" and hosts[-1] == "192.168.1.77", (hosts, out)
    assert W.stops >= 1
    for needle in ("wifi: link lost", "wifi: reconnect 1/", "wifi: link up, ip 192.168.1.77",
                   "http: restarting on 192.168.1.77", "ui http://192.168.1.77/"):
        assert needle in out, (needle, out)
    assert "hunter2-secret" not in out
    assert out.count("\nhttp ") == 0, "server polled while link down"


def test_gives_up_and_resets():
    outcome, out = run({100: drop}, 2000)
    assert outcome == "reset", (outcome, out[-800:])
    assert 100 + 200 <= W.resets[0] <= 100 + 400, W.resets
    assert "hard reset" in out


def test_server_socket_errors_restart_server():
    def bad(w):
        w.poll_raises = True

    def good(w):
        w.poll_raises = False

    outcome, out = run({50: bad, 50.3: good}, 120)
    assert outcome == "stop"
    assert "consecutive poll errors" in out, out
    assert len(W.starts) == 2 and W.starts[1][1] == "192.168.1.50"


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            n += 1
    print("ok", n, "tests")
