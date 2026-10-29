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
- **Crash-safe swap**: the swap loop, its /ota_state.json bookkeeping and
  the boot-time recover() all live in firmware/ota_recover.py (root, not
  lib/, and not replaceable by an OTA -- see that module's docstring for why
  that matters). Each file's replacement is the `path.new -> (path ->
  path.bak) -> path` dance lib/wifisettings.py's save() uses, and
  recover() finishes the *whole* set after a power cut, including files
  whose swap hadn't started yet.
- **Rollback**: after a completed apply, each live file's immediately-
  previous version is still sitting at `<path>.ota_bak`. rollback() stages
  a *copy* of each backup as `<path>.ota_new` (backups stay intact until
  the swap loop actually starts) and then runs the very same crash-safe
  swap as apply(), so it is recoverable by the same recover(). One level of
  history only; manual, owner-triggered -- automatic boot-failure detection
  would need boot.py changes and a crash counter and is explicitly out of
  scope for this first cut (see DESIGN.md's note on this).

Pure Python (os, json, hashlib if present): runs under desktop CPython for
tests/test_ota.py, which fakes lib/httpclient.py the same way
tests/test_net.py does.
"""
import json
import os

import httpclient
import ota_recover as rec

try:
    import hashlib
except ImportError:
    hashlib = None

MAX_MANIFEST_SIZE = 32768  # ~150 file entries; tools/gen_ota_manifest.py checks this too
MAX_FILE_SIZE = 262144  # 256 KiB: comfortably covers every file in this repo today
# httpclient's default 8 s body budget is sized for OpenSky's few-KB polls; a
# ~170 KB firmware file over TLS on the ESP32-S3 needs far longer. This
# blocks the main loop for as long as a fetch takes, which is acceptable
# only because OTA is an explicit, owner-triggered "device restarts after
# this" action (the web UI says so), unlike the background poll.
FILE_BUDGET_S = 60
NEW_SUFFIX = rec.NEW_SUFFIX
BAK_SUFFIX = rec.BAK_SUFFIX

# A manifest entry's path must land inside the existing firmware tree:
# code.py itself, or under lib/ or www/. Blocks path traversal (".." or a
# leading "/") and blocks overwriting anything else on CIRCUITPY (prefs.json,
# settings.toml, boot.py, ota_recover.py) via a malicious or buggy manifest.
_ALLOWED_TOP = ("lib/", "www/")


class OTAError(Exception):
    """Manifest validation, integrity check, or filesystem failure. The
    message is written straight to the API response and serial -- keep it
    short and specific (which file, what failed)."""


def safe_path(path):
    """True if `path` is a plain relative path under code.py or lib//www/,
    with no ".." traversal, no absolute leading slash, and no backslash or
    control character (CircuitPython's FAT driver accepts "\\" as a path
    separator, so "lib/..\\boot.py" would otherwise slip past a "/"-only
    ".." check)."""
    if not isinstance(path, str) or not path or path.startswith("/"):
        return False
    for ch in path:
        if ch == "\\" or ord(ch) < 0x20:
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


def version_tuple(v):
    """"v1.4.0" / "1.4" -> (1, 4, 0) / (1, 4); None if any dotted part isn't
    a plain non-negative integer (a "-rc1" tag, say)."""
    if not isinstance(v, str):
        return None
    parts = v.strip().lstrip("vV").split(".")
    out = []
    for p in parts:
        if not p.isdigit():
            return None
        out.append(int(p))
    return tuple(out)


def is_newer(remote, local):
    """True if manifest version `remote` should be offered over running
    version `local`. Numeric dotted versions compare as numbers (1.10 > 1.9);
    anything unparseable falls back to "different", so a hand-picked tag is
    still offered rather than silently ignored."""
    r = version_tuple(remote)
    l = version_tuple(local)
    if r is None or l is None:
        return remote != local
    return r > l


class Checker:
    """Background "is there a newer manifest?" check for the panel (issue #29).
    One instance for the whole run (firmware/code.py). Pure bookkeeping around
    fetch_manifest(): due() says when to spend a fetch, check() does it and
    never raises -- a failed check just retries sooner (RETRY_S) and leaves
    whatever was already found in `available`. It only ever *reports*; applying
    stays the owner's explicit action in the web UI.
    """

    FIRST_DELAY_S = 45    # after boot / a URL change: let Wi-Fi, NTP and the first poll settle
    INTERVAL_S = 86400    # between successful checks
    RETRY_S = 3600        # after a failed one

    def __init__(self, local_version):
        self.local = local_version
        self.available = None    # newest newer version string seen, else None
        self.announced = None    # the version the panel has already shown a notice for
        self.error = None
        self._url = None
        self._next_at = None

    def due(self, now, url):
        """True when a fetch should run now. A blank url disables checking
        (and forgets any earlier result); a changed url restarts the clock."""
        if not url:
            self._url = None
            self._next_at = None
            self.available = None
            return False
        if url != self._url:
            self._url = url
            self._next_at = now + self.FIRST_DELAY_S
            self.available = None
        return now >= self._next_at

    def check(self, pool, url, now):
        """Fetch the manifest and update `available`. Returns the version to
        announce on the panel (set the first time a given version is found),
        else None. Never raises."""
        self._url = url  # so a later due(url) doesn't mistake this for a URL change
        try:
            m = fetch_manifest(pool, url)
        except Exception as e:
            self.error = str(e)
            self._next_at = now + self.RETRY_S
            return None
        self.error = None
        self._next_at = now + self.INTERVAL_S
        if is_newer(m["version"], self.local):
            self.available = m["version"]
            if self.announced != self.available:
                self.announced = self.available
                return self.available
        else:
            self.available = None
        return None


def _sha256_hex(data):
    """Hex sha256 of `data`, or None if hashlib is unavailable. Uses only
    the API CircuitPython's hashlib has -- new(name), update(), digest() --
    not CPython's hashlib.sha256()/hexdigest() shortcuts, which it lacks."""
    if hashlib is None:
        return None
    h = hashlib.new("sha256")
    h.update(data)
    return "".join("%02x" % b for b in h.digest())


def _remove_quietly(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _stage_file(pool, f):
    """Fetch, size/sha256-verify, and write f['path'] + NEW_SUFFIX. Raises
    OTAError on any mismatch (wrong size, wrong hash, no hashlib) or
    whatever httpclient raises on a fetch failure -- in every case, no file
    on disk is touched beyond this one's own .ota_new (the caller is what
    cleans those up across files on a later failure)."""
    data = httpclient.get_bytes(pool, f["url"], budget=FILE_BUDGET_S,
                                max_body=MAX_FILE_SIZE)
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


def _copy(src, dst):
    with open(src, "rb") as i:
        with open(dst, "wb") as o:
            while True:
                chunk = i.read(1024)
                if not chunk:
                    break
                o.write(chunk)


def apply(pool, manifest):
    """Fetch + verify + stage every file; only once all succeed, swap every
    one live. Returns manifest["version"]. Raises OTAError (validation/
    integrity) or an httpclient exception (fetch failure) -- either way, if
    raised during staging, every .ota_new this call wrote is removed and no
    live file is touched; see firmware/ota_recover.py for the swap phase's
    own crash safety once it starts.
    """
    files = manifest["files"]
    staged = []
    try:
        for f in files:
            staged.append(f["path"])  # before staging: a half-written .ota_new is cleaned up too
            _stage_file(pool, f)
    except Exception:
        for path in staged:
            _remove_quietly(path + NEW_SUFFIX)
        raise

    paths = [f["path"] for f in files]
    rec.write_state("swapping", manifest["version"], paths, then="done")
    for path in paths:
        rec.swap_one(path)
    rec.write_state("done", manifest["version"], paths)
    return manifest["version"]


def rollback():
    """Restore every file from its last apply()'s .ota_bak over the current
    (presumably bad) version. Returns the list of paths actually restored
    (a path with no .ota_bak -- e.g. it was newly added by that update, so
    there was nothing to revert to -- is skipped, not an error). Raises
    OTAError if there's no completed update recorded to roll back.

    Staged as copies and swapped through the same ota_recover machinery as
    apply(): a power cut before the swap loop starts leaves every .ota_bak
    intact and the state still "done" (just retry); a cut inside the loop
    leaves state "swapping", which recover() finishes toward "rolled_back".
    """
    state = rec.read_state()
    if state is None or state.get("phase") != "done":
        raise OTAError("no completed update to roll back")
    version = state.get("version")
    paths = [p for p in state.get("files", ()) if rec.exists(p + BAK_SUFFIX)]
    staged = []
    try:
        for path in paths:
            staged.append(path)
            _copy(path + BAK_SUFFIX, path + NEW_SUFFIX)
    except Exception:
        for path in staged:
            _remove_quietly(path + NEW_SUFFIX)
        raise
    if paths:
        rec.write_state("swapping", version, paths, then="rolled_back")
        for path in paths:
            rec.swap_one(path)
    rec.write_state("rolled_back", version, state.get("files", ()))
    return paths
