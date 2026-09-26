"""Host-side check for the "is the clock real" gate in lib/schedule.py.

Run: python3 tests/test_schedule_clock.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))

import schedule  # noqa: E402
from schedule import (MIN_TRUSTED_TS, brightness, clock_trusted, night,  # noqa: E402
                      set_clock_synced, sleeping)

EPOCH_2000 = 946684800   # CircuitPython default RTC: 2000-01-01 00:00:00 UTC
REAL_2025 = 1735689600   # 2025-01-01 00:00:00 UTC (= 18:00 CST, after sunset at 30N 95W)

P = {
    "lat": 30.0, "lon": -95.0,
    "brightness_day": 0.7, "brightness_night": 0.18, "brightness_max": 1.0,
    "night_mode": "fixed", "night_start": "17:00", "night_end": "07:00",
    "sleep_enabled": True, "sleep_start": "17:30", "sleep_end": "06:30",
    "tz_offset_min": -360, "us_dst": True,
}


def with_(**kw):
    p = dict(P)
    p.update(kw)
    return p


def test_constant():
    import calendar
    assert MIN_TRUSTED_TS == calendar.timegm((2024, 1, 1, 0, 0, 0)), MIN_TRUSTED_TS


def test_unsynced_default_epoch_never_blanks():
    set_clock_synced(False)
    assert not clock_trusted(EPOCH_2000)
    # 2000-01-01 00:00Z = 18:00 CST: inside both the sleep and the night window
    assert sleeping(P, EPOCH_2000) is False
    assert night(P, EPOCH_2000) is False
    assert night(with_(night_mode="sunset"), EPOCH_2000) is False
    assert brightness(P, EPOCH_2000) == 0.7
    assert brightness(with_(brightness_max=0.5), EPOCH_2000) == 0.5  # cap still applies


def test_synced_applies_schedule():
    set_clock_synced(True)
    try:
        assert clock_trusted(EPOCH_2000)
        assert sleeping(P, EPOCH_2000) is True
        assert brightness(P, EPOCH_2000) == 0.0
        assert brightness(with_(sleep_enabled=False), EPOCH_2000) == 0.18
        assert night(with_(night_mode="sunset"), EPOCH_2000) is True
    finally:
        set_clock_synced(False)


def test_unsynced_but_plausible_clock_is_trusted():
    # e.g. RTC survived microcontroller.reset() but NTP failed this boot
    set_clock_synced(False)
    assert clock_trusted(REAL_2025)
    assert sleeping(P, REAL_2025) is True
    assert brightness(P, REAL_2025) == 0.0
    assert brightness(with_(sleep_enabled=False), REAL_2025) == 0.18
    assert night(with_(night_mode="sunset", sleep_enabled=False), REAL_2025) is True
    assert not clock_trusted(MIN_TRUSTED_TS - 1) and clock_trusted(MIN_TRUSTED_TS)


def test_default_args_still_work():
    set_clock_synced(False)
    # old call signatures (prefs only) keep working and use time.time()
    assert brightness(P) in (0.0, 0.18, 0.7)
    sleeping(P)
    night(P)
    assert schedule.clock_synced() is False


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all schedule clock-gate tests passed")
