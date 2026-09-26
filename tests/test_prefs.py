"""Host-side check for lib/prefs.py: save/load round trip (the "reboot"),
.bak fallback, clamps, and form-vs-JSON boolean merge rules (DESIGN.md sec. 6).

Run: python3 tests/test_prefs.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "firmware", "lib"))

import prefs  # noqa: E402
from prefs import DEFAULTS, apply_form, load, save  # noqa: E402


def _tmp():
    d = tempfile.mkdtemp()
    prefs.PATH = os.path.join(d, "prefs.json")
    prefs.BACKUP = os.path.join(d, "prefs.bak")
    return d


def test_missing_file_gives_defaults():
    _tmp()
    p = load()
    assert p == dict(DEFAULTS, nm=10.0), p


def test_pin_persists_across_reload():
    # "Save lat/lon from phone; reboot; values persist": an HTML form POST,
    # then a fresh load() (what code.py does at boot).
    _tmp()
    apply_form(load(), {"lat": "47.6062", "lon": "-122.3321", "nm": "5"})
    p = load()
    assert (p["lat"], p["lon"], p["nm"]) == (47.6062, -122.3321, 5.0), p
    # A second unit with a different pin uses the same code path (no fork).
    _tmp()
    apply_form(load(), {"lat": 30.25, "lon": -95.5}, partial=True)
    p = load()
    assert (p["lat"], p["lon"]) == (30.25, -95.5), p


def test_backup_written_and_used_when_main_corrupt():
    _tmp()
    save({"lat": 40.0})
    save({"lat": 41.0})          # first file becomes prefs.bak
    with open(prefs.BACKUP) as f:
        assert json.load(f)["lat"] == 40.0
    with open(prefs.PATH, "w") as f:
        f.write("{not json")     # torn write / corruption
    assert load()["lat"] == 40.0


def test_clamps():
    _tmp()
    p = save({"nm": 500, "brightness_day": 0.9, "brightness_night": 2.0,
              "brightness_max": 0.5, "tz_offset_min": 5000, "night_mode": "bogus",
              "timezone": "America/Chicago"})
    assert p["nm"] == 50.0
    assert p["brightness_max"] == 0.5
    assert p["brightness_day"] == 0.5 and p["brightness_night"] == 0.5
    assert p["tz_offset_min"] == 840
    assert p["night_mode"] == "sunset"
    assert "timezone" not in p
    assert save({"nm": 0})["nm"] == 1.0
    assert save({"tz_offset_min": -5000})["tz_offset_min"] == -720


def test_form_missing_checkbox_means_false():
    _tmp()
    cur = save({"hide_heli": True, "hide_mil": True, "sleep_enabled": True, "us_dst": True})
    p = apply_form(cur, {"hide_heli": "on", "lat": "30.1"})
    assert p["hide_heli"] is True
    assert p["hide_mil"] is False and p["sleep_enabled"] is False and p["us_dst"] is False
    assert p["hide_ga"] is False


def test_json_is_partial_merge():
    _tmp()
    cur = save({"hide_heli": True, "hide_mil": True, "hide_ga": False})
    p = apply_form(cur, {"hide_ga": True, "lat": 31.0}, partial=True)
    assert p["hide_heli"] is True and p["hide_mil"] is True and p["hide_ga"] is True
    assert p["lat"] == 31.0
    p = apply_form(p, {"hide_heli": False}, partial=True)
    assert p["hide_heli"] is False and p["hide_mil"] is True
    # unparseable numbers keep the stored value; unknown keys are ignored
    p = apply_form(p, {"lat": "north", "bogus": "x"}, partial=True)
    assert p["lat"] == 31.0 and "bogus" not in p
    assert load() == p


if __name__ == "__main__":
    for name in sorted(k for k in dir() if k.startswith("test_")):
        globals()[name]()
        print("ok", name)
    print("prefs: all passed")
