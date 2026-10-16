import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "firmware", "lib"))
import reqguard

HOST = "192.168.1.50"
MDNS_HOST = "tailwatch-ab12.local"


def allowed(host_hdr, origin, referer, write, extra_host=None):
    return reqguard.check(host_hdr, origin, referer, HOST, write, extra_host=extra_host) is None


def rejected(host_hdr, origin, referer, write, extra_host=None):
    return reqguard.check(host_hdr, origin, referer, HOST, write, extra_host=extra_host) is not None


# allowed
assert allowed(HOST, "http://192.168.1.50", None, True)
assert allowed(HOST + ":80", "http://192.168.1.50:80", None, True)
assert allowed(HOST, None, "http://192.168.1.50/", True)
assert allowed(HOST, None, None, True)  # non-browser client (curl): no Origin/Referer at all
assert allowed(HOST, None, None, False)  # plain GET, correct Host

# rejected: Origin
assert rejected(HOST, "http://evil.example", None, True)
assert rejected(HOST, "null", None, True)
assert rejected(HOST, "https://192.168.1.50", None, True)
assert rejected(HOST, "http://192.168.1.50.evil.com", None, True)
assert rejected(HOST, "http://192.168.1.50@evil.com", None, True)

# rejected: Referer (no Origin present)
assert rejected(HOST, None, "http://evil.com/?h=192.168.1.50", True)

# rejected: Host (GET)
assert rejected("evil.example", None, None, False)
assert rejected(None, None, None, False)
assert rejected(HOST + ":8080", None, None, False)

# issue #31: a page reached via the device's mDNS hostname is still same-origin
assert allowed(MDNS_HOST, "http://" + MDNS_HOST, None, True, extra_host=MDNS_HOST)
assert allowed(MDNS_HOST + ":80", None, "http://" + MDNS_HOST + "/", True, extra_host=MDNS_HOST)
assert allowed(MDNS_HOST, None, None, False, extra_host=MDNS_HOST)  # plain GET
assert allowed(HOST, "http://" + HOST, None, True, extra_host=MDNS_HOST)  # IP form still works too
assert rejected(MDNS_HOST, None, None, False)  # no extra_host given (e.g. mdns not running): rejected
assert rejected(MDNS_HOST, "http://evil.example", None, True, extra_host=MDNS_HOST)
assert rejected("evil-" + MDNS_HOST, None, None, False, extra_host=MDNS_HOST)
# a request for one unit's hostname is never same-origin for a different one
assert rejected("tailwatch-ffff.local", None, None, False, extra_host=MDNS_HOST)

print("reqguard: all passed")
