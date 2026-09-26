"""Host-side check for lib/dim.py: colour-scaled dimming and the sleep blank.

Run: python3 tests/test_dim.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))

from dim import Dimmer, min_visible, scale_color  # noqa: E402


class Display:
    def __init__(self, group):
        self.root_group = group
        self.brightness = 1.0


BASE = (0x000000, 0xFFFFFF, 0x999999, 0xFF7900)


def make():
    awake, blank = object(), object()
    d = Display(awake)
    pal = [0] * len(BASE)
    dm = Dimmer(d, awake, blank, floor=min_visible(4))
    dm.add_palette(pal, BASE)
    return d, pal, dm, awake, blank


def test_scale_color():
    assert min_visible(4) == 16 and min_visible(3) == 32
    assert scale_color(0xFFFFFF, 1.0) == 0xFFFFFF
    assert scale_color(0xFFFFFF, 0.5) == 0x808080
    assert scale_color(0xFFFFFF, 0.0) == 0x000000
    assert scale_color((255, 0, 10), 0.01, floor=16) == (16, 0, 10)  # floor, never above original
    assert scale_color(0xFFFFFF, 2.0) == 0xFFFFFF


def test_sleep_blanks_and_wake_restores():
    d, pal, dm, awake, blank = make()
    assert dm.apply(0.7) is True
    assert d.root_group is awake and d.brightness == 1.0
    assert pal[1] == scale_color(0xFFFFFF, 0.7, 16)
    assert dm.apply(0.0) is True            # sleep window: panel dark
    assert d.root_group is blank and d.brightness == 0.0
    assert dm.apply(0.18) is True           # wake at night level
    assert d.root_group is awake and d.brightness == 1.0
    assert pal[1] == scale_color(0xFFFFFF, 0.18, 16)


def test_rescales_from_base_not_compounding():
    d, pal, dm, _, _ = make()
    for f in (0.5, 0.5, 0.25, 0.5):
        dm.apply(f, force=True)
    assert pal == [scale_color(c, 0.5, 16) for c in BASE]


def test_no_op_when_level_unchanged():
    d, pal, dm, _, _ = make()
    assert dm.apply(0.4) is True
    assert dm.apply(0.4) is False
    assert dm.apply(-1) is True and dm.level == 0.0 and d.brightness == 0.0


if __name__ == "__main__":
    for name in sorted(k for k in dir() if k.startswith("test_")):
        globals()[name]()
        print("ok", name)
    print("dim: all passed")
