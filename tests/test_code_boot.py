"""Host simulation of code.py's boot status screen and background OTA check
(issues #29 and the boot-screen/IP request): the panel shows version + IP (+
the mDNS name) until the first successful poll instead of a misleading "NO
TRAFFIC"; with a saved `ota_url` it checks for a newer manifest in the
background, announcing a newer version on the panel and in /api/status
without ever applying anything itself. Reuses tests/test_code_linkwatch.py.

Run: python3 tests/test_code_boot.py   (from the repo root)
"""
import json
import os
import sys
import tempfile
import time as _time
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_code_linkwatch as sim  # noqa: E402
import prefs  # noqa: E402
import schedule  # noqa: E402
from version import VERSION  # noqa: E402

T_2025 = 1735689600
_orig_fake_modules = sim.fake_modules
PIN = {"lat": 47.6062, "lon": -122.3321, "nm": 5,
       "sleep_enabled": False, "night_mode": "off"}
MANIFEST_URL = "https://example.com/tailwatch/manifest.json"


def _manifest(version):
    return json.dumps({"version": version, "files": [
        {"path": "code.py", "url": "https://example.com/code.py",
         "sha256": "0" * 64, "size": 10}]}).encode()


class FakeStatusError(Exception):
    def __init__(self, status, retry_after=None):
        super().__init__("HTTP %d" % status)
        self.status = status
        self.retry_after = retry_after


def run(p, polls_ok=True, manifest=None, manifest_err=None, end=80, mdns=False):
    """Boot code.py with /prefs.json = p. polls_ok: OpenSky returns an empty
    sky (else every poll raises OSError). manifest: bytes served for any
    get_bytes() call, or manifest_err: exception raised instead. Returns
    (outcome, serial output); sim.W.manifest_calls counts get_bytes() calls.
    mdns=True also provides a working fake `mdns` module (else the board "has
    none", and lib/mdnsadv.py's ImportError fallback applies)."""
    def make():
        m = _orig_fake_modules()
        sim.W.manifest_calls = 0

        def get_json(pool, url, headers=None, **kw):
            if not polls_ok:
                raise OSError("no uplink")
            return {"time": 1735689500, "states": []}

        def get_bytes(pool, url, headers=None, **kw):
            sim.W.manifest_calls += 1
            if manifest_err is not None:
                raise manifest_err
            return manifest

        m["httpclient"] = types.ModuleType("httpclient")
        m["httpclient"].get_json = get_json
        m["httpclient"].get_bytes = get_bytes
        m["httpclient"].HTTPStatusError = FakeStatusError
        m["httpclient"].reset = lambda: None
        if mdns:
            class Server:
                def __init__(self, radio):
                    self.hostname = None

                def advertise_service(self, **kw):
                    pass

                def deinit(self):
                    pass

            m["mdns"] = types.ModuleType("mdns")
            m["mdns"].Server = Server
        return m

    d = tempfile.mkdtemp()
    old = prefs.PATH, prefs.BACKUP
    prefs.PATH = os.path.join(d, "prefs.json")
    prefs.BACKUP = os.path.join(d, "prefs.bak")
    with open(prefs.PATH, "w") as f:
        json.dump(p, f)
    real_time = _time.time
    _time.time = lambda: T_2025 + sim.W.t
    schedule.set_clock_synced(False)
    sim.fake_modules = make
    sys.modules.pop("mdnsadv", None)  # lib/mdnsadv.py binds `mdns` once, at import
    sys.modules.pop("mdns", None)
    try:
        return sim.run({}, end)
    finally:
        sys.modules.pop("mdnsadv", None)
        sim.fake_modules = _orig_fake_modules
        _time.time = real_time
        prefs.PATH, prefs.BACKUP = old


def _displays(out, kind):
    return [l for l in out.splitlines() if l.startswith("display " + kind)]


# ---- boot screen ----

def test_boot_screen_shows_version_ip_until_first_poll_not_no_traffic():
    outcome, out = run(PIN, polls_ok=False, end=30)
    assert outcome == "stop", (outcome, out[-800:])
    boot = _displays(out, "BOOT")
    assert boot, out
    assert "TAILWATCH v" + VERSION in boot[0], boot[0]
    assert "192.168.1.50" in boot[0], boot[0]  # the sim's station IP
    assert "waiting for data" in boot[0], boot[0]
    assert "display NO TRAFFIC" not in out, out  # the old misleading boot state


