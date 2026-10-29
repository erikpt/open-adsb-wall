"""Host-side checks for lib/badapple.py (issue #30): RLE frame decoding and
the Player state machine (start/tick/stop, frame pacing, clip-end restore).
Not the actual pixel rendering (displayio is faked) -- same split as
tests/test_card.py and tests/test_cycle.py.

Run: python3 tests/test_badapple.py
"""
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "..", "firmware", "lib")
sys.path.insert(0, LIB)


class Bitmap:
    def __init__(self, w, h, n):
        self.w, self.h = w, h
        self.d = {}

    def __setitem__(self, k, v):
        self.d[k] = v

    def __getitem__(self, k):
        return self.d.get(k, 0)


class Palette(list):
    def __init__(self, n):
        super().__init__([0] * n)


class Group(list):
    pass


sys.modules["displayio"] = types.ModuleType("displayio")
sys.modules["displayio"].Bitmap = Bitmap
sys.modules["displayio"].Palette = Palette
sys.modules["displayio"].Group = Group
sys.modules["displayio"].TileGrid = lambda bitmap, pixel_shader: types.SimpleNamespace(
    bitmap=bitmap, pixel_shader=pixel_shader)

# A tiny synthetic clip: 4x2 frames (not the real embedded WIDTH/HEIGHT), so
# tests stay fast and readable rather than decoding the real ~128x64 clip.
badapple_frames = types.ModuleType("badapple_frames")
badapple_frames.WIDTH = 4
badapple_frames.HEIGHT = 2
badapple_frames.FPS = 10
# frame A: row0 "0011", row1 "1100" -> runs 2,2 / 0,2,2 (row1 starts "on": a
# leading 0-length "off" run)
FRAME_A = bytes([2, 2, 0, 2, 2])
# frame B: all off
FRAME_B = bytes([4, 4])
badapple_frames.FRAMES = (FRAME_A, FRAME_B)
sys.modules["badapple_frames"] = badapple_frames

import badapple  # noqa: E402


def test_decode_frame_matches_expected_grid():
    bmp = badapple.decode_frame(FRAME_A, width=4, height=2)
    row0 = [bmp[x, 0] for x in range(4)]
    row1 = [bmp[x, 1] for x in range(4)]
    assert row0 == [0, 0, 1, 1], row0
    assert row1 == [1, 1, 0, 0], row1


def test_decode_frame_all_off():
    bmp = badapple.decode_frame(FRAME_B, width=4, height=2)
    assert all(bmp[x, y] == 0 for x in range(4) for y in range(2))


def test_decode_frame_reuses_given_bitmap():
    bmp = Bitmap(4, 2, 2)
    out = badapple.decode_frame(FRAME_A, width=4, height=2, bitmap=bmp)
    assert out is bmp


class Display:
    def __init__(self):
        self.root_group = Group()
        self.brightness = 1.0
        self.auto_refresh = True


def test_start_swaps_display_and_tick_decodes_first_frame_immediately():
    d = Display()
    prev_group = d.root_group
    p = badapple.Player(fps=10, frames=(FRAME_A, FRAME_B))
    p.start(d)
    assert p.active
    assert d.root_group is not prev_group
    assert d.brightness == p.brightness
    still_active = p.tick(0.0)  # first tick: decodes frame 0 immediately
    assert still_active and p.active
    assert p._bitmap[2, 0] == 1  # frame A's row0 col2 is "on"


def test_tick_paces_by_frame_dt_not_every_call():
    d = Display()
    p = badapple.Player(fps=10, frames=(FRAME_A, FRAME_B))  # frame_dt = 0.1
    p.start(d)
    p.tick(0.0)              # frame 0 decoded
    assert p._i == 1
    p.tick(0.05)             # too soon: no advance
    assert p._i == 1
    p.tick(0.1)              # frame_dt elapsed: frame 1 decoded
    assert p._i == 2


def test_clip_end_restores_display_and_deactivates():
    d = Display()
    prev_group = d.root_group
    prev_brightness = 0.77
    d.brightness = prev_brightness
    p = badapple.Player(fps=10, frames=(FRAME_A, FRAME_B))
    p.start(d)
    p.tick(0.0)   # frame 0
    p.tick(0.1)   # frame 1 (last frame): clip ends here
    assert not p.active
    assert d.root_group is prev_group
    assert d.brightness == prev_brightness


def test_stop_restores_display_early():
    d = Display()
    prev_group = d.root_group
    p = badapple.Player(fps=10, frames=(FRAME_A, FRAME_B))
    p.start(d)
    p.tick(0.0)
    p.stop()
    assert not p.active
    assert d.root_group is prev_group


def test_stop_when_not_active_is_a_no_op():
    p = badapple.Player(fps=10, frames=(FRAME_A, FRAME_B))
    p.stop()  # never started: must not raise
    assert not p.active


def test_tick_when_not_active_returns_false_without_side_effects():
    p = badapple.Player(fps=10, frames=(FRAME_A, FRAME_B))
    assert p.tick(123.0) is False


def test_restart_after_stop_replays_from_frame_zero():
    d = Display()
    p = badapple.Player(fps=10, frames=(FRAME_A, FRAME_B))
    p.start(d)
    p.tick(0.0)
    p.tick(0.1)  # clip ends, auto-stops
    assert not p.active
    p.start(d)   # repeat trigger
    assert p.active and p._i == 0
    p.tick(50.0)
    assert p._i == 1


if __name__ == "__main__":
    n = 0
    for name in sorted(k for k in dir() if k.startswith("test_")):
        globals()[name]()
        print("ok", name)
        n += 1
    print("ok", n, "tests")
