"""Host-side checks for lib/linkwatch.py (station Wi-Fi drop recovery).

Run: python3 tests/test_linkwatch.py
"""
import io
import os
import sys
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "firmware", "lib"))

import linkwatch  # noqa: E402
from linkwatch import (CHECK_S, DOWN, GAVE_UP, GRACE_S, MAX_RECONNECTS,  # noqa: E402
                       RETRY_GAP_S, UP, LinkWatch)

PW = "hunter2-secret"


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class Radio:
    """Fake wifi.radio. connect() advances the clock by `block` seconds."""

    def __init__(self, clock, ip="192.168.1.50"):
        self.clock = clock
        self.connected = True
        self.ipv4_address = ip
        self.connects = []
        self.join_ip = None      # IP a successful connect() yields; None = fail
        self.block = 10.0
        self.reads = 0

    def __getattribute__(self, name):
        if name == "ipv4_address":
            object.__setattr__(self, "reads", object.__getattribute__(self, "reads") + 1)
        return object.__getattribute__(self, name)

    def drop(self):
        self.connected = False
        self.ipv4_address = None

    def connect(self, ssid, pw, timeout=None):
        self.connects.append((ssid, pw, timeout, self.clock.t))
        self.clock.t += self.block if self.join_ip is None else 1.0
        if self.join_ip is None:
            raise ConnectionError("No network with that ssid")
        self.connected = True
        self.ipv4_address = self.join_ip


def make(ip="192.168.1.50"):
    c = Clock()
    r = Radio(c, ip)
    w = LinkWatch(r, "HomeNet", lambda: PW, ip, connect_timeout=10, clock=c)
    return c, r, w


def run(w, c, seconds, step=0.05):
    """Tick for `seconds` of fake time; return list of non-None events."""
    evs = []
    end = c.t + seconds
    while c.t < end:
        e = w.tick()
        if e is not None:
            evs.append(e)
        c.t += step
    return evs


def test_steady_up_no_events_and_throttled():
    c, r, w = make()
    r.reads = 0
    assert run(w, c, 20.0) == []
    assert w.state == UP
    # ~20 s / CHECK_S checks, not one per 50 ms loop pass
    assert r.reads <= int(20.0 / CHECK_S) + 2, r.reads


def test_drop_then_reconnect_same_ip():
    c, r, w = make()
    run(w, c, 3)
    r.drop()
    evs = run(w, c, CHECK_S + 0.1)
    assert evs == [("down",)] and w.state == DOWN and w.drops == 1
    # no connect() during the grace period
    run(w, c, GRACE_S - CHECK_S - 1)
    assert r.connects == []
    r.join_ip = "192.168.1.50"
    evs = run(w, c, 5)
    assert evs == [("up", "192.168.1.50", "192.168.1.50")], evs
    assert len(r.connects) == 1
    ssid, pw, timeout, _ = r.connects[0]
    assert (ssid, pw, timeout) == ("HomeNet", PW, 10)
    assert w.state == UP and w.tries == 0


def test_self_recovery_new_ip_without_connect():
    c, r, w = make()
    r.drop()
    run(w, c, CHECK_S + 0.1)
    r.connected = True
    r.ipv4_address = "192.168.1.77"
    evs = run(w, c, CHECK_S + 0.1)
    assert evs == [("up", "192.168.1.50", "192.168.1.77")], evs
    assert r.connects == [] and w.host == "192.168.1.77"


def test_ip_change_while_up():
    c, r, w = make()
    run(w, c, 3)
    r.ipv4_address = "10.0.0.9"
    evs = run(w, c, CHECK_S + 0.1)
    assert evs == [("up", "192.168.1.50", "10.0.0.9")], evs
    assert run(w, c, 10) == []


def test_bounded_retries_then_reset():
    c, r, w = make()
    r.drop()
    t_drop = c.t
    evs = run(w, c, 600)
    assert evs == [("down",), ("reset",)], evs
    assert len(r.connects) == MAX_RECONNECTS, len(r.connects)
    assert w.state == GAVE_UP
    # attempts honour grace + gaps (each failed connect blocks r.block s)
    t = [x[3] for x in r.connects]
    assert t[0] >= t_drop + GRACE_S
    for i in range(1, len(t)):
        assert t[i] - t[i - 1] >= r.block + RETRY_GAP_S[i - 1], (i, t)
    # once given up, it stays quiet (caller resets)
    assert run(w, c, 60) == [] and len(r.connects) == MAX_RECONNECTS


def test_recovery_after_some_failures_resets_counter():
    c, r, w = make()
    r.drop()
    run(w, c, GRACE_S + CHECK_S + 30)  # a couple of failed attempts
    assert 1 <= w.tries < MAX_RECONNECTS
    r.join_ip = "192.168.1.51"
    evs = run(w, c, 120)
    assert evs[-1] == ("up", "192.168.1.50", "192.168.1.51"), evs
    assert w.tries == 0 and w.state == UP
    r.drop()
    assert run(w, c, CHECK_S + 0.1) == [("down",)] and w.drops == 2


def test_radio_errors_count_as_down():
    class Broken:
        @property
        def connected(self):
            raise OSError("radio off")

    c = Clock()
    w = LinkWatch(Broken(), "HomeNet", lambda: PW, "1.2.3.4", clock=c)
    assert w.ip() is None
    assert w.tick() == ("down",)

    class NoConnectedAttr:  # older CircuitPython: fall back to ipv4_address only
        ipv4_address = "1.2.3.4"

    w = LinkWatch(NoConnectedAttr(), "HomeNet", lambda: PW, "1.2.3.4", clock=c)
    assert w.ip() == "1.2.3.4"


def test_password_never_printed():
    buf = io.StringIO()
    with redirect_stdout(buf):
        c, r, w = make()
        r.drop()
        run(w, c, 600)
    out = buf.getvalue()
    assert PW not in out
    for needle in ("link lost", "reconnect 1/%d to HomeNet" % MAX_RECONNECTS,
                   "failed", "hard reset"):
        assert needle in out, (needle, out)


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            n += 1
    print("ok", n, "tests")
