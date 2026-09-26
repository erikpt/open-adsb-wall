"""Host-side check for the sleep/night schedule with a trusted clock:
lib/schedule.py windows, lib/tz.py US DST rule, lib/sun.py sunset.
(The untrusted-clock gate is tests/test_schedule_clock.py.)

Run: python3 tests/test_schedule.py
"""
import calendar
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))

from schedule import brightness, night, set_clock_synced, sleeping  # noqa: E402
from sun import is_after_sunset, sunrise_sunset  # noqa: E402
from tz import local_minutes, utc_offset_min  # noqa: E402


def utc(*t):
    return calendar.timegm(t + (0,) * (6 - len(t)))


P = {
    "lat": 30.0, "lon": -95.0,
    "brightness_day": 0.7, "brightness_night": 0.18, "brightness_max": 1.0,
    "night_mode": "fixed", "night_start": "21:00", "night_end": "06:30",
    "sleep_enabled": True, "sleep_start": "23:00", "sleep_end": "06:30",
    "tz_offset_min": -360, "us_dst": True,
}


def with_(**kw):
    p = dict(P)
    p.update(kw)
    return p


def test_us_dst_boundaries_central():
    # 2025: DST starts Sun 9 Mar 02:00 CST (08:00Z), ends Sun 2 Nov 02:00 CDT (07:00Z)
    assert utc_offset_min(-360, True, utc(2025, 3, 9, 7, 59)) == -360
    assert utc_offset_min(-360, True, utc(2025, 3, 9, 8, 0)) == -300
    assert utc_offset_min(-360, True, utc(2025, 11, 2, 6, 59)) == -300
    assert utc_offset_min(-360, True, utc(2025, 11, 2, 7, 0)) == -360
    assert utc_offset_min(-360, False, utc(2025, 7, 1)) == -360     # us_dst off
    assert local_minutes(-360, True, utc(2025, 7, 1, 17, 0)) == 12 * 60  # noon CDT


def test_sleep_window_wraps_midnight():
    set_clock_synced(True)
    try:
        # Jan (CST, UTC-6): 23:30 local = 05:30Z next day; 07:00 local = 13:00Z
        assert sleeping(P, utc(2025, 1, 2, 5, 30)) is True
        assert brightness(P, utc(2025, 1, 2, 5, 30)) == 0.0
        assert sleeping(P, utc(2025, 1, 2, 12, 29)) is True    # 06:29 local
        assert sleeping(P, utc(2025, 1, 2, 12, 30)) is False   # 06:30 local: end is exclusive
        assert sleeping(with_(sleep_enabled=False), utc(2025, 1, 2, 5, 30)) is False
        assert sleeping(with_(sleep_start="06:30"), utc(2025, 1, 2, 5, 30)) is False  # start == end: off
        # Jul (CDT, UTC-5): 23:30 local = 04:30Z
        assert sleeping(P, utc(2025, 7, 2, 4, 30)) is True
        assert sleeping(P, utc(2025, 7, 2, 3, 30)) is False    # 22:30 CDT
    finally:
        set_clock_synced(False)


def test_fixed_night_brightness_is_night_slider_capped():
    set_clock_synced(True)
    try:
        t = utc(2025, 1, 2, 3, 30)  # 21:30 CST: night, not sleep
        p = with_(night_mode="fixed")
        assert night(p, t) is True and sleeping(p, t) is False
        assert brightness(p, t) == 0.18
        assert brightness(with_(brightness_night=0.9, brightness_max=0.5), t) == 0.5
        assert brightness(with_(night_mode="off"), t) == 0.7
        assert brightness(p, utc(2025, 1, 1, 18, 0)) == 0.7   # 12:00 CST: day
        assert brightness(with_(brightness_max=0.4), utc(2025, 1, 1, 18, 0)) == 0.4
    finally:
        set_clock_synced(False)


def test_sunset_mode():
    # 30N 95W on 2025-01-01: sunset ~17:35 CST (23:35Z), sunrise ~07:15 CST (13:15Z)
    rise, sett = sunrise_sunset(30.0, -95.0, utc(2025, 1, 1, 18))
    assert abs(sett - utc(2025, 1, 1, 23, 35)) <= 15 * 60, sett
    assert abs(rise - utc(2025, 1, 1, 13, 15)) <= 15 * 60, rise
    assert not is_after_sunset(30.0, -95.0, utc(2025, 1, 1, 22, 0))   # 16:00 CST
    assert is_after_sunset(30.0, -95.0, utc(2025, 1, 2, 0, 30))       # 18:30 CST
    assert is_after_sunset(30.0, -95.0, utc(2025, 1, 1, 10, 0))       # 04:00 CST
    set_clock_synced(True)
    try:
        p = with_(night_mode="sunset", sleep_enabled=False)
        assert brightness(p, utc(2025, 1, 2, 0, 30)) == 0.18
        assert brightness(p, utc(2025, 1, 1, 18, 0)) == 0.7
    finally:
        set_clock_synced(False)


if __name__ == "__main__":
    for name in sorted(k for k in dir() if k.startswith("test_")):
        globals()[name]()
        print("ok", name)
    print("schedule: all passed")
