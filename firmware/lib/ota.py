"""On-device OTA firmware update (issue #29): the owner pastes a manifest
URL into the local web UI; the device fetches it and every listed file
directly (no cloud tier, issue #2 -- same "device calls out, nothing calls
in" shape as the OpenSky poll).

Manifest (JSON, fetched from the owner-supplied URL)::

    {
      "version": "1.4.0",
      "files": [
        {"path": "code.py", "url": "https://.../code.py",
         "sha256": "<64 hex chars>", "size": 5234},
        {"path": "lib/hero.py", "url": "https://.../lib/hero.py",
         "sha256": "...", "size": 2345}
      ]
    }

Safety (DESIGN.md issue #29's acceptance criteria):

- **Integrity**: every file's sha256 + size are checked against the
  manifest before anything touches the live filesystem. If `hashlib` isn't
  available on this CircuitPython build (uneven across boards/versions,
  same caveat as lib/mdnsadv.py's `mdns`), apply() refuses outright rather
  than silently skipping verification -- no checksum means no OTA, not a
  quieter one.
- **Nothing partial**: every file is fetched and verified into a `<path>
  .ota_new` staging file first; only once *all* of them succeed does the
  swap phase run at all. A failure partway through staging deletes every
  `.ota_new` it had written and touches zero live files.
- **Crash-safe swap**: each live file's replacement is the exact
  `path.new -> (path -> path.bak) -> path` dance lib/wifisettings.py's
  save()/recover() already use for settings.toml, just looped over
  multiple files with their own `.ota_new`/`.ota_bak` suffixes (so OTA and
  a concurrent Wi-Fi settings save can never collide on the same temp
  name). /ota_state.json records which files are mid-swap so recover()
  (called at boot, same as wifisettings.recover()) can finish an
  interrupted swap instead of leaving a half-applied, possibly unbootable
  set of files.
- **Rollback**: after a completed apply, each live file's immediately-
  previous version is still sitting at `<path>.ota_bak`. rollback() swaps
  every one back over the current (bad) file. One level of history only --
  this is a manual, owner-triggered revert (a new web UI button), not
  automatic boot-failure detection, which would need boot.py changes and a
  crash counter and is explicitly out of scope for this first cut (see
  DESIGN.md's note on this).

Pure Python (os, json, hashlib if present): runs under desktop CPython for
tests/test_ota.py, which fakes lib/httpclient.py the same way
tests/test_net.py does.
"""
import json
import os

import httpclient

try:
    import hashlib
except ImportError:
    hashlib = None

STATE_PATH = "/ota_state.json"
MAX_MANIFEST_SIZE = 8192
MAX_FILE_SIZE = 262144  # 256 KiB: comfortably covers every file in this repo today
NEW_SUFFIX = ".ota_new"
BAK_SUFFIX = ".ota_bak"

# A manifest entry's path must land inside the existing firmware tree:
# code.py itself, or under lib/ or www/. Blocks path traversal (".." or a
# leading "/") and blocks overwriting anything else on CIRCUITPY (prefs.json,
# settings.toml, boot.py) via a malicious or buggy manifest.
_ALLOWED_TOP = ("lib/", "www/")


class OTAError(Exception):
    """Manifest validation, integrity check, or filesystem failure. The
    message is written straight to the API response and serial -- keep it
    short and specific (which file, what failed)."""


def safe_path(path):
    """True if `path` is a plain relative path under code.py or lib//www/,
    with no ".." traversal and no absolute leading slash."""
    if not isinstance(path, str) or not path or path.startswith("/"):
        return False
    if path == "code.py":
        return True
    if not path.startswith(_ALLOWED_TOP):
        return False
    parts = path.split("/")
    return ".." not in parts and "" not in parts[1:]


def parse_manifest(data):
    """JSON bytes/str -> validated manifest dict. Raises OTAError (never
    KeyError/TypeError) on anything malformed, with a specific reason."""
    try:
        m = json.loads(data)
    except ValueError:
        raise OTAError("manifest is not valid JSON")
    if not isinstance(m, dict):
        raise OTAError("manifest must be a JSON object")
    version = m.get("version")
    if not isinstance(version, str) or not version:
        raise OTAError("manifest missing a version string")
    files = m.get("files")
    if not isinstance(files, list) or not files:
        raise OTAError("manifest has no files listed")
    seen = set()
    for f in files:
        if not isinstance(f, dict):
            raise OTAError("each manifest file entry must be an object")
        path = f.get("path")
        url = f.get("url")
        sha256 = f.get("sha256")
        size = f.get("size")
        if not safe_path(path):
            raise OTAError("unsafe or disallowed path: %r" % (path,))
        if path in seen:
            raise OTAError("duplicate path in manifest: %r" % (path,))
        seen.add(path)
        if not isinstance(url, str) or not url.lower().startswith("https://"):
            raise OTAError("file %r: url must be https://" % (path,))
        if not isinstance(sha256, str) or len(sha256) != 64 or not all(
                c in "0123456789abcdefABCDEF" for c in sha256):
            raise OTAError("file %r: sha256 must be 64 hex characters" % (path,))
        if not isinstance(size, int) or isinstance(size, bool) or not (0 < size <= MAX_FILE_SIZE):
            raise OTAError("file %r: size must be 1..%d bytes" % (path, MAX_FILE_SIZE))
    return {"version": version, "files": files}


