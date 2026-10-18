"""Host-side checks for lib/cycle.py (issue #20): snapshot build/tick/
wraparound, ready_for_build() gating, and empty-list behavior.

Run: python3 tests/test_cycle.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "firmware", "lib"))

from cycle import Cycle  # noqa: E402


def _cand(hex_, dist, alt=1000.0, spd=100.0):
    return {"hex": hex_, "cs": hex_.upper(), "lat": 0, "lon": 0, "dist": dist,
            "alt": alt, "spd": spd, "trk": 0, "cat": None, "age": 0}


FIVE = [_cand("e", 5.0), _cand("a", 1.0), _cand("c", 3.0), _cand("b", 2.0), _cand("d", 4.0)]


def test_no_snapshot_is_ready_for_build_and_ticks_to_none():
    cyc = Cycle()
    assert cyc.ready_for_build()
    assert cyc.tick(0.0) is None


def test_build_sorts_by_rank_closest_first():
    cyc = Cycle()
    cyc.build(FIVE)
    assert [c["hex"] for c in cyc.list] == ["a", "b", "c", "d", "e"]
    assert cyc.tick(0.0)["hex"] == "a"


def test_build_caps_at_max_cards():
    cands = [_cand(str(i), float(i)) for i in range(8)]
    cyc = Cycle(max_cards=5)
    cyc.build(cands)
    assert len(cyc.list) == 5
    assert [c["hex"] for c in cyc.list] == ["0", "1", "2", "3", "4"]


def test_fewer_than_max_cards_cycles_through_what_exists_no_padding():
    cyc = Cycle(dwell_s=10)
    cyc.build([_cand("a", 1.0), _cand("b", 2.0)])  # only 2 candidates
    assert len(cyc.list) == 2
    assert cyc.tick(0.0)["hex"] == "a"
    assert cyc.tick(9.9)["hex"] == "a"   # still within dwell
    assert cyc.tick(10.0)["hex"] == "b"  # advances to 2nd
    assert not cyc.ready_for_build()     # not wrapped yet
    assert cyc.tick(20.0)["hex"] == "a"  # wraps back to 1st
    assert cyc.ready_for_build()         # full rotation complete


def test_not_ready_for_build_mid_rotation():
    cyc = Cycle(dwell_s=12)
    cyc.build(FIVE)
    assert not cyc.ready_for_build()
    for t in (0.0, 12.0, 24.0, 36.0):  # advances through cards 0..3, still mid-rotation
        cyc.tick(t)
        assert not cyc.ready_for_build()


def test_ready_for_build_only_after_full_rotation_wraps():
    cyc = Cycle(dwell_s=12)
    cyc.build(FIVE)
    now = 0.0
    cyc.tick(now)
    for _ in range(len(FIVE) - 1):  # advance through b, c, d, e (no wrap yet)
        now += 12.0
        cyc.tick(now)
        assert not cyc.ready_for_build()
    now += 12.0  # wraps back to card 0
    cyc.tick(now)
    assert cyc.ready_for_build()


def test_build_again_restarts_rotation_at_card_zero():
    cyc = Cycle(dwell_s=12)
    cyc.build(FIVE)
    cyc.tick(0.0)
    cyc.tick(12.0)
    assert cyc.tick(12.0)["hex"] == "b"
    cyc.build(FIVE)  # fresh snapshot mid-rotation
    assert cyc.index == 0
    assert not cyc.ready_for_build()
    assert cyc.tick(12.1)["hex"] == "a"  # since reset too: no immediate advance


def test_build_with_empty_candidates_ticks_to_none():
    cyc = Cycle()
    cyc.build(FIVE)
    cyc.tick(0.0)
    cyc.build([])
    assert cyc.tick(0.0) is None
    assert cyc.ready_for_build()  # empty list: nothing to rotate through, due immediately


if __name__ == "__main__":
    n = 0
    for name in sorted(k for k in dir() if k.startswith("test_")):
        globals()[name]()
        print("ok", name)
        n += 1
    print("ok", n, "tests")
