import time

from tz import local_minutes
from sun import is_after_sunset

# 2024-01-01T00:00:00Z. After power-up CircuitPython's RTC starts at its
# built-in epoch (commonly 2000-01-01 00:00:00). Until NTP succeeds, a clock
# earlier than this is treated as "not set", never as a real time of day.
MIN_TRUSTED_TS = 1704067200

_synced = False  # set by code.py after a successful NTP -> RTC write


def set_clock_synced(ok=True):
    global _synced
    _synced = bool(ok)


def clock_synced():
    return _synced


def clock_trusted(ts=None):
    """True if the RTC holds a real time: NTP-synced this boot, or plausibly
    set (>= 2024) -- e.g. the ESP32-S3 RTC kept time across microcontroller.reset()."""
    if _synced:
        return True
    if ts is None:
        ts = time.time()
    return ts >= MIN_TRUSTED_TS


def _hm(s):
    try:
        h, m = s.split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return 0


def _now_minutes(prefs, ts=None):
    # Local wall-clock minutes for sleep/fixed-night windows. The offset is
    # applied ONLY here: the RTC stays UTC and sun.py needs UTC. Fixed US DST
    # rule only, not a tz database -- see lib/tz.py.
    return local_minutes(prefs.get("tz_offset_min", 0), prefs.get("us_dst", False), ts)


def _in_window(now_m, start_s, end_s):
    a = _hm(start_s)
    b = _hm(end_s)
    if a == b:
        return False
    if a < b:
        return a <= now_m < b
    return now_m >= a or now_m < b


def sleeping(prefs, ts=None):
    if not prefs.get("sleep_enabled"):
        return False
    if ts is None:
        ts = time.time()
    if not clock_trusted(ts):
        return False  # unset clock: never blank the panel on a bogus time
    return _in_window(_now_minutes(prefs, ts), prefs["sleep_start"], prefs["sleep_end"])


def night(prefs, ts=None):
    mode = prefs.get("night_mode", "sunset")
    if mode == "off":
        return False
    if ts is None:
        ts = time.time()
    if not clock_trusted(ts):
        return False  # unset clock: day brightness
    if mode == "fixed":
        return _in_window(_now_minutes(prefs, ts), prefs["night_start"], prefs["night_end"])
    return is_after_sunset(prefs["lat"], prefs["lon"], ts)


def brightness(prefs, ts=None):
    if ts is None:
        ts = time.time()
    cap = float(prefs.get("brightness_max", 1.0))
    if sleeping(prefs, ts):
        return 0.0
    if night(prefs, ts):
        return min(float(prefs["brightness_night"]), cap)
    return min(float(prefs["brightness_day"]), cap)
