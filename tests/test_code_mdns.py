"""Host simulation of code.py's mDNS wiring (issue #31): advertises
tailwatch-XXXX.local in station mode only, and restarts/recovers it the same
way restart_http() does across a Wi-Fi drop and reconnect. Reuses the
tests/test_code_linkwatch.py harness, faking lib/mdnsadv.py's `mdns` module
so no real mDNS server is ever touched.

Run: python3 tests/test_code_mdns.py   (from the repo root)
"""
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_code_linkwatch as sim  # noqa: E402  (also puts firmware/lib/ on sys.path)

_orig_fake_modules = sim.fake_modules


class FakeMdnsServer:
    instances = []

    def __init__(self, radio):
        self.radio = radio
        self.hostname = None
        self.services = []
        self.deinit_calls = 0
        FakeMdnsServer.instances.append(self)

    def advertise_service(self, service_type, protocol, port):
        self.services.append((service_type, protocol, port))

    def deinit(self):
        self.deinit_calls += 1


def _fake_modules_with_mdns():
    FakeMdnsServer.instances = []
    m = _orig_fake_modules()
    mod = types.ModuleType("mdns")
    mod.Server = FakeMdnsServer
    m["mdns"] = mod
    return m


def run_with_mdns(events, end):
    """sim.run(), but with a working fake mdns module, and lib/mdnsadv.py
    forced to re-import against it (its `mdns = None`/module binding is
    resolved once at import time and otherwise stays cached across runs)."""
    sim.fake_modules = _fake_modules_with_mdns
    sys.modules.pop("mdnsadv", None)
    sys.modules.pop("mdns", None)
    try:
        return sim.run(events, end)
    finally:
        sim.fake_modules = _orig_fake_modules
        sys.modules.pop("mdnsadv", None)
        sys.modules.pop("mdns", None)


def test_station_mode_advertises_per_unit_hostname():
    # Radio.mac_address in the sim is b"\x00\x01\x02\x03\x04\x05" -> "0405".
    outcome, out = run_with_mdns({}, 20)
    assert outcome == "stop", (outcome, out[-800:])
    assert "ui http://tailwatch-0405.local/" in out, out
    assert len(FakeMdnsServer.instances) == 1
    srv = FakeMdnsServer.instances[0]
    assert srv.hostname == "tailwatch-0405"
    assert srv.services == [("_http", "_tcp", 80)]


def test_drop_stops_and_reconnect_restarts_advertising():
    def drop(w):
        sim.drop(w)

    def back(w):
        w.join_ip = "192.168.1.77"

    outcome, out = run_with_mdns({100: drop, 130: back}, 300)
    assert outcome == "stop", (outcome, out[-800:])
    assert len(FakeMdnsServer.instances) == 2  # initial + one restart on reconnect
    first, second = FakeMdnsServer.instances
    assert first.deinit_calls == 1  # stopped on the drop, not left stale
    assert second.hostname == "tailwatch-0405"  # same per-unit name after rejoining


def test_missing_mdns_module_does_not_crash_station_mode():
    # The default harness (tests/test_code_linkwatch.py) has no fake "mdns"
    # module at all -- lib/mdnsadv.py's own ImportError fallback must hold.
    outcome, out = sim.run({}, 20)
    assert outcome == "stop", (outcome, out[-800:])
    assert "ui http://192.168.1.50/" in out, out  # the plain web UI still comes up
    assert ".local/" not in out, out


if __name__ == "__main__":
    n = 0
    for name in sorted(k for k in dir() if k.startswith("test_")):
        globals()[name]()
        print("ok", name)
        n += 1
    print("ok", n, "tests")
