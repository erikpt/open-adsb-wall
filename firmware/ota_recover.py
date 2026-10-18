"""Crash-safe swap + boot-time recovery for OTA updates (issue #29).

Lives at the CIRCUITPY root, NOT in lib/, on purpose: lib/ota.py's manifest
allow-list only lets an OTA replace code.py or files under lib/ and www/, so
this module can never itself be mid-swap when a power cut happens. That is
what lets firmware/boot.py and the first lines of firmware/code.py import it
and call recover() *before* any lib/ module (any of which an interrupted OTA
may have left as only `<path>.ota_new`) is imported. It imports nothing but
os and json, for the same reason.

State file /ota_state.json::

    {"phase": "swapping" | "done" | "rolled_back",
     "then": "done" | "rolled_back",     # only while swapping
     "version": "...", "files": ["code.py", "lib/hero.py", ...]}

"swapping" is written only after every replacement has been fully staged as
`<path>.ota_new` (lib/ota.py apply()/rollback()), and carries the phase to
settle on once every swap finishes ("then"). A power cut anywhere in the swap
loop therefore leaves state "swapping", and recover() finishes the *whole*
set, not just the file that was mid-rename.
"""
import json
import os

STATE_PATH = "/ota_state.json"
NEW_SUFFIX = ".ota_new"
BAK_SUFFIX = ".ota_bak"


def write_state(phase, version, paths, then=None):
    state = {"phase": phase, "version": version, "files": list(paths)}
    if then is not None:
        state["then"] = then
    with open(STATE_PATH, "w") as f:
        json.dump(state, f)


def read_state():
    try:
        with open(STATE_PATH, "r") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def swap_one(path):
    """path.ota_new -> (path -> path.ota_bak) -> path. Mirrors
    lib/wifisettings.py:save()'s crash-safe rename order exactly."""
    bak = path + BAK_SUFFIX
    new = path + NEW_SUFFIX
    try:
        os.remove(bak)
    except OSError:
        pass
    try:
        os.rename(path, bak)
    except OSError:
        pass  # path didn't exist yet (a brand-new file the manifest added)
    os.rename(new, path)


def recover():
    """Finish an interrupted swap phase. Call as early as possible at boot
    (boot.py, and again before code.py's own imports). For every file listed
    in a "swapping" state:

    - `path.ota_new` absent: this file's swap already completed (or never
      needed one) -- nothing to do.
    - `path` absent, `path.ota_new` present: the cut landed between that
      file's two renames; the old version is already safe at `path.ota_bak`,
      so just promote the new one.
    - both present: this file's swap never started (the cut landed between
      files); run its full swap now.

    Then settles the state on its recorded "then" phase. Silently does
    nothing if there is no in-progress state, or on a read-only filesystem
    (booted with UP held) -- recover() runs again before code.py's imports,
    so a later writable boot still finishes the job.
    """
    state = read_state()
    if state is None or state.get("phase") != "swapping":
        return
    files = state.get("files", ())
    try:
        for path in files:
            new = path + NEW_SUFFIX
            if not exists(new):
                continue
            if exists(path):
                swap_one(path)
            else:
                os.rename(new, path)
        write_state(state.get("then") or "done", state.get("version"), files)
    except OSError:
        pass
