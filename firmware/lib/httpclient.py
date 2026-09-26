"""The one way TailWatch makes outbound HTTP(S) requests (for lib/net.py's
OpenSky poll). code.py is a single-threaded loop that also serves the
settings UI, so every request here must be short, bounded, and must never
leak a socket:

- One adafruit_requests.Session for the whole run (session()): reuses the SSL
  context and, via keep-alive, the TLS connection itself, so a steady-state
  poll skips DNS and the ~1 s ESP32-S3 TLS handshake.
- timeout=TIMEOUT_S (4 s) on every request. adafruit_requests applies it per
  socket operation (connect, TLS handshake, each recv), not per request, and
  Session.request() retries once on a dead keep-alive socket, so the worst
  case before the first body byte is roughly 2 x 2 x TIMEOUT_S = 16 s (plus
  DNS on a fresh connection). BUDGET_S additionally caps the body read by
  wall clock.
- The response is ALWAYS closed. A clean, fully read 200 goes back to the
  keep-alive pool (r.close()). Anything else (non-200, exception, budget or
  size overrun) drops the socket outright (_drop()): unread body bytes on a
  pooled socket would corrupt the next request, and a response that is never
  closed makes adafruit_connection_manager raise "An existing socket is
  already connected" on every later request to that host.
- Call reset() after a Wi-Fi drop/reconnect (code.py does, on LinkWatch
  events): pooled sockets belong to the old link.

Why 4 s: OpenSky's /states/all for a small bbox normally answers in well under
2 s, and a fresh TLS handshake on the S3 is ~1-1.5 s, so 4 s per operation is
~2x headroom over a normal slow poll, while cutting the worst-case UI stall to
about half of what DESIGN.md's old 5-8 s would allow (up to 32 s with the
retry). A UI request that arrives during a poll is not lost: it waits in the
server's listen backlog (listen(10)) and is answered on the next server.poll().

Lazy imports: importing this module costs nothing and does not need
adafruit_requests on the drive until the first request. Pure Python otherwise:
tests/test_httpclient.py runs it under desktop CPython with a fake Session.
"""
import json
import time

TIMEOUT_S = 4       # per socket operation; see module docstring
BUDGET_S = 8        # wall-clock cap from request start to end of body
MAX_BODY = 32768    # bytes; a 10 nm OpenSky box is a few KB
CHUNK = 1024

_session = None
_pool = None
_clock = time.monotonic


class HTTPStatusError(Exception):
    """Non-200 reply. retry_after: OpenSky's X-Rate-Limit-Retry-After-Seconds
    header (seconds, int) on a 429, else None."""

    def __init__(self, status, retry_after=None):
        super().__init__("HTTP %d" % status)
        self.status = status
        self.retry_after = retry_after


def _new_session(pool):
    import ssl
    import adafruit_requests
    return adafruit_requests.Session(pool, ssl.create_default_context())


def session(pool):
    """The shared Session (created on first use)."""
    global _session, _pool
    if _session is None or pool is not _pool:
        _session = _new_session(pool)
        _pool = pool
    return _session


def _close_all():
    """Force-close every socket adafruit_connection_manager holds for _pool,
    including one stuck "in use" by a Response whose header read raised inside
    Session.get() (we never got the object, so we can't close it ourselves)."""
    if _pool is None:
        return
    try:
        import adafruit_connection_manager
        adafruit_connection_manager.connection_manager_close_all(_pool)
    except Exception as e:  # not installed / pool not managed: nothing pooled
        print("httpclient close_all", e)


def reset():
    """Close every pooled socket and forget the Session (after a Wi-Fi drop).
    Safe to call before any request was made."""
    global _session
    if _session is None:
        return
    _close_all()
    _session = None


def _drop(r):
    """Close r's socket outright instead of returning it to the keep-alive pool."""
    sock = getattr(r, "socket", None)
    if sock is None:
        return
    try:
        import adafruit_connection_manager
        adafruit_connection_manager.get_connection_manager(_pool).close_socket(sock)
    except Exception:
        try:
            sock.close()
        except Exception:
            pass
    r.socket = None


def get_json(pool, url, headers=None, timeout=TIMEOUT_S, budget=BUDGET_S,
             max_body=MAX_BODY):
    """GET url and return the decoded JSON body.

    Raises HTTPStatusError (non-200), TimeoutError (budget), ValueError
    (oversize / bad JSON), OSError / RuntimeError (network, from
    adafruit_requests). The response is closed on every path.
    """
    t0 = _clock()
    r = None
    clean = False
    try:
        r = session(pool).get(url, headers=headers, timeout=timeout)
        if r.status_code != 200:
            ra = r.headers.get("x-rate-limit-retry-after-seconds")
            try:
                ra = int(ra) if ra is not None else None
            except ValueError:
                ra = None
            raise HTTPStatusError(r.status_code, ra)
        buf = bytearray()
        for chunk in r.iter_content(CHUNK):
            buf.extend(chunk)
            if len(buf) > max_body:
                raise ValueError("response over %d bytes" % max_body)
            if _clock() - t0 > budget:
                raise TimeoutError("response over %d s budget" % budget)
        clean = True
    finally:
        if r is None:
            _close_all()    # Session.get() raised: its socket may still be marked in use
        elif clean:
            r.close()       # fully read: socket back to the keep-alive pool
        else:
            _drop(r)
    return json.loads(buf)  # bytearray: no copy (CPython and CircuitPython)
