import json
import os

PATH = "/prefs.json"
BACKUP = "/prefs.bak"
DEFAULTS = {
    "lat": 30.2094,
    "lon": -95.7508,
    "nm": 10,
    "hide_heli": True,
    "hide_ga": False,
    "hide_mil": True,
    "brightness_day": 0.7,
    "brightness_night": 0.18,
    "brightness_max": 1.0,
    "night_mode": "sunset",
    "night_start": "21:00",
    "night_end": "06:30",
    "sleep_enabled": True,
    "sleep_start": "23:00",
    "sleep_end": "06:30",
    "tz_offset_min": -360,  # standard-time UTC offset, minutes (east +); -360 = US Central
    "us_dst": True,         # auto-apply fixed US DST rule (lib/tz.py); not a tz database
    "api": "https://api.example.com",
    "token": "",
}

_BOOLS = {
    "hide_heli",
    "hide_ga",
    "hide_mil",
    "sleep_enabled",
    "us_dst",
}
_FLOATS = {
    "lat",
    "lon",
    "nm",
    "brightness_day",
    "brightness_night",
    "brightness_max",
    "tz_offset_min",
}


def _clamp(p):
    p["nm"] = max(1.0, min(50.0, float(p["nm"])))
    for k in ("brightness_day", "brightness_night", "brightness_max"):
        p[k] = max(0.0, min(1.0, float(p[k])))
    if p["brightness_day"] > p["brightness_max"]:
        p["brightness_day"] = p["brightness_max"]
    if p["brightness_night"] > p["brightness_max"]:
        p["brightness_night"] = p["brightness_max"]
    try:
        off = int(round(float(p["tz_offset_min"])))
    except (ValueError, TypeError):
        off = DEFAULTS["tz_offset_min"]
    p["tz_offset_min"] = max(-720, min(840, off))  # UTC-12:00 .. UTC+14:00
    p.pop("timezone", None)  # legacy IANA string: unresolvable on-device, drop it
    if p["night_mode"] not in ("off", "fixed", "sunset"):
        p["night_mode"] = "sunset"
    return p


def load():
    data = dict(DEFAULTS)
    try:
        with open(PATH, "r") as f:
            data.update(json.load(f))
    except (OSError, ValueError):
        try:
            with open(BACKUP, "r") as f:
                data.update(json.load(f))
        except (OSError, ValueError):
            pass
    return _clamp(data)


def save(data):
    data = _clamp(dict(DEFAULTS, **data))
    raw = json.dumps(data)
    try:
        os.rename(PATH, BACKUP)
    except OSError:
        pass
    with open(PATH, "w") as f:
        f.write(raw)
    return data


_TRUTHY = ("1", "true", "on", "yes")


def _to_bool(v):
    """Coerce a submitted value to bool, or None if unrecognised.

    bool is checked first: isinstance(True, int) is True.
    """
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        return v.strip().lower() in _TRUTHY
    return None


def apply_form(current, form, partial=False):
    """Merge a POSTed dict into current prefs and save.

    partial=False (HTML form: urlencoded/multipart/query, all-string values):
        every boolean is rewritten; a missing key means False, because an
        unchecked checkbox is simply absent (DESIGN.md section 6).
    partial=True (JSON body, native types): only keys present in `form`
        change; omitted or unrecognised values keep their stored value.
    """
    out = dict(current)
    for k in _BOOLS:
        b = _to_bool(form[k]) if k in form else None
        if b is not None:
            out[k] = b
        elif not partial:
            out[k] = False
    for k, v in form.items():
        if k in _BOOLS:
            continue
        if k in _FLOATS:
            try:
                out[k] = float(v)
            except (ValueError, TypeError):
                pass
        elif k in current and isinstance(v, str):
            out[k] = v
    return save(out)
