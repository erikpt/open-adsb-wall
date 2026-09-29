"""OpenSky /states/all HTTPS client (issue #26; DESIGN.md sec. 8).

The device's only outbound network call besides NTP. Builds the bbox query
for the device's own pin/radius (lib/bbox.py), adds extended=1 (state-vector
category data lib/hero.py / lib/filters.py need to tell airliners from
helicopters/GA/military), and an optional bearer token to raise OpenSky's
anonymous rate limit. Goes through lib/httpclient.py's shared Session /
timeout / budget contract -- never a bare adafruit_requests call -- so a
poll can never starve the local settings HTTP server.

Returns the raw parsed OpenSky JSON dict ({"time": ..., "states": [...]}) for
lib/hero.py:candidates() to turn into candidate dicts. Never returns None or
swallows a failure -- raises whatever lib/httpclient.py's get_json() does
(HTTPStatusError, with e.retry_after seconds on a 429 if OpenSky sent one;
OSError / RuntimeError / TimeoutError / ValueError otherwise). code.py's
poll_card() is what turns a raise into "keep the last good card" per
DESIGN.md sec. 8 -- this module never guesses at that policy itself.

CircuitPython-safe: no f-strings, no typing. No urllib (not vendored on this
board) -- the query string is built by hand; every value is a float we
formatted ourselves, so there is nothing that needs percent-encoding.
"""
import httpclient
from bbox import box

STATES_PATH = "/states/all"


def _url(api_base, bbox):
    base = (api_base or "").rstrip("/")
    return "%s%s?lamin=%.6f&lamax=%.6f&lomin=%.6f&lomax=%.6f&extended=1" % (
        base, STATES_PATH, bbox["lamin"], bbox["lamax"], bbox["lomin"], bbox["lomax"])


def poll(pool, prefs):
    """OpenSky's raw states/all JSON for prefs' lat/lon/nm.

    prefs["api"]: OpenSky API base URL (DEFAULTS: https://opensky-network.org/api).
    prefs["token"]: optional bearer token (DESIGN.md sec. 5/6/8) -- omitted
    entirely when blank, since anonymous access is the documented default.
    """
    b = box(prefs["lat"], prefs["lon"], prefs["nm"])
    url = _url(prefs.get("api"), b)
    token = (prefs.get("token") or "").strip()
    headers = {"Authorization": "Bearer " + token} if token else None
    return httpclient.get_json(pool, url, headers=headers)
