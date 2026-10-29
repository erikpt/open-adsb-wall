"""Host-side checks for firmware/boot.py's OTA recovery hook (issue #29):
after the read-write remount, boot.py finishes an interrupted OTA swap with
only its own imports loaded (so even a missing code.py gets promoted back),
skips it when UP is held (read-only to code.py), and never lets a recovery
failure block the boot itself.

Run: python3 tests/test_boot.py
"""
import os
import runpy
import shutil
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
FIRMWARE = os.path.join(HERE, "..", "firmware")
sys.path.insert(0, FIRMWARE)  # root-level ota_recover.py, as on CIRCUITPY

import ota_recover as rec  # noqa: E402


def _run_boot(up_held):
    calls = {"remount": 0}

    class Pin:
        def __init__(self, pin):
            self.value = not up_held  # active-low

        def switch_to_input(self, pull=None):
            pass

        def deinit(self):
            pass

    def remount(path, readonly=True):
        calls["remount"] += 1

    mods = {
        "board": types.SimpleNamespace(BUTTON_UP="UP"),
        "digitalio": types.SimpleNamespace(
            DigitalInOut=Pin, Pull=types.SimpleNamespace(UP="up")),
        "storage": types.SimpleNamespace(remount=remount),
    }
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        runpy.run_path(os.path.join(FIRMWARE, "boot.py"), run_name="__main__")
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return calls


class Sandbox:
    def __enter__(self):
        self.old = os.getcwd()
        self.dir = tempfile.mkdtemp()
        os.chdir(self.dir)
        rec.STATE_PATH = os.path.join(self.dir, "ota_state.json")
        return self.dir

    def __exit__(self, *exc):
        os.chdir(self.old)
        shutil.rmtree(self.dir, ignore_errors=True)


def _interrupted_code_py():
    # power cut between code.py's two renames: no code.py at all, only the new one
    with open("code.py" + rec.BAK_SUFFIX, "w") as f:
        f.write("old")
    with open("code.py" + rec.NEW_SUFFIX, "w") as f:
        f.write("new")
    rec.write_state("swapping", "1.4.0", ["code.py"], then="done")


def test_normal_boot_recovers_a_missing_code_py():
    with Sandbox():
        _interrupted_code_py()
        calls = _run_boot(up_held=False)
        assert calls["remount"] == 1
        with open("code.py") as f:
            assert f.read() == "new"


def test_up_held_boot_skips_recovery():
    with Sandbox():
        _interrupted_code_py()
        calls = _run_boot(up_held=True)
        assert calls["remount"] == 0
        assert not os.path.exists("code.py")  # still pending; code.py's own call retries


def test_recovery_failure_does_not_block_boot():
    with Sandbox():
        real = rec.recover

        def boom():
            raise RuntimeError("fs exploded")

        rec.recover = boom
        try:
            calls = _run_boot(up_held=False)  # must not raise
        finally:
            rec.recover = real
        assert calls["remount"] == 1


if __name__ == "__main__":
    n = 0
    for name in sorted(k for k in dir() if k.startswith("test_")):
        globals()[name]()
        print("ok", name)
        n += 1
    print("ok", n, "tests")
