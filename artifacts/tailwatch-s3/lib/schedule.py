import time
from sun import is_after_sunset


def _hm(s):
    try:
        h, m = s.split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return 0


def _now_minutes():
    t = time.localtime()
    return t.tm_hour * 60 + t.tm_min


def _in_window(now_m, start_s, end_s):
    a = _hm(start_s)
    b = _hm(end_s)
    if a == b:
        return False
    if a < b:
        return a <= now_m < b
    return now_m >= a or now_m < b


def sleeping(prefs):
    if not prefs.get("sleep_enabled"):
        return False
    return _in_window(_now_minutes(), prefs["sleep_start"], prefs["sleep_end"])


def night(prefs):
    mode = prefs.get("night_mode", "sunset")
    if mode == "off":
        return False
    if mode == "fixed":
        return _in_window(_now_minutes(), prefs["night_start"], prefs["night_end"])
    return is_after_sunset(prefs["lat"], prefs["lon"])


def brightness(prefs):
    cap = float(prefs.get("brightness_max", 1.0))
    if sleeping(prefs):
        return 0.0
    if night(prefs):
        return min(float(prefs["brightness_night"]), cap)
    return min(float(prefs["brightness_day"]), cap)
