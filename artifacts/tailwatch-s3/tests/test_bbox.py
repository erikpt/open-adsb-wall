"""Host-side check that lib/bbox.py matches the DESIGN.md sec. 6 formula.

Run: python3 tests/test_bbox.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))

from bbox import box  # noqa: E402


def close(a, b):
    return abs(a - b) < 1e-9


def formula(lat, lon, nm):
    dlat = nm / 69.0
    dlon = nm / (69.0 * math.cos(math.radians(lat)))
    return {"lamin": lat - dlat, "lamax": lat + dlat, "lomin": lon - dlon, "lomax": lon + dlon}


def test_ten_mile_box_matches_formula():
    b = box(30.0, -95.0, 10)
    want = formula(30.0, -95.0, 10)
    for k in want:
        assert close(b[k], want[k]), (k, b[k], want[k])
    # sanity against hand-computed values (DESIGN.md sec. 6 at 30N 95W)
    assert close(round(b["lamin"], 4), 29.8551) and close(round(b["lomax"], 4), -94.8327), b


def test_friend_pin_and_default_nm():
    assert box(47.6062, -122.3321) == box(47.6062, -122.3321, 10)
    b = box(47.6062, -122.3321, 5)
    want = formula(47.6062, -122.3321, 5)
    for k in want:
        assert close(b[k], want[k]), (k, b[k], want[k])


def test_high_latitude_cos_floor():
    # existing behaviour: cos(lat) is floored at 0.2 (|lat| > ~78.5 deg) so
    # the box can't blow up toward the pole
    b = box(89.0, 0.0, 10)
    assert close(b["lomax"], 10 / (69.0 * 0.2)), b


if __name__ == "__main__":
    for name in sorted(k for k in dir() if k.startswith("test_")):
        globals()[name]()
        print("ok", name)
    print("bbox: all passed")
