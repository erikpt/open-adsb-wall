"""Host simulation of code.py (fake CircuitPython modules, reusing the
tests/test_code_linkwatch.py harness): a sleep window blanks the panel and
suppresses the ADS-B poll; awake, the poll's bbox comes from the saved pin.

Run: python3 tests/test_code_schedule.py   (from the tailwatch-s3 root)
"""
import ast
import json
import os
import sys
import tempfile
import time as _time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_code_linkwatch as sim  # noqa: E402  (also puts lib/ on sys.path)
import prefs  # noqa: E402
import schedule  # noqa: E402
from bbox import box  # noqa: E402

T_2025 = 1735689600  # 2025-01-01 00:00Z = 18:00 CST (Jan: no DST)


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
    try:
        return sim.run({}, end)
    finally:
        _time.time = real_time
        prefs.PATH, prefs.BACKUP = old


def box_lines(out):
    return [ast.literal_eval(line[4:]) for line in out.splitlines() if line.startswith("box {")]


def test_sleep_window_blanks_and_skips_poll():
    outcome, out = run_with({"sleep_enabled": True, "sleep_start": "17:30",
                             "sleep_end": "06:30", "tz_offset_min": -360, "us_dst": True})
    assert outcome == "stop", (outcome, out[-800:])
    assert "brightness 0.0" in out, out
    assert box_lines(out) == [], "polled while asleep:\n" + out


def test_awake_polls_with_saved_pin():
    pin = {"lat": 47.6062, "lon": -122.3321, "nm": 5,
           "sleep_enabled": False, "night_mode": "off", "brightness_day": 0.6}
    outcome, out = run_with(pin)
    assert outcome == "stop", (outcome, out[-800:])
    assert "brightness 0.6" in out, out
    boxes = box_lines(out)
    assert len(boxes) >= 2, out           # one poll per 15 s over 60 s
    want = box(47.6062, -122.3321, 5)
    for k in want:
        assert abs(boxes[0][k] - want[k]) < 1e-9, (k, boxes[0], want)


if __name__ == "__main__":
    n = 0
    for name in sorted(k for k in dir() if k.startswith("test_")):
        globals()[name]()
        print("ok", name)
        n += 1
    print("ok", n, "tests")
