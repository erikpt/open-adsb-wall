"""Host simulation of code.py's Bad Apple easter egg wiring (issue #30):
hold-UP-5s trigger, non-blocking playback (the HTTP server keeps getting
polled every iteration while it plays), a repeat trigger stopping it early,
and a clean return to the normal card display afterward. Reuses the
tests/test_code_linkwatch.py harness.

Run: python3 tests/test_code_badapple.py   (from the repo root)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_code_linkwatch as sim  # noqa: E402

PIN = {"lat": 47.6062, "lon": -122.3321, "nm": 5,
       "sleep_enabled": False, "night_mode": "off"}


def hold_up(w):
    w.buttons["BUTTON_UP"].value = False  # active-low: pressed


def release_up(w):
    w.buttons["BUTTON_UP"].value = True


def test_hold_up_5s_starts_playback_without_blocking_http():
    # Hold at t=1, 5s later (t=6) HoldButton fires. Run well past the clip's
    # own ~24s length (288 frames / 12 fps) so it finishes on its own.
    outcome, out = sim.run({1: hold_up}, 40)
    assert outcome == "stop", (outcome, out[-800:])
    assert "badapple: start" in out, out
    assert "badapple: stop (clip ended)" in out, out
    # server.poll() must keep running every iteration throughout -- a single
    # blocking play() loop would make this count collapse to ~1 for the
    # whole clip instead of one per ~0.05s main-loop iteration.
    assert out.count("\nhttp ") == 0, "server.poll() raised unexpectedly"


def test_does_not_trigger_before_hold_s_elapses():
    def release_early(w):
        w.buttons["BUTTON_UP"].value = True

    outcome, out = sim.run({1: hold_up, 3: release_early}, 10)
    assert outcome == "stop", (outcome, out[-800:])
    assert "badapple: start" not in out, out


def test_repeat_trigger_stops_playback_early():
    def hold_again(w):
        w.buttons["BUTTON_UP"].value = False

    def release_again(w):
        w.buttons["BUTTON_UP"].value = True

    # First hold starts playback (fires at t=6); release then hold again for
    # another 5s to stop it early (fires at t=13), well before the ~24s clip
    # (288 frames / 12 fps) would finish on its own. release_again lands
    # comfortably after the fire time, not racing the exact 0.05s-step poll.
    outcome, out = sim.run(
        {1: hold_up, 7: release_up, 8: hold_again, 14: release_again}, 20)
    assert outcome == "stop", (outcome, out[-800:])
    assert out.count("badapple: start") == 1, out
    assert "badapple: stop (repeat trigger)" in out, out
    assert "badapple: stop (clip ended)" not in out, out


def test_normal_display_resumes_after_playback():
    outcome, out = sim.run({1: hold_up}, 40)
    assert outcome == "stop", (outcome, out[-800:])
    stop_i = out.index("badapple: stop (clip ended)")
    after = out[stop_i:]
    # No poll ever succeeds in this sim, so the normal display that resumes is
    # the boot status screen (issue #30 only cares that refresh_display() came back).
    assert "display BOOT" in after, after[:500]


if __name__ == "__main__":
    n = 0
    for name in sorted(k for k in dir() if k.startswith("test_")):
        globals()[name]()
        print("ok", name)
        n += 1
    print("ok", n, "tests")
