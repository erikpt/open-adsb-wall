"""Host-side checks for lib/net.py: URL/bbox/extended=1 construction, the
optional bearer token, and that every failure httpclient.get_json can raise
propagates unchanged rather than getting swallowed here (issue #26 -- that
policy belongs to code.py's poll_card()/main loop, not this module).

Run: python3 tests/test_net.py
"""
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "firmware", "lib"))

import httpclient  # noqa: E402
import net  # noqa: E402
from bbox import box  # noqa: E402

POOL = object()
PREFS = {"lat": 47.6062, "lon": -122.3321, "nm": 5,
         "api": "https://opensky-network.org/api", "token": ""}


class FakeGetJSON:
    """Stand-in for httpclient.get_json: records every call, then either
    returns a canned response or raises a canned exception."""

    def __init__(self, response=None, raises=None):
        self.calls = []
        self.response = response if response is not None else {"time": 100, "states": []}
        self.raises = raises

    def __call__(self, pool, url, headers=None, **kw):
        self.calls.append({"pool": pool, "url": url, "headers": headers})
        if self.raises is not None:
            raise self.raises
        return self.response


def _patched(fake):
    real = httpclient.get_json
    httpclient.get_json = fake
    return real


def _restore(real):
    httpclient.get_json = real


def _query(url):
    return dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))


def test_url_has_correct_path_bbox_and_extended():
    fake = FakeGetJSON()
    real = _patched(fake)
    try:
        net.poll(POOL, PREFS)
    finally:
        _restore(real)
    assert len(fake.calls) == 1
    url = fake.calls[0]["url"]
    split = urllib.parse.urlsplit(url)
    assert split.scheme == "https" and split.netloc == "opensky-network.org"
    assert split.path == "/api/states/all", split.path
    q = _query(url)
    assert q["extended"] == "1", q
    want = box(PREFS["lat"], PREFS["lon"], PREFS["nm"])
    for k in ("lamin", "lamax", "lomin", "lomax"):
        assert abs(float(q[k]) - want[k]) < 1e-6, (k, q[k], want[k])


def test_api_base_trailing_slash_does_not_double_up():
    fake = FakeGetJSON()
    real = _patched(fake)
    try:
        p = dict(PREFS, api="https://opensky-network.org/api/")
        net.poll(POOL, p)
    finally:
        _restore(real)
    url = fake.calls[0]["url"]
    assert "//states" not in url.split("://", 1)[1], url
    assert urllib.parse.urlsplit(url).path == "/api/states/all", url


def test_no_token_sends_no_auth_header():
    fake = FakeGetJSON()
    real = _patched(fake)
    try:
        net.poll(POOL, dict(PREFS, token=""))
    finally:
        _restore(real)
    assert fake.calls[0]["headers"] is None, fake.calls[0]["headers"]


def test_token_sends_bearer_header_stripped():
    fake = FakeGetJSON()
    real = _patched(fake)
    try:
        net.poll(POOL, dict(PREFS, token="  secret-tok  "))
    finally:
        _restore(real)
    assert fake.calls[0]["headers"] == {"Authorization": "Bearer secret-tok"}, fake.calls[0]["headers"]


def test_returns_parsed_json_unchanged():
    resp = {"time": 12345, "states": [["abc123", "UAL123  ", "United States", 12340,
                                       12344, -122.3, 47.6, 100.0, False, 50.0, 90.0,
                                       0.0, None, 1000.0, None, False, 0, 4]]}
    fake = FakeGetJSON(response=resp)
    real = _patched(fake)
    try:
        got = net.poll(POOL, PREFS)
    finally:
        _restore(real)
    assert got is resp


def test_http_status_error_propagates_with_retry_after():
    fake = FakeGetJSON(raises=httpclient.HTTPStatusError(429, retry_after=30))
    real = _patched(fake)
    try:
        try:
            net.poll(POOL, PREFS)
            assert False, "expected HTTPStatusError"
        except httpclient.HTTPStatusError as e:
            assert e.status == 429 and e.retry_after == 30
    finally:
        _restore(real)


def test_other_exceptions_propagate_unchanged():
    for exc in (OSError("no route"), RuntimeError("adafruit_requests boom"),
                TimeoutError("response over 8 s budget"), ValueError("bad json")):
        fake = FakeGetJSON(raises=exc)
        real = _patched(fake)
        try:
            try:
                net.poll(POOL, PREFS)
                assert False, "expected " + type(exc).__name__
            except type(exc) as e:
                assert e is exc
        finally:
            _restore(real)


if __name__ == "__main__":
    n = 0
    for name in sorted(k for k in dir() if k.startswith("test_")):
        globals()[name]()
        print("ok", name)
        n += 1
    print("ok", n, "tests")