def test_boot_screen_names_the_mdns_host_when_advertising():
    outcome, out = run(PIN, polls_ok=False, end=20, mdns=True)
    assert outcome == "stop", (outcome, out[-800:])
    boot = _displays(out, "BOOT")[0]
    # IP, then the per-unit .local name (sim MAC ...04:05), then the status line
    assert "192.168.1.50 / tailwatch-0405.local / waiting for data" in boot, boot


def test_boot_screen_omits_the_mdns_line_when_the_board_has_no_mdns():
    outcome, out = run(PIN, polls_ok=False, end=20, mdns=False)
    boot = _displays(out, "BOOT")[0]
    assert ".local" not in boot, boot
    assert "192.168.1.50 / waiting for data" in boot, boot


def test_boot_screen_gives_way_to_the_card_after_first_successful_poll():
    outcome, out = run(PIN, polls_ok=True, end=40)
    assert outcome == "stop", (outcome, out[-800:])
    lines = [l for l in out.splitlines() if l.startswith("display ")]
    first_ok = next(i for i, l in enumerate(lines) if l == "display NO TRAFFIC")  # empty sky = polled fine
    assert all(not l.startswith("display BOOT") for l in lines[first_ok:]), lines[first_ok:][:5]
    assert any(l.startswith("display BOOT") for l in lines[:first_ok]), lines[:first_ok][:5]


def test_boot_screen_becomes_no_link_if_first_poll_never_succeeds():
    outcome, out = run(PIN, polls_ok=False, end=80)
    assert outcome == "stop", (outcome, out[-800:])
    assert "display NO LINK" in out, out[-500:]
    assert out.index("display BOOT") < out.index("display NO LINK")


# ---- background OTA check ----

def test_newer_manifest_is_announced_on_the_panel_not_applied():
    outcome, out = run(dict(PIN, ota_url=MANIFEST_URL), manifest=_manifest("9.9.9"), end=80)
    assert outcome == "stop", (outcome, out[-800:])
    assert "ota: update available 9.9.9" in out, out
    notice = _displays(out, "UPDATE")
    assert notice, out
    assert "UPDATE AVAILABLE / v9.9.9 / running v" + VERSION in notice[0], notice[0]
    assert "ota applied" not in out, out  # report-only: installing is the owner's tap
    assert sim.W.manifest_calls == 1  # one check, not one per poll


def test_notice_is_temporary_then_normal_display_resumes():
    outcome, out = run(dict(PIN, ota_url=MANIFEST_URL), manifest=_manifest("9.9.9"), end=80)
    lines = [l for l in out.splitlines() if l.startswith("display ")]
    last_notice = max(i for i, l in enumerate(lines) if l.startswith("display UPDATE"))
    assert len(lines) > last_notice + 1, "display never came back after the notice"


def test_same_or_older_version_is_not_announced():
    for v in (VERSION, "0.0.1"):
        outcome, out = run(dict(PIN, ota_url=MANIFEST_URL), manifest=_manifest(v), end=80)
        assert outcome == "stop", (outcome, out[-800:])
        assert "update available" not in out and not _displays(out, "UPDATE"), v
        assert sim.W.manifest_calls == 1, v


def test_no_ota_url_means_no_background_fetch():
    outcome, out = run(PIN, manifest=_manifest("9.9.9"), end=80)
    assert outcome == "stop", (outcome, out[-800:])
    assert sim.W.manifest_calls == 0
    assert "update available" not in out


def test_failed_check_is_logged_retried_late_and_never_crashes():
    outcome, out = run(dict(PIN, ota_url=MANIFEST_URL),
                       manifest_err=OSError("no route"), end=200)
    assert outcome == "stop", (outcome, out[-800:])
    assert "ota check failed no route" in out, out
    assert sim.W.manifest_calls == 1  # RETRY_S is an hour, not every loop
    assert "display NO TRAFFIC" in out  # polling/display unaffected


def test_bad_manifest_is_reported_not_announced():
    outcome, out = run(dict(PIN, ota_url=MANIFEST_URL), manifest=b"not json", end=80)
    assert outcome == "stop", (outcome, out[-800:])
    assert "ota check failed" in out, out
    assert "update available" not in out


if __name__ == "__main__":
    n = 0
    for name in sorted(k for k in dir() if k.startswith("test_")):
        globals()[name]()
        print("ok", name)
        n += 1
    print("ok", n, "tests")
