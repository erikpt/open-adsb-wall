"""Host simulation of code.py's setup-AP fallback (DESIGN.md sec. 7 "AP mode"),
reusing the tests/test_code_linkwatch.py fake-CircuitPython harness.

Run: python3 tests/test_code_apmode.py   (from the tailwatch-s3 root)
"""
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_code_linkwatch as sim  # noqa: E402

ALPHABET = "abcdefghijkmnpqrstuvwxyz23456789"
_orig_fake_modules = sim.fake_modules


def _ap_fake_modules():
    """The station harness, but the configured network never answers."""
    m = _orig_fake_modules()
    radio = sim.W.radio
    radio.connected = False
    radio.ipv4_address = None
    sim.W.ap = []

    def start_scanning_networks():
        return iter([types.SimpleNamespace(ssid="Neighbour", rssi=-60, channel=1),
                     types.SimpleNamespace(ssid="Other", rssi=-70, channel=6)])

    def start_ap(ssid, pw, channel=None, authmode=None, max_connections=None):
        sim.W.ap.append((ssid, pw, channel, tuple(authmode or ()), max_connections))
        radio.ipv4_address_ap = "192.168.4.1"

    radio.start_scanning_networks = start_scanning_networks
    radio.stop_scanning_networks = lambda: None
    radio.stop_station = lambda: None
    radio.start_ap = start_ap
    m["wifi"].AuthMode = types.SimpleNamespace(WPA2="WPA2", PSK="PSK", OPEN="OPEN")
    return m


def run_ap(ssid, end):
    """Boot code.py with CIRCUITPY_WIFI_SSID = ssid and a radio that can't join."""
    real_getenv = os.getenv

    def getenv(k, default=None):
        return ssid if k == "CIRCUITPY_WIFI_SSID" else real_getenv(k, default)

    sim.fake_modules, os.getenv = _ap_fake_modules, getenv
    try:
        return sim.run({}, end)
    finally:
        sim.fake_modules, os.getenv = _orig_fake_modules, real_getenv


def check_ap_started(out):
    assert len(sim.W.ap) == 1, sim.W.ap
    ssid, pw, chan, auth, maxc = sim.W.ap[0]
    assert ssid == "TailWatch-0405", ssid          # last two MAC bytes
    assert len(pw) == 8 and all(ch in ALPHABET for ch in pw), pw
    assert "WPA2" in auth and "OPEN" not in auth, auth
    assert chan == 11 and maxc == 2, (chan, maxc)  # 1 and 6 are busy in the scan
    assert ("SETUP: join Wi-Fi %s password %s, open http://192.168.4.1/" % (ssid, pw)) in out, out
    hosts = [h for _, h in sim.W.starts]
    assert hosts and all(h == "192.168.4.1" for h in hosts), hosts  # UI served on the AP
    return pw


def test_no_ssid_stays_in_ap_mode():
    outcome, out = run_ap("", 1500)
    assert outcome == "stop", (outcome, out[-800:])   # no idle reboot without an SSID
    check_ap_started(out)
    assert sim.W.connects == [], sim.W.connects        # nothing to join
    assert "ntp" not in out, out                       # no NTP attempt in AP mode


def test_unreachable_ssid_falls_back_then_reboots_when_idle():
    outcome, out = run_ap("HomeNet", 1500)
    assert outcome == "reset", (outcome, out[-800:])
    assert len(sim.W.connects) == 2, sim.W.connects    # two 10 s join attempts
    pw = check_ap_started(out)
    assert 600 <= sim.W.resets[0] <= 640, sim.W.resets  # AP_IDLE_RETRY_S after boot
    assert "setup AP idle; rebooting to retry HomeNet" in out
    assert "hunter2-secret" not in out and out.count(pw) == 1


def test_fresh_password_each_boot():
    run_ap("", 5)
    a = sim.W.ap[0][1]
    run_ap("", 5)
    b = sim.W.ap[0][1]
    assert a != b, (a, b)   # os.urandom per boot; 1-in-2**40 false failure


if __name__ == "__main__":
    n = 0
    for name in sorted(k for k in dir() if k.startswith("test_")):
        globals()[name]()
        print("ok", name)
        n += 1
    print("ok", n, "tests")
