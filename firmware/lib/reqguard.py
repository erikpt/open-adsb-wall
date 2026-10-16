"""Same-origin guard for the local web UI (issue #14). Pure Python: runs under
desktop CPython for tests/test_reqguard.py.

- Host must be this device's own address (optionally :80): blocks DNS
  rebinding, where evil.example re-resolves to the S3 and reads/writes /api/*.
- On state-changing requests, Origin (else Referer) must be http://<host>:
  blocks CSRF, where some other site makes a LAN browser POST here (the
  browser sets Host to the S3's IP then, so Host alone can't catch it).
- No Origin and no Referer on a POST is allowed: that is a non-browser client
  (curl), which is not a CSRF vector. Browsers always send Origin on POST;
  under no-referrer policies it is the literal "null", which is rejected.
"""


def _norm_host(s):
    """'1.2.3.4' / '1.2.3.4:80' -> '1.2.3.4' (lowercase); None for other ports/junk."""
    if not isinstance(s, str):
        return None
    s = s.strip().lower()
    if not s or "@" in s:
        return None
    if s.endswith(":80"):
        s = s[:-3]
    if ":" in s or not s:
        return None
    return s


def _url_host(url):
    """'http://1.2.3.4[:80][/path?q]' -> '1.2.3.4'; None for https/null/other."""
    if not isinstance(url, str):
        return None
    u = url.strip()
    if u[:7].lower() != "http://":
        return None
    u = u[7:]
    for sep in "/?#":
        i = u.find(sep)
        if i >= 0:
            u = u[:i]
    return _norm_host(u)


def check(host_hdr, origin, referer, host, write, extra_host=None):
    """None if allowed, else a short reason (for the 403 body and serial log).

    extra_host (issue #31): the device's own mDNS hostname (e.g.
    "tailwatch-ab12.local"), accepted alongside its IP -- a page loaded via
    that hostname sends it as Host, and as the authority in Origin/Referer
    on a POST, so both checks must allow it too, not just the IP form.
    """
    me = _norm_host(host)
    if me is None:
        return "device host unknown"
    mine = {me}
    extra = _norm_host(extra_host)
    if extra:
        mine.add(extra)
    if _norm_host(host_hdr) not in mine:
        return "Host %r is not this device" % (host_hdr,)
    if not write:
        return None
    if origin is not None:
        if _url_host(origin) not in mine:
            return "cross-site Origin %r" % (origin,)
        return None
    if referer:
        if _url_host(referer) not in mine:
            return "cross-site Referer %r" % (referer,)
    return None
