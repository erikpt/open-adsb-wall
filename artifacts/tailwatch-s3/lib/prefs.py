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
    "timezone": "America/Chicago",
    "api": "https://api.example.com",
    "token": "",
}

_BOOLS = {
    "hide_heli",
    "hide_ga",
    "hide_mil",
    "sleep_enabled",
}
_FLOATS = {
    "lat",
    "lon",
    "nm",
    "brightness_day",
    "brightness_night",
    "brightness_max",
}


def _clamp(p):
    p["nm"] = max(1.0, min(50.0, float(p["nm"])))
    for k in ("brightness_day", "brightness_night", "brightness_max"):
        p[k] = max(0.0, min(1.0, float(p[k])))
    if p["brightness_day"] > p["brightness_max"]:
        p["brightness_day"] = p["brightness_max"]
    if p["brightness_night"] > p["brightness_max"]:
        p["brightness_night"] = p["brightness_max"]
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


def apply_form(current, form):
    out = dict(current)
    for k in _BOOLS:
        out[k] = form.get(k) in ("1", "true", "on", "yes")
    for k, v in form.items():
        if k in _FLOATS:
            try:
                out[k] = float(v)
            except ValueError:
                pass
        elif k in current and k not in _BOOLS:
            out[k] = v
    return save(out)
