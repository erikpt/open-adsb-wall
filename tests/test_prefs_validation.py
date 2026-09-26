import os, sys, json, math, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "firmware", "lib"))
import prefs

D = prefs.DEFAULTS


def c(**kw):
    p = dict(D)
    p.update(kw)
    return prefs._clamp(p)


# valid values pass through (normalised)
p = c(lat=45.5, lon=-122.6, night_start="7:05", night_end=" 06:30 ", sleep_start="00:00", sleep_end="23:59")
assert (p["lat"], p["lon"]) == (45.5, -122.6)
assert (p["night_start"], p["night_end"], p["sleep_start"], p["sleep_end"]) == ("07:05", "06:30", "00:00", "23:59")
assert c(lat="45.5")["lat"] == 45.5 and c(lat=-90)["lat"] == -90.0 and c(lon=180)["lon"] == 180.0

# bad lat/lon -> default
for bad in (91, -90.01, "abc", None, True, float("nan"), float("inf"), [1], {}):
    assert c(lat=bad)["lat"] == D["lat"], bad
for bad in (180.5, -181, "x", None, False, float("nan"), float("-inf")):
    assert c(lon=bad)["lon"] == D["lon"], bad

# bad times -> default
for k in prefs._TIMES:
    for bad in ("24:00", "12:60", "-1:00", "12", "12:5", "123:00", "12:00:00", "ab:cd", "", None, 1200, [], "+1:00", " 1:0 ", "²:00"):
        assert c(**{k: bad})[k] == D[k], (k, bad)

# previously-crashing numeric fields now fall back
assert c(nm="abc")["nm"] == float(D["nm"]) and c(nm=None)["nm"] == float(D["nm"])
assert c(brightness_day="x")["brightness_day"] == D["brightness_day"]
assert c(tz_offset_min=float("inf"))["tz_offset_min"] == D["tz_offset_min"]

# existing behaviour preserved
assert c(nm=500)["nm"] == 50.0 and c(tz_offset_min="330.4")["tz_offset_min"] == 330
assert c(night_mode="bogus")["night_mode"] == "sunset" and "timezone" not in c(timezone="America/Chicago")

# end-to-end: malformed stored file loads without raising and save() rewrites clean values
d = tempfile.mkdtemp()
prefs.PATH = os.path.join(d, "prefs.json")
prefs.BACKUP = os.path.join(d, "prefs.bak")
with open(prefs.PATH, "w") as f:
    json.dump({"lat": "north", "lon": 999, "nm": "far", "night_start": "25:99", "sleep_end": None}, f)
p = prefs.load()
assert p["lat"] == D["lat"] and p["lon"] == D["lon"] and p["night_start"] == D["night_start"] and p["sleep_end"] == D["sleep_end"]
prefs.save(p)
with open(prefs.PATH) as f:
    s = json.load(f)
assert s["lat"] == D["lat"] and s["night_start"] == "21:00" and s["sleep_end"] == "06:30"

# apply_form path
p = prefs.apply_form(prefs.load(), {"lat": "95", "lon": "-97.1", "night_start": "9:30", "sleep_start": "lol"}, partial=True)
assert p["lat"] == D["lat"] and p["lon"] == -97.1 and p["night_start"] == "09:30" and p["sleep_start"] == D["sleep_start"]

print("prefs validation: OK")
