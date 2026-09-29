"""Host simulation of code.py's real poll wiring (issue #26): lib/net.py ->
lib/filters.py -> lib/hero.py -> lib/enrich.py, assembled by poll_card() and
printed once per successful/attempted poll. Reuses the tests/test_code_linkwatch.py
harness, faking lib/httpclient.py so no real socket is ever touched -- see
tests/test_code_schedule.py for the same technique applied to bbox/schedule
timing instead of card content.

Run: python3 tests/test_code_poll.py   (from the repo root)
"""
import ast
import json
import os
import sys
import tempfile
import time as _time
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_code_linkwatch as sim  # noqa: E402  (also puts firmware/lib/ on sys.path)
import prefs  # noqa: E402
import schedule  # noqa: E402

T_2025 = 1735689600
_orig_fake_modules = sim.fake_modules

# A realistic /states/all row for a United flight near the test pin
# (47.6062, -122.3321). Indices per lib/hero.py's OpenSky state-vector map.
UAL_STATE = [
    "abc123",        # 0  icao24
    "UAL123  ",      # 1  callsign (OpenSky pads to 8 chars)
    "United States", # 2  origin_country
    1735689500,      # 3  time_position
    1735689500,      # 4  last_contact
    -122.34,         # 5  longitude
    47.61,           # 6  latitude
    3000.0,          # 7  baro_altitude
    False,           # 8  on_ground
    200.0,           # 9  velocity
    90.0,            # 10 true_track
    0.0,             # 11 vertical_rate
    None,            # 12 sensors
    3100.0,          # 13 geo_altitude
    None,            # 14 squawk
    False,           # 15 spi
    0,               # 16 position_source
    4,               # 17 category: CAT_LARGE (airliner-sized)
]


class FakeHTTPStatusError(Exception):
    def __init__(self, status, retry_after=None):
        super().__init__("HTTP %d" % status)
        self.status = status
        self.retry_after = retry_after


def _fake_modules_returning(states_by_call):
    """states_by_call: list of ("ok", states-list) | ("http", status, retry_after)
    | ("err", exception) -- one per successful get_json() call, repeating the
    last entry once the list is exhausted."""

    def make():
        m = _orig_fake_modules()
        sim.W.net_calls = []

        def get_json(pool, url, headers=None, **kw):
            i = min(len(sim.W.net_calls), len(states_by_call) - 1)
            sim.W.net_calls.append(url)
            spec = states_by_call[i]
            if spec[0] == "ok":
                return {"time": 1735689500, "states": spec[1]}
            if spec[0] == "http":
                raise FakeHTTPStatusError(spec[1], retry_after=spec[2])
            raise spec[1]

        m["httpclient"] = types.ModuleType("httpclient")
        m["httpclient"].get_json = get_json
        m["httpclient"].HTTPStatusError = FakeHTTPStatusError
        m["httpclient"].reset = lambda: None
        return m

    return make


def run_with(p, states_by_call, end=35):
    d = tempfile.mkdtemp()
    old = prefs.PATH, prefs.BACKUP
    prefs.PATH = os.path.join(d, "prefs.json")
    prefs.BACKUP = os.path.join(d, "prefs.bak")
    with open(prefs.PATH, "w") as f:
        json.dump(p, f)
    real_time = _time.time
    _time.time = lambda: T_2025 + sim.W.t
    schedule.set_clock_synced(False)
    sim.fake_modules = _fake_modules_returning(states_by_call)
    try:
        return sim.run({}, end)
    finally:
        sim.fake_modules = _orig_fake_modules
        _time.time = real_time
        prefs.PATH, prefs.BACKUP = old


PIN = {"lat": 47.6062, "lon": -122.3321, "nm": 5,
       "sleep_enabled": False, "night_mode": "off"}


def _cards(out):
    """Every dict poll_card() printed, in order (print(last_card) each success)."""
    cards = []
    for line in out.splitlines():
        if line.startswith("{") and "'flight'" in line:
            cards.append(ast.literal_eval(line))
    return cards


def test_real_aircraft_becomes_a_card():
    outcome, out = run_with(PIN, [("ok", [UAL_STATE])])
    assert outcome == "stop", (outcome, out[-800:])
    cards = _cards(out)
    assert cards, out
    c = cards[0]
    assert c["flight"] == "UAL123", c
    assert c["airline"] == "United", c
    assert c["logo"] == "ual", c
    assert c["hex"] == "abc123", c
    assert "hero new abc123" in out, out


def test_empty_sky_gives_null_flight_card():
    outcome, out = run_with(PIN, [("ok", [])])
    assert outcome == "stop", (outcome, out[-800:])
    cards = _cards(out)
    assert cards, out
    assert cards[0]["flight"] is None, cards[0]
    assert "hero none None" in out, out


def test_429_backs_off_and_keeps_last_card():
    # First poll succeeds with a real aircraft, second 429s with a 20 s
    # Retry-After -- the next poll (at t=15 s, 15 s later) must be skipped,
    # so only 2 net calls happen in a 35 s run (polls would otherwise land
    # at ~0, 15, 30).
    outcome, out = run_with(PIN, [("ok", [UAL_STATE]), ("http", 429, 20)], end=35)
    assert outcome == "stop", (outcome, out[-800:])
    assert len(sim.W.net_calls) == 2, sim.W.net_calls
    assert "poll http 429 retry_after 20" in out, out
    # last_card is only printed on a SUCCESSFUL poll; the 429'd poll must not
    # print a second (bad) card -- exactly one real card in the whole run.
    assert len(_cards(out)) == 1, out


def test_other_failure_keeps_last_card_and_does_not_crash():
    outcome, out = run_with(PIN, [("ok", [UAL_STATE]), ("err", OSError("no route"))], end=35)
    assert outcome == "stop", (outcome, out[-800:])
    assert len(sim.W.net_calls) >= 2, sim.W.net_calls
    assert "poll no route" in out, out
    assert len(_cards(out)) == 1, out  # the OSError poll never printed a card


if __name__ == "__main__":
    n = 0
    for name in sorted(k for k in dir() if k.startswith("test_")):
        globals()[name]()
        print("ok", name)
        n += 1
    print("ok", n, "tests")
