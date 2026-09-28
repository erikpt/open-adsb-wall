"""Host simulation of code.py (fake CircuitPython modules, reusing the
tests/test_code_linkwatch.py harness): a sleep window blanks the panel and
suppresses the ADS-B poll; awake, the poll's bbox comes from the saved pin.

Run: python3 tests/test_code_schedule.py   (from the tailwatch-s3 root)
"""
import json
import os
import sys
import tempfile
import time as _time
import types
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_code_linkwatch as sim  # noqa: E402  (also puts lib/ on sys.path)
import prefs  # noqa: E402
import schedule  # noqa: E402
from bbox import box  # noqa: E402

T_2025 = 1735689600  # 2025-01-01 00:00Z = 18:00 CST (Jan: no DST)
_orig_fake_modules = sim.fake_modules


class FakeHTTPStatusError(Exception):
    def __init__(self, status, retry_after=None):
        super().__init__("HTTP %d" % status)
        self.status = status
        self.retry_after = retry_after


def _net_fake_modules():
    """The station harness, plus a fake lib/httpclient.py so poll_card()'s
    real lib/net.py -> lib/httpclient.py call never touches a real socket.
    Every call is logged to sim.W.net_calls instead (issue #26: this used to
    just check the poll_card() stub's own "box {...}" print line -- now that
    the fetch is real, count/inspect the fake transport call instead, per
    DESIGN.md sec. 13)."""
    m = _orig_fake_modules()
    sim.W.net_calls = []  # [url] per successful/attempted get_json() call

    def get_json(pool, url, headers=None, **kw):
        sim.W.net_calls.append(url)
        return {"time": int(sim.W.t), "states": []}  # empty sky: keeps hero.select() harmless

    m["httpclient"] = types.ModuleType("httpclient")
    m["httpclient"].get_json = get_json
    m["httpclient"].HTTPStatusError = FakeHTTPStatusError
    m["httpclient"].reset = lambda: None
    return m


def run_with(p, end=60):
    """Run code.py with /prefs.json = p and a trusted wall clock at T_2025."""
    d = tempfile.mkdtemp()
    old = prefs.PATH, prefs.BACKUP
    prefs.PATH = os.path.join(d, "prefs.json")
    prefs.BACKUP = os.path.join(d, "prefs.bak")
    with open(prefs.PATH, "w") as f:
        json.dump(p, f)
    real_time = _time.time
    _time.time = lambda: T_2025 + sim.W.t
    schedule.set_clock_synced(False)  # NTP always fails in the sim
    sim.fake_modules = _net_fake_modules
    try:
        return sim.run({}, end)
    finally:
        sim.fake_modules = _orig_fake_modules
        _time.time = real_time
        prefs.PATH, prefs.BACKUP = old


def bbox_of(url):
    """{lamin, lamax, lomin, lomax} parsed back out of a lib/net.py URL."""
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
    return {k: float(q[k]) for k in ("lamin", "lamax", "lomin", "lomax")}


def test_sleep_window_blanks_and_skips_poll():
    outcome, out = run_with({"sleep_enabled": True, "sleep_start": "17:30",
                             "sleep_end": "06:30", "tz_offset_min": -360, "us_dst": True})
    assert outcome == "stop", (outcome, out[-800:])
    assert "brightness 0.0" in out, out
    assert sim.W.net_calls == [], "polled while asleep:\n" + out


def test_awake_polls_with_saved_pin():
    pin = {"lat": 47.6062, "lon": -122.3321, "nm": 5,
           "sleep_enabled": False, "night_mode": "off", "brightness_day": 0.6}
    outcome, out = run_with(pin)
    assert outcome == "stop", (outcome, out[-800:])
    assert "brightness 0.6" in out, out
    calls = sim.W.net_calls
    assert len(calls) >= 2, out           # one poll per 15 s over 60 s
    assert "/states/all" in calls[0] and "extended=1" in calls[0], calls[0]
    want = box(47.6062, -122.3321, 5)
    got = bbox_of(calls[0])
    for k in want:
        assert abs(got[k] - want[k]) < 1e-6, (k, got, want)


if __name__ == "__main__":
    n = 0
    for name in sorted(k for k in dir() if k.startswith("test_")):
        globals()[name]()
        print("ok", name)
        n += 1
    print("ok", n, "tests")
