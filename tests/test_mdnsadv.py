"""Host-side checks for lib/mdnsadv.py (issue #31): best-effort mDNS
advertisement -- missing module, construction failure, and the restart
(stop-then-start) shape firmware/code.py relies on for Wi-Fi reconnects.

Run: python3 tests/test_mdnsadv.py
"""
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "firmware", "lib"))


class FakeServer:
    instances = []

    def __init__(self, radio):
        self.radio = radio
        self.hostname = None
        self.services = []
        self.deinit_calls = 0
        FakeServer.instances.append(self)

    def advertise_service(self, service_type, protocol, port):
        self.services.append((service_type, protocol, port))

    def deinit(self):
        self.deinit_calls += 1


def _install_fake_mdns():
    FakeServer.instances = []
    mod = types.ModuleType("mdns")
    mod.Server = FakeServer
    sys.modules["mdns"] = mod
    sys.modules.pop("mdnsadv", None)  # re-import against this fake
    import mdnsadv
    return mdnsadv


def test_start_advertises_http_tcp_80_at_given_hostname():
    mdnsadv = _install_fake_mdns()
    adv = mdnsadv.Advertiser("radio", "tailwatch-ab12")
    assert adv.start() is True
    srv = FakeServer.instances[0]
    assert srv.radio == "radio"
    assert srv.hostname == "tailwatch-ab12"
    assert srv.services == [("_http", "_tcp", 80)]


def test_stop_calls_deinit_and_clears_server():
    mdnsadv = _install_fake_mdns()
    adv = mdnsadv.Advertiser("radio", "tailwatch-ab12")
    adv.start()
    srv = FakeServer.instances[0]
    adv.stop()
    assert srv.deinit_calls == 1
    assert adv.server is None
    adv.stop()  # idempotent: no server, no crash
    assert srv.deinit_calls == 1


def test_restart_stops_the_previous_server_first():
    mdnsadv = _install_fake_mdns()
    adv = mdnsadv.Advertiser("radio", "tailwatch-ab12")
    adv.start()
    first = FakeServer.instances[0]
    assert adv.start() is True  # e.g. a Wi-Fi reconnect calling start() again
    assert first.deinit_calls == 1
    assert len(FakeServer.instances) == 2
    assert adv.server is FakeServer.instances[1]


def test_missing_mdns_module_is_a_no_op_not_a_crash():
    sys.modules.pop("mdns", None)
    sys.modules.pop("mdnsadv", None)
    import mdnsadv
    adv = mdnsadv.Advertiser("radio", "tailwatch-ab12")
    assert adv.start() is False
    assert adv.server is None
    adv.stop()  # still safe to call


def test_construction_failure_is_caught_not_raised():
    mod = types.ModuleType("mdns")

    class BoomServer:
        def __init__(self, radio):
            raise RuntimeError("mdns not supported on this build")

    mod.Server = BoomServer
    sys.modules["mdns"] = mod
    sys.modules.pop("mdnsadv", None)
    import mdnsadv
    adv = mdnsadv.Advertiser("radio", "tailwatch-ab12")
    assert adv.start() is False
    assert adv.server is None


if __name__ == "__main__":
    n = 0
    for name in sorted(k for k in dir() if k.startswith("test_")):
        globals()[name]()
        print("ok", name)
        n += 1
    print("ok", n, "tests")
