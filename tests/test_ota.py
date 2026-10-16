"""Host-side checks for lib/ota.py (issue #29): manifest validation, the
fetch/verify/stage-then-swap apply() pipeline, crash recovery, and manual
rollback. Fakes lib/httpclient.py the same way tests/test_net.py does, and
runs inside a throwaway temp directory (ota.py's manifest paths, e.g.
"code.py"/"lib/hero.py", are relative to CIRCUITPY's root) so it never
touches this checkout.

Run: python3 tests/test_ota.py
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "firmware", "lib"))

import httpclient  # noqa: E402
import ota  # noqa: E402

GOOD_URL = "https://example.com/release/1.4.0/code.py"


def _entry(path, data, url=GOOD_URL):
    return {"path": path, "url": url, "sha256": hashlib.sha256(data).hexdigest(),
            "size": len(data)}


def _manifest(entries, version="1.4.0"):
    return {"version": version, "files": entries}


class FakeGetBytes:
    """Stand-in for httpclient.get_bytes: serves canned bytes by URL, or
    raises a canned exception for one/all URLs."""

    def __init__(self, by_url=None, raises=None):
        self.calls = []
        self.by_url = by_url or {}
        self.raises = raises

    def __call__(self, pool, url, headers=None, **kw):
        self.calls.append(url)
        if self.raises is not None and (callable(self.raises) is False):
            raise self.raises
        if callable(self.raises):
            exc = self.raises(url)
            if exc is not None:
                raise exc
        return self.by_url[url]


def _patched(fake):
    real = httpclient.get_bytes
    httpclient.get_bytes = fake
    return real


def _restore(real):
    httpclient.get_bytes = real


class TempCwd:
    """chdir into a fresh temp dir (with a lib/ and www/ subdir, like the
    real CIRCUITPY root) for the duration of a `with` block."""

    def __enter__(self):
        self.old = os.getcwd()
        self.dir = tempfile.mkdtemp()
        os.chdir(self.dir)
        os.makedirs("lib", exist_ok=True)
        os.makedirs("www", exist_ok=True)
        ota.STATE_PATH = os.path.join(self.dir, "ota_state.json")
        return self.dir

    def __exit__(self, *exc):
        os.chdir(self.old)
        shutil.rmtree(self.dir, ignore_errors=True)


# ---- safe_path ----

def test_safe_path_accepts_code_py_and_lib_and_www():
    assert ota.safe_path("code.py")
    assert ota.safe_path("lib/hero.py")
    assert ota.safe_path("www/index.html")


def test_safe_path_rejects_traversal_and_other_files():
    for bad in ("../boot.py", "lib/../../boot.py", "/etc/passwd", "settings.toml",
                "prefs.json", "boot.py", "", None, "lib/", "lib//hero.py" if False else "lib/x/../y.py"):
        assert not ota.safe_path(bad), bad


# ---- parse_manifest ----

def test_parse_manifest_accepts_valid():
    data = b"x" * 10
    m = ota.parse_manifest(json.dumps(_manifest([_entry("code.py", data)])))
    assert m["version"] == "1.4.0"
    assert m["files"][0]["path"] == "code.py"


def test_parse_manifest_rejects_bad_json():
    try:
        ota.parse_manifest(b"not json")
        assert False
    except ota.OTAError:
        pass


def test_parse_manifest_requires_version_and_files():
    try:
        ota.parse_manifest(json.dumps({"files": []}))
        assert False
    except ota.OTAError:
        pass
    try:
        ota.parse_manifest(json.dumps({"version": "1.0"}))
        assert False
    except ota.OTAError:
        pass
    try:
        ota.parse_manifest(json.dumps({"version": "1.0", "files": []}))
        assert False
    except ota.OTAError:
        pass


def test_parse_manifest_rejects_unsafe_path():
    bad = _entry("../boot.py", b"x")
    try:
        ota.parse_manifest(json.dumps(_manifest([bad])))
        assert False
    except ota.OTAError:
        pass


def test_parse_manifest_rejects_non_https_url():
    bad = dict(_entry("code.py", b"x"), url="http://example.com/code.py")
    try:
        ota.parse_manifest(json.dumps(_manifest([bad])))
        assert False
    except ota.OTAError:
        pass


def test_parse_manifest_rejects_bad_sha256():
    bad = dict(_entry("code.py", b"x"), sha256="not-hex")
    try:
        ota.parse_manifest(json.dumps(_manifest([bad])))
        assert False
    except ota.OTAError:
        pass


def test_parse_manifest_rejects_duplicate_path():
    e = _entry("code.py", b"x")
    try:
        ota.parse_manifest(json.dumps(_manifest([e, dict(e)])))
        assert False
    except ota.OTAError:
        pass


def test_parse_manifest_rejects_oversize():
    bad = dict(_entry("code.py", b"x"), size=ota.MAX_FILE_SIZE + 1)
    try:
        ota.parse_manifest(json.dumps(_manifest([bad])))
        assert False
    except ota.OTAError:
        pass


# ---- fetch_manifest ----

def test_fetch_manifest_parses_response():
    data = b"print(1)"
    fake = FakeGetBytes(by_url={GOOD_URL: json.dumps(_manifest([_entry("code.py", data)])).encode()})
    real = _patched(fake)
    try:
        m = ota.fetch_manifest(object(), GOOD_URL)
    finally:
        _restore(real)
    assert m["version"] == "1.4.0"


# ---- apply() ----

def test_apply_writes_files_and_backs_up_existing():
    with TempCwd():
        with open("code.py", "w") as f:
            f.write("old code")
        new_code = b"new code!"
        new_hero = b"new hero!"
        manifest = _manifest([
            _entry("code.py", new_code, url="https://example.com/code.py"),
            _entry("lib/hero.py", new_hero, url="https://example.com/hero.py"),
        ])
        fake = FakeGetBytes(by_url={
            "https://example.com/code.py": new_code,
            "https://example.com/hero.py": new_hero,
        })
        real = _patched(fake)
        try:
            version = ota.apply(object(), manifest)
        finally:
            _restore(real)
        assert version == "1.4.0"
        with open("code.py", "rb") as f:
            assert f.read() == new_code
        with open("lib/hero.py", "rb") as f:
            assert f.read() == new_hero
        with open("code.py" + ota.BAK_SUFFIX, "rb") as f:
            assert f.read() == b"old code"
        assert not os.path.exists("lib/hero.py" + ota.BAK_SUFFIX)  # brand-new file: nothing to back up
        assert not os.path.exists("code.py" + ota.NEW_SUFFIX)
        with open(ota.STATE_PATH) as f:
            state = json.load(f)
        assert state["phase"] == "done" and state["version"] == "1.4.0"


def test_apply_checksum_mismatch_touches_no_live_files():
    with TempCwd():
        with open("code.py", "w") as f:
            f.write("old code")
        manifest = _manifest([_entry("code.py", b"expected", url="https://example.com/code.py")])
        fake = FakeGetBytes(by_url={"https://example.com/code.py": b"tampered!"})
        real = _patched(fake)
        try:
            try:
                ota.apply(object(), manifest)
                assert False
            except ota.OTAError:
                pass
        finally:
            _restore(real)
        with open("code.py") as f:
            assert f.read() == "old code"  # untouched
        assert not os.path.exists("code.py" + ota.NEW_SUFFIX)
        assert not os.path.exists("code.py" + ota.BAK_SUFFIX)


def test_apply_size_mismatch_is_rejected():
    with TempCwd():
        bad = dict(_entry("code.py", b"abc", url="https://example.com/code.py"), size=999)
        manifest = _manifest([bad])
        fake = FakeGetBytes(by_url={"https://example.com/code.py": b"abc"})
        real = _patched(fake)
        try:
            try:
                ota.apply(object(), manifest)
                assert False
            except ota.OTAError:
                pass
        finally:
            _restore(real)
        assert not os.path.exists("code.py")


def test_apply_second_file_failure_cleans_up_first_files_staging():
    with TempCwd():
        good = _entry("code.py", b"good data", url="https://example.com/code.py")
        bad = _entry("lib/hero.py", b"expected", url="https://example.com/hero.py")
        manifest = _manifest([good, bad])
        fake = FakeGetBytes(by_url={
            "https://example.com/code.py": b"good data",
            "https://example.com/hero.py": b"TAMPERED",
        })
        real = _patched(fake)
        try:
            try:
                ota.apply(object(), manifest)
                assert False
            except ota.OTAError:
                pass
        finally:
            _restore(real)
        # neither file was ever written live, and the first file's staged
        # .ota_new (written before the second file failed) is cleaned up too
        assert not os.path.exists("code.py")
        assert not os.path.exists("code.py" + ota.NEW_SUFFIX)
        assert not os.path.exists("lib/hero.py")


def test_apply_without_hashlib_refuses():
    with TempCwd():
        manifest = _manifest([_entry("code.py", b"data", url="https://example.com/code.py")])
        fake = FakeGetBytes(by_url={"https://example.com/code.py": b"data"})
        real = _patched(fake)
        real_hashlib = ota.hashlib
        ota.hashlib = None
        try:
            try:
                ota.apply(object(), manifest)
                assert False
            except ota.OTAError as e:
                assert "hashlib" in str(e)
        finally:
            _restore(real)
            ota.hashlib = real_hashlib
        assert not os.path.exists("code.py")


def test_apply_fetch_failure_propagates_and_cleans_up():
    with TempCwd():
        manifest = _manifest([_entry("code.py", b"data", url="https://example.com/code.py")])
        fake = FakeGetBytes(by_url={}, raises=OSError("no route"))
        real = _patched(fake)
        try:
            try:
                ota.apply(object(), manifest)
                assert False
            except OSError:
                pass
        finally:
            _restore(real)
        assert not os.path.exists("code.py")
        assert not os.path.exists("code.py" + ota.NEW_SUFFIX)


# ---- recover() ----

def test_recover_finishes_interrupted_swap():
    with TempCwd():
        # Simulate a power cut between os.rename(path, bak) and
        # os.rename(new, path): code.py is gone, only code.py.ota_new remains.
        with open("code.py" + ota.NEW_SUFFIX, "w") as f:
            f.write("new code")
        ota._write_state("swapping", "1.4.0", ["code.py"])
        ota.recover()
        with open("code.py") as f:
            assert f.read() == "new code"
        with open(ota.STATE_PATH) as f:
            assert json.load(f)["phase"] == "done"


def test_recover_is_a_noop_when_swap_already_completed():
    with TempCwd():
        with open("code.py", "w") as f:
            f.write("already swapped")
        ota._write_state("swapping", "1.4.0", ["code.py"])
        ota.recover()  # path exists already: nothing to promote
        with open("code.py") as f:
            assert f.read() == "already swapped"


def test_recover_is_a_noop_with_no_state_file():
    with TempCwd():
        ota.recover()  # must not raise


# ---- rollback() ----

def test_rollback_restores_previous_version():
    with TempCwd():
        with open("code.py", "w") as f:
            f.write("original")
        new_code = b"updated"
        manifest = _manifest([_entry("code.py", new_code, url="https://example.com/code.py")])
        fake = FakeGetBytes(by_url={"https://example.com/code.py": new_code})
        real = _patched(fake)
        try:
            ota.apply(object(), manifest)
        finally:
            _restore(real)
        with open("code.py", "rb") as f:
            assert f.read() == new_code
        restored = ota.rollback()
        assert restored == ["code.py"]
        with open("code.py") as f:
            assert f.read() == "original"


def test_rollback_skips_files_with_no_backup():
    with TempCwd():
        # lib/hero.py was a brand-new file added by the update: no .ota_bak
        new_hero = b"brand new"
        manifest = _manifest([_entry("lib/hero.py", new_hero, url="https://example.com/hero.py")])
        fake = FakeGetBytes(by_url={"https://example.com/hero.py": new_hero})
        real = _patched(fake)
        try:
            ota.apply(object(), manifest)
        finally:
            _restore(real)
        restored = ota.rollback()
        assert restored == []  # nothing to roll back to, but not an error


def test_rollback_without_a_completed_update_raises():
    with TempCwd():
        try:
            ota.rollback()
            assert False
        except ota.OTAError:
            pass


if __name__ == "__main__":
    n = 0
    for name in sorted(k for k in dir() if k.startswith("test_")):
        globals()[name]()
        print("ok", name)
        n += 1
    print("ok", n, "tests")
