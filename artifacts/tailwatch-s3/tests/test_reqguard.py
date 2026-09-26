import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import reqguard

HOST = "192.168.1.50"


def allowed(host_hdr, origin, referer, write):
    return reqguard.check(host_hdr, origin, referer, HOST, write) is None


def rejected(host_hdr, origin, referer, write):
    return reqguard.check(host_hdr, origin, referer, HOST, write) is not None


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

print("reqguard: all passed")
