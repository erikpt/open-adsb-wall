import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import prefs

d = tempfile.mkdtemp()
prefs.PATH = os.path.join(d, "prefs.json")
prefs.BACKUP = os.path.join(d, "prefs.bak")

# public() redaction
base = dict(prefs.DEFAULTS)
pub = prefs.public(dict(base, token="abc"))
assert "token" not in pub
assert pub["token_set"] is True

pub_empty = prefs.public(dict(base, token=""))
assert pub_empty["token_set"] is False
pub_ws = prefs.public(dict(base, token="   "))
assert pub_ws["token_set"] is False

# apply_form token rules, starting from a stored token of "abc"
cur = dict(base, token="abc")

p = prefs.apply_form(cur, {"token": ""})  # form path (partial=False): blank keeps stored token
assert p["token"] == "abc"

p = prefs.apply_form(cur, {"token": "  new "})
assert p["token"] == "new"

p = prefs.apply_form(cur, {"token_clear": "1"})
assert p["token"] == ""

p = prefs.apply_form(cur, {"lat": 1}, partial=True)  # JSON partial update: omitted token unchanged
assert p["token"] == "abc"

p = prefs.apply_form(cur, {"token_set": False})  # round-tripped read-only key: no effect
assert p["token"] == "abc"

print("prefs token: all passed")