def fetch_manifest(pool, url):
    """https url -> parse_manifest(...). Propagates httpclient's exceptions
    (HTTPStatusError, OSError, TimeoutError, ...) unchanged, same policy as
    lib/net.py:poll() -- the caller (code.py's route handler) decides how to
    report those; this module never swallows a fetch failure."""
    data = httpclient.get_bytes(pool, url, max_body=MAX_MANIFEST_SIZE)
    return parse_manifest(data)


def _sha256_hex(data):
    if hashlib is None:
        return None
    return hashlib.sha256(data).hexdigest()


def _write_state(phase, version, paths):
    with open(STATE_PATH, "w") as f:
        json.dump({"phase": phase, "version": version, "files": list(paths)}, f)


def _read_state():
    try:
        with open(STATE_PATH, "r") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _stage_file(pool, f):
    """Fetch, size/sha256-verify, and write f['path'] + NEW_SUFFIX. Raises
    OTAError on any mismatch (wrong size, wrong hash, no hashlib) or
    whatever httpclient raises on a fetch failure -- in every case, no file
    on disk is touched beyond this one's own .ota_new (the caller is what
    cleans those up across files on a later failure)."""
    data = httpclient.get_bytes(pool, f["url"], max_body=MAX_FILE_SIZE)
    if len(data) != f["size"]:
        raise OTAError("file %r: fetched %d bytes, manifest says %d" % (
            f["path"], len(data), f["size"]))
    digest = _sha256_hex(data)
    if digest is None:
        raise OTAError("hashlib unavailable on this build: cannot verify "
                        "update integrity, refusing to apply")
    if digest != f["sha256"].lower():
        raise OTAError("file %r: checksum mismatch" % (f["path"],))
    with open(f["path"] + NEW_SUFFIX, "wb") as out:
        out.write(data)


def apply(pool, manifest):
    """Fetch + verify + stage every file; only once all succeed, swap every
    one live. Returns manifest["version"]. Raises OTAError (validation/
    integrity) or an httpclient exception (fetch failure) -- either way, if
    raised during staging, every .ota_new this call wrote is removed and no
    live file is touched; see this module's docstring for the swap phase's
    own crash safety once it starts.
    """
    files = manifest["files"]
    staged = []
    try:
        for f in files:
            _stage_file(pool, f)
            staged.append(f["path"])
    except Exception:
        for path in staged:
            try:
                os.remove(path + NEW_SUFFIX)
            except OSError:
                pass
        raise

    paths = [f["path"] for f in files]
    _write_state("swapping", manifest["version"], paths)
    for path in paths:
        _swap_one(path)
    _write_state("done", manifest["version"], paths)
    return manifest["version"]


def _swap_one(path):
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
    """Finish an interrupted apply() swap phase. Call once at boot, before
    anything imports the modules an OTA might have replaced (same spot
    wifisettings.recover() runs, for the same reason) -- a power cut
    between two of apply()'s per-file renames otherwise leaves that one
    file as only `path.ota_new`, which this promotes back to `path`.
    Silently does nothing if there's no in-progress state, or on a
    read-only filesystem (booted with UP held)."""
    state = _read_state()
    if state is None or state.get("phase") != "swapping":
        return
    for path in state.get("files", ()):
        try:
            os.stat(path)
            continue  # already swapped in (or always existed): nothing to do
        except OSError:
            pass
        try:
            os.rename(path + NEW_SUFFIX, path)
        except OSError:
            pass  # neither path nor path.ota_new exists: nothing recoverable
    try:
        _write_state("done", state.get("version"), state.get("files", ()))
    except OSError:
        pass


def rollback():
    """Restore every file from its last apply()'s .ota_bak over the current
    (presumably bad) version. Returns the list of paths actually restored
    (a path with no .ota_bak -- e.g. it was newly added by that update, so
    there was nothing to revert to -- is skipped, not an error). Raises
    OTAError if there's no completed update recorded to roll back."""
    state = _read_state()
    if state is None or state.get("phase") != "done":
        raise OTAError("no completed update to roll back")
    restored = []
    for path in state.get("files", ()):
        bak = path + BAK_SUFFIX
        try:
            os.stat(bak)
        except OSError:
            continue
        try:
            os.remove(path + NEW_SUFFIX)
        except OSError:
            pass
        os.rename(path, path + NEW_SUFFIX)
        os.rename(bak, path)
        restored.append(path)
    _write_state("rolled_back", state.get("version"), state.get("files", ()))
    return restored
