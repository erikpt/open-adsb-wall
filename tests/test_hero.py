"""Host-side check for lib/hero.py. Run: python3 tests/test_hero.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "firmware", "lib"))

import hero  # noqa: E402
from hero import Hero, candidates, select, stale_limit, distance_mi  # noqa: E402

PIN = (30.0000, -95.0000)


def c(hx, dist, alt=3000.0, spd=150.0, age=0):
    return {"hex": hx, "cs": hx.upper(), "lat": 0.0, "lon": 0.0, "dist": dist,
            "alt": alt, "spd": spd, "trk": 0.0, "cat": None, "age": age}


def state(hx, lat, lon, t_pos=1000, ground=False, alt=3000.0, cs="TST123  "):
    # 17 fields (no category), shaped like OpenSky /states/all
    return [hx, cs, "United States", t_pos, t_pos, lon, lat, alt, ground,
            150.0, 90.0, 0.0, None, alt, "1200", False, 0]


def test_candidates():
    resp = {"time": 1010, "states": [
        state("A1B2C3", PIN[0] + 1.0 / 69.0, PIN[1]),          # 1 mi north
        state("dddddd", PIN[0], PIN[1], ground=True),           # on ground
        state("eeeeee", None, None),                            # no position
        state("ffffff", PIN[0], PIN[1], t_pos=None),            # falls back to last_contact (None)
        ["short"],                                              # malformed
    ]}
    out = candidates(resp, PIN[0], PIN[1])
    hexes = [x["hex"] for x in out]
    assert hexes == ["a1b2c3", "ffffff"], hexes
    a = out[0]
    assert abs(a["dist"] - 1.0) < 0.01, a["dist"]
    assert a["age"] == 10 and a["cs"] == "TST123" and a["cat"] is None
    assert candidates(None, 0, 0) == [] and candidates({"time": 1, "states": None}, 0, 0) == []
    # 1 mi east at this latitude
    d = distance_mi(PIN[0], PIN[1], PIN[0], PIN[1] + 1.0 / (69.0 * 0.8641))
    assert abs(d - 1.0) < 0.01, d


def test_rules():
    assert select(None, []) == (None, "none")
    got, why = select(None, [c("b", 4.0), c("a", 3.0)])
    assert got["hex"] == "a" and why == "new"
    # tie-break: equal distance -> lower altitude
    got, _ = select(None, [c("hi", 3.0, alt=9000), c("lo", 3.0, alt=2000)])
    assert got["hex"] == "lo"
    # (a) 10 % closer: hold
    got, why = select("a", [c("a", 5.0), c("b", 4.5)], held_s=60)
    assert (got["hex"], why) == ("a", "keep")
    # (a) 22 % closer, 1.1 mi: switch, but not inside the dwell window
    got, why = select("a", [c("a", 5.0), c("b", 3.9)], held_s=60)
    assert (got["hex"], why) == ("b", "closer")
    got, why = select("a", [c("a", 5.0), c("b", 3.9)], held_s=10)
    assert (got["hex"], why) == ("a", "dwell")
    # (a) near the pin: 40 % closer but only 0.4 mi -> hold (position noise)
    got, why = select("a", [c("a", 1.0), c("b", 0.6)], held_s=60)
    assert (got["hex"], why) == ("a", "keep")
    # (b) hero missing from response
    got, why = select("a", [c("b", 8.0)], held_s=5)
    assert (got["hex"], why) == ("b", "gone")
    got, why = select("a", [], held_s=5)
    assert (got, why) == (None, "gone")
    # (c) hero present but its position is older than max_stale_s
    got, why = select("a", [c("a", 1.0, age=60), c("b", 8.0)], held_s=5, max_stale_s=45)
    assert (got["hex"], why) == ("b", "stale")
    # stale rows are never picked as a new hero either
    got, why = select(None, [c("a", 1.0, age=60)], max_stale_s=45)
    assert (got, why) == (None, "none")


def test_no_flapping():
    """Two aircraft crossing near-equidistant: at most one switch."""
    h = Hero(poll_s=15)
    t = 0.0
    shown = []
    # a recedes 4.0 -> 6.0 mi, b approaches 6.0 -> 4.0 mi over 20 polls, with jitter
    for i in range(21):
        jit = 0.15 if i % 2 else -0.15
        da = 4.0 + 0.1 * i + jit
        db = 6.0 - 0.1 * i - jit
        got, _ = h.select([c("a", da), c("b", db)], t)
        shown.append(got["hex"])
        t += 15
    switches = sum(1 for i in range(1, len(shown)) if shown[i] != shown[i - 1])
    assert shown[0] == "a" and shown[-1] == "b" and switches == 1, shown


def test_state_object():
    h = Hero(poll_s=15)
    assert h.max_stale_s == 45 and stale_limit(60) == 90 and stale_limit(5) == 30
    got, why = h.select([c("a", 3.0)], 100.0)
    assert h.hex == "a" and h.since == 100.0 and why == "new"
    assert not h.expired(140.0) and h.expired(146.0)   # (c) on device clock
    h.select([c("a", 3.2)], 115.0)
    assert h.since == 100.0 and h.seen == 115.0 and h.card["dist"] == 3.2
    got, why = h.select([], 130.0)
    assert got is None and why == "gone" and h.hex is None and not h.expired(1e9)


if __name__ == "__main__":
    for name in sorted(k for k in dir() if k.startswith("test_")):
        globals()[name]()
        print("ok", name)
    print("hero: all passed")
