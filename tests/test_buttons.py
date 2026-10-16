"""Host-side checks for lib/buttons.py: HoldButton fires once per qualifying
hold, needs a release before it can fire again, and ignores a hold shorter
than hold_s.

Run: python3 tests/test_buttons.py
"""
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "firmware", "lib"))

import time as _time  # noqa: E402

_fake_t = [0.0]
_real_monotonic = _time.monotonic
_time.monotonic = lambda: _fake_t[0]


class FakePin:
    def __init__(self):
        self.value = True  # unpressed (active-low, pulled up)


class DigitalInOut:
    def __init__(self, pin):
        self.pin = pin
        self.direction = None
        self.pull = None

    @property
    def value(self):
        return self.pin.value


digitalio = types.ModuleType("digitalio")
digitalio.DigitalInOut = DigitalInOut
digitalio.Direction = types.SimpleNamespace(INPUT="input")
digitalio.Pull = types.SimpleNamespace(UP="up")
sys.modules["digitalio"] = digitalio

import buttons  # noqa: E402


def _set(t):
    _fake_t[0] = t


def test_fires_once_after_hold_s():
    pin = FakePin()
    b = buttons.HoldButton(pin, hold_s=5.0)
    _set(0.0)
    pin.value = False  # pressed
    assert b.poll() is False
    _set(4.9)
    assert b.poll() is False
    _set(5.0)
    assert b.poll() is True
    _set(5.05)
    assert b.poll() is False  # already fired this hold


def test_requires_release_before_firing_again():
    pin = FakePin()
    b = buttons.HoldButton(pin, hold_s=5.0)
    _set(0.0)
    pin.value = False
    assert b.poll() is False  # press noticed at t=0.0
    _set(5.0)
    assert b.poll() is True
    pin.value = True  # release
    assert b.poll() is False
    pin.value = False  # press again
    assert b.poll() is False  # press noticed at t=5.0 (this poll() call)
    _set(5.1)
    assert b.poll() is False  # held only ~0.1s so far
    _set(10.1)
    assert b.poll() is True


def test_release_before_hold_s_resets_the_timer():
    # poll() only learns the pin changed when it's called, same as the real
    # main loop calling it every ~0.05s -- so each state change below is
    # paired with an immediate poll() to pin down exactly when HoldButton
    # records it, rather than when the test merely flips the fake pin.
    pin = FakePin()
    b = buttons.HoldButton(pin, hold_s=5.0)
    _set(0.0)
    pin.value = False
    assert b.poll() is False  # press noticed at t=0.0
    _set(3.0)
    assert b.poll() is False  # held 3.0s, not yet 5.0
    pin.value = True  # released early
    assert b.poll() is False
    pin.value = False  # second press
    assert b.poll() is False  # press noticed at t=3.0 (this poll() call)
    _set(6.0)  # only 3.0s since the second press was noticed
    assert b.poll() is False
    _set(8.0)  # 5.0s since the second press was noticed
    assert b.poll() is True


def test_never_pressed_never_fires():
    pin = FakePin()
    b = buttons.HoldButton(pin, hold_s=5.0)
    _set(0.0)
    assert b.poll() is False
    _set(100.0)
    assert b.poll() is False


def test_pressed_reflects_active_low_pin():
    pin = FakePin()
    b = buttons.HoldButton(pin, hold_s=5.0)
    assert b.pressed() is False
    pin.value = False
    assert b.pressed() is True


if __name__ == "__main__":
    n = 0
    for name in sorted(k for k in dir() if k.startswith("test_")):
        globals()[name]()
        print("ok", name)
        n += 1
    print("ok", n, "tests")
    _time.monotonic = _real_monotonic
