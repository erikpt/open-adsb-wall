"""Host-side checks for lib/httpclient.py: one reused Session, a short
timeout on every request, and the response closed on every path.

Run: python3 tests/test_httpclient.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))

import httpclient  # noqa: E402

POOL = object()


class Sock:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class Resp:
    def __init__(self, status=200, chunks=(b'{"states": []}',), headers=None,
                 raise_at=None, tick=0.0, clock=None):
        self.status_code = status
        self.headers = headers or {}
        self._chunks = chunks
        self._raise_at = raise_at
        self._tick = tick
        self._clock = clock
        self.socket = Sock()
        self.returned_to_pool = False

    def iter_content(self, n):
        for i, c in enumerate(self._chunks):
            if self._raise_at == i:
                raise OSError(116, "ETIMEDOUT")
            if self._clock is not None:
                self._clock.t += self._tick
            yield c
        self.close()  # adafruit_requests does this at end of stream

    def close(self):
        if self.socket is not None:
            self.returned_to_pool = True
            self.socket = None


class Session:
    def __init__(self):
        self.calls = []
        self.next = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append((url, headers, timeout))
        r = self.next.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def fresh():
    made = []

    def new(pool):
        s = Session()
        made.append(s)
        return s

    httpclient._session = None
    httpclient._pool = None
    httpclient._new_session = new
    httpclient._clock = Clock()
    return made


def test_session_reused_and_timeout_passed():
    made = fresh()
    for _ in range(3):
        s = httpclient.session(POOL)
        s.next.append(Resp())
        assert httpclient.get_json(POOL, "https://x/api") == {"states": []}
    assert len(made) == 1
    assert all(c[2] == httpclient.TIMEOUT_S for c in made[0].calls)
    assert httpclient.TIMEOUT_S <= 5


def test_ok_response_returned_to_pool():
    fresh()
    r = Resp(chunks=(b'{"a":', b" 1}"))
    httpclient.session(POOL).next.append(r)
    assert httpclient.get_json(POOL, "https://x") == {"a": 1}
    assert r.returned_to_pool and r.socket is None


def test_non_200_drops_socket_and_reports_retry_after():
    fresh()
    r = Resp(status=429, headers={"x-rate-limit-retry-after-seconds": "37"})
    sock = r.socket
    httpclient.session(POOL).next.append(r)
    try:
        httpclient.get_json(POOL, "https://x")
        raise AssertionError("no raise")
    except httpclient.HTTPStatusError as e:
        assert e.status == 429 and e.retry_after == 37
    assert sock.closed and r.socket is None and not r.returned_to_pool


def test_error_mid_body_drops_socket():
    fresh()
    r = Resp(chunks=(b"{", b"}"), raise_at=1)
    sock = r.socket
    httpclient.session(POOL).next.append(r)
    try:
        httpclient.get_json(POOL, "https://x")
        raise AssertionError("no raise")
    except OSError:
        pass
    assert sock.closed and r.socket is None


def test_budget_and_size_caps():
    fresh()
    clk = httpclient._clock
    r = Resp(chunks=(b"[",) + (b"1,",) * 20 + (b"1]",), tick=1.0, clock=clk)
    sock = r.socket
    httpclient.session(POOL).next.append(r)
    try:
        httpclient.get_json(POOL, "https://x")
        raise AssertionError("no raise")
    except TimeoutError:
        pass
    assert sock.closed
    assert clk.t <= httpclient.BUDGET_S + 2

    fresh()
    r = Resp(chunks=(b"x" * 1024,) * 40)
    sock = r.socket
    httpclient.session(POOL).next.append(r)
    try:
        httpclient.get_json(POOL, "https://x")
        raise AssertionError("no raise")
    except ValueError:
        pass
    assert sock.closed


def test_get_raising_does_not_leave_session_broken():
    made = fresh()
    s = httpclient.session(POOL)
    s.next += [OSError(113, "EHOSTUNREACH"), Resp()]
    try:
        httpclient.get_json(POOL, "https://x")
        raise AssertionError("no raise")
    except OSError:
        pass
    assert httpclient.get_json(POOL, "https://x") == {"states": []}
    assert len(made) == 1


def test_reset_forgets_session():
    made = fresh()
    httpclient.reset()               # no session yet: no-op, no import
    httpclient.session(POOL)
    httpclient.reset()
    assert httpclient._session is None
    httpclient.session(POOL)
    assert len(made) == 2


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            n += 1
    print("ok", n, "tests")
