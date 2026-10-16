"""Host simulation of code.py's cycle-mode wiring (issue #20): with
prefs["display_mode"] == "cycle", firmware/code.py must rotate through up to
5 candidates at 12 s each (lib/cycle.py:Cycle), and must skip the OpenSky
poll entirely while a rotation is still in progress rather than fetching and
discarding it. Reuses tests/test_code_poll.py's run_with()/PIN harness, which
itself builds on tests/test_code_linkwatch.py's faked-CircuitPython sim.

Run: python3 tests/test_code_cycle.py   (from the repo root)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_code_linkwatch as sim  # noqa: E402
import test_code_poll as tcp  # noqa: E402


def _state(hex_, cs, lat, lon):
    """One /states/all row -- same shape as test_code_poll.py:UAL_STATE,
    varying position (and so lib/hero.py:rank()'s distance) to get a
    deterministic closest-first order."""
    return [hex_, cs, "United States", 1735689500, 1735689500, lon, lat,
            3000.0, False, 200.0, 90.0, 0.0, None, 3100.0, None, False, 0, 4]


# Closest to furthest from PIN (47.6062, -122.3321), by construction.
THREE_STATES = [
    _state("aaa001", "AAA1    ", 47.61, -122.34),
    _state("bbb002", "BBB2    ", 47.65, -122.40),
    _state("ccc003", "CCC3    ", 47.70, -122.45),
]

CYCLE_PIN = dict(tcp.PIN, display_mode="cycle", nm=50)  # wide enough to keep all 3 candidates


def _displays(out):
    """Every "display ..." line code.py printed, in order."""
    return [line[len("display "):] for line in out.splitlines() if line.startswith("display ")]


def test_rotates_through_candidates_closest_first():
    outcome, out = tcp.run_with(CYCLE_PIN, [("ok", THREE_STATES)], end=45)
    assert outcome == "stop", (outcome, out[-800:])
    shown = [d for d in _displays(out) if d != "NO TRAFFIC"]
    assert shown, out
    # first real card is the closest; order never regresses to a farther
    # card without passing through the nearer ones first (no shuffling).
    first_of_each = []
    for name in shown:
        if not first_of_each or first_of_each[-1] != name:
            first_of_each.append(name)
    assert first_of_each[:3] == ["AAA1", "BBB2", "CCC3"], first_of_each


def test_wraps_back_to_first_after_full_rotation():
    outcome, out = tcp.run_with(CYCLE_PIN, [("ok", THREE_STATES)], end=60)
    assert outcome == "stop", (outcome, out[-800:])
    shown = [d for d in _displays(out) if d != "NO TRAFFIC"]
    # 3 cards * 12 s each: AAA1 -> BBB2 -> CCC3 -> AAA1 (wrapped)
    assert "CCC3" in shown and shown.index("CCC3") < len(shown) - 1
    assert shown[-1] == "AAA1", shown


def test_poll_is_skipped_mid_rotation_not_just_discarded():
    # 3 candidates * 12 s/card = 36 s per full rotation; a naive "poll every
    # 15 s regardless" would make 4 OpenSky calls in 60 s. Issue #20's
    # ready_for_build() gate gives only 2 (one to start the first rotation,
    # one once it fully wraps) -- so the poll itself is skipped while
    # mid-rotation, not fetched and thrown away.
    outcome, out = tcp.run_with(CYCLE_PIN, [("ok", THREE_STATES)], end=60)
    assert outcome == "stop", (outcome, out[-800:])
    assert len(sim.W.net_calls) == 2, sim.W.net_calls


def test_no_candidates_shows_no_traffic_not_a_crash():
    outcome, out = tcp.run_with(CYCLE_PIN, [("ok", [])], end=20)
    assert outcome == "stop", (outcome, out[-800:])
    assert "display NO TRAFFIC" in out, out
    assert "display NO LINK" not in out, out


if __name__ == "__main__":
    n = 0
    for name in sorted(k for k in dir() if k.startswith("test_")):
        globals()[name]()
        print("ok", name)
        n += 1
    print("ok", n, "tests")
