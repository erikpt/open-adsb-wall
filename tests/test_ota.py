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

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "firmware", "lib"))
sys.path.insert(0, os.path.join(HERE, "..", "firmware"))  # root-level ota_recover.py

import httpclient  # noqa: E402
import ota  # noqa: E402
import ota_recover as rec  # noqa: E402

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
        self.kwargs = []
        self.by_url = by_url or {}
        self.raises = raises

    def __call__(self, pool, url, headers=None, **kw):
        self.calls.append(url)
        self.kwargs.append(kw)
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
        rec.STATE_PATH = os.path.join(self.dir, "ota_state.json")
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
                "prefs.json", "boot.py", "ota_recover.py", "", None, "lib/",
                "lib//hero.py", "lib/x/../y.py"):
        assert not ota.safe_path(bad), bad


def test_safe_path_rejects_backslash_and_control_chars():
    # FatFs accepts "\\" as a separator, so these would otherwise walk out of lib/www
    for bad in ("lib/..\\boot.py", "www/..\\..\\prefs.json", "lib\\hero.py",
                "lib/he\x00ro.py", "lib/he\nro.py"):
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
        with open(rec.STATE_PATH) as f:
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
        rec.write_state("swapping", "1.4.0", ["code.py"])
        rec.recover()
        with open("code.py") as f:
            assert f.read() == "new code"
        with open(rec.STATE_PATH) as f:
            assert json.load(f)["phase"] == "done"


def test_recover_is_a_noop_when_swap_already_completed():
    with TempCwd():
        with open("code.py", "w") as f:
            f.write("already swapped")
        rec.write_state("swapping", "1.4.0", ["code.py"])
        rec.recover()  # path exists already: nothing to promote
        with open("code.py") as f:
            assert f.read() == "already swapped"


def test_recover_is_a_noop_with_no_state_file():
    with TempCwd():
        rec.recover()  # must not raise


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


# ---- crash safety / regression tests for review findings ----

class _PowerCut(Exception):
    pass


def _cut_swap_after(n):
    """Make rec.swap_one raise _PowerCut on its (n+1)th call, like losing
    power between per-file swaps. Returns an undo callable."""
    real = rec.swap_one
    count = [0]

    def cutting(path):
        if count[0] >= n:
            raise _PowerCut()
        count[0] += 1
        real(path)

    rec.swap_one = cutting
    return lambda: setattr(rec, "swap_one", real)


def _two_file_manifest():
    a, b = b"new code", b"new hero"
    manifest = _manifest([
        _entry("code.py", a, url="https://example.com/code.py"),
        _entry("lib/hero.py", b, url="https://example.com/hero.py"),
    ])
    fake = FakeGetBytes(by_url={"https://example.com/code.py": a,
                                "https://example.com/hero.py": b})
    return manifest, fake


def _read(path):
    with open(path, "rb") as f:
        return f.read()


def test_recover_finishes_whole_set_when_cut_between_files():
    with TempCwd():
        for name, text in (("code.py", "old code"), ("lib/hero.py", "old hero")):
            with open(name, "w") as f:
                f.write(text)
        manifest, fake = _two_file_manifest()
        real = _patched(fake)
        undo = _cut_swap_after(1)  # first file swaps, power dies before the second
        try:
            try:
                ota.apply(object(), manifest)
                assert False
            except _PowerCut:
                pass
        finally:
            undo()
            _restore(real)
        # the half-applied state a reboot would find
        assert _read("code.py") == b"new code" and _read("lib/hero.py") == b"old hero"
        assert os.path.exists("lib/hero.py" + ota.NEW_SUFFIX)
        rec.recover()
        assert _read("code.py") == b"new code" and _read("lib/hero.py") == b"new hero"
        assert not os.path.exists("lib/hero.py" + ota.NEW_SUFFIX)
        assert _read("lib/hero.py" + ota.BAK_SUFFIX) == b"old hero"  # still revertible
        with open(rec.STATE_PATH) as f:
            assert json.load(f)["phase"] == "done"


def test_recover_promotes_file_cut_between_its_two_renames():
    with TempCwd():
        with open("lib/hero.py" + ota.BAK_SUFFIX, "w") as f:
            f.write("old hero")
        with open("lib/hero.py" + ota.NEW_SUFFIX, "w") as f:
            f.write("new hero")
        rec.write_state("swapping", "1.4.0", ["lib/hero.py"], then="done")
        rec.recover()
        assert _read("lib/hero.py") == b"new hero"
        assert _read("lib/hero.py" + ota.BAK_SUFFIX) == b"old hero"  # backup not clobbered


def _applied_two_files():
    for name, text in (("code.py", "old code"), ("lib/hero.py", "old hero")):
        with open(name, "w") as f:
            f.write(text)
    manifest, fake = _two_file_manifest()
    real = _patched(fake)
    try:
        ota.apply(object(), manifest)
    finally:
        _restore(real)


def test_rollback_cut_mid_swap_is_finished_by_recover():
    with TempCwd():
        _applied_two_files()
        undo = _cut_swap_after(1)
        try:
            try:
                ota.rollback()
                assert False
            except _PowerCut:
                pass
        finally:
            undo()
        with open(rec.STATE_PATH) as f:
            assert json.load(f)["phase"] == "swapping"
        rec.recover()
        assert _read("code.py") == b"old code" and _read("lib/hero.py") == b"old hero"
        with open(rec.STATE_PATH) as f:
            assert json.load(f)["phase"] == "rolled_back"


def test_rollback_staging_failure_leaves_backups_and_state_intact():
    with TempCwd():
        _applied_two_files()
        real_copy = ota._copy
        calls = [0]

        def flaky(src, dst):
            calls[0] += 1
            if calls[0] == 2:
                raise OSError("disk full")
            real_copy(src, dst)

        ota._copy = flaky
        try:
            try:
                ota.rollback()
                assert False
            except OSError:
                pass
        finally:
            ota._copy = real_copy
        assert _read("code.py") == b"new code"  # nothing live touched
        assert not os.path.exists("code.py" + ota.NEW_SUFFIX)  # staged copy cleaned up
        assert os.path.exists("code.py" + ota.BAK_SUFFIX) and os.path.exists("lib/hero.py" + ota.BAK_SUFFIX)
        with open(rec.STATE_PATH) as f:
            assert json.load(f)["phase"] == "done"
        assert sorted(ota.rollback()) == ["code.py", "lib/hero.py"]  # retry succeeds
        assert _read("code.py") == b"old code"


def test_second_rollback_is_refused():
    with TempCwd():
        _applied_two_files()
        ota.rollback()
        try:
            ota.rollback()
            assert False
        except ota.OTAError:
            pass


def test_sha256_uses_only_the_circuitpython_hashlib_api():
    # CircuitPython's hashlib has new()/update()/digest(), not sha256()/hexdigest()
    class Hash:
        def __init__(self, name):
            self._h = hashlib.new(name)

        def update(self, data):
            self._h.update(data)

        def digest(self):
            return self._h.digest()

    class CPHashlib:
        @staticmethod
        def new(name, data=b""):
            return Hash(name)

    real = ota.hashlib
    ota.hashlib = CPHashlib
    try:
        assert ota._sha256_hex(b"abc") == hashlib.sha256(b"abc").hexdigest()
        with TempCwd():
            manifest = _manifest([_entry("code.py", b"data", url="https://example.com/code.py")])
            fake = FakeGetBytes(by_url={"https://example.com/code.py": b"data"})
            r = _patched(fake)
            try:
                assert ota.apply(object(), manifest) == "1.4.0"
            finally:
                _restore(r)
    finally:
        ota.hashlib = real


def test_file_fetches_get_a_longer_budget_than_the_default():
    with TempCwd():
        manifest = _manifest([_entry("code.py", b"data", url="https://example.com/code.py")])
        fake = FakeGetBytes(by_url={"https://example.com/code.py": b"data"})
        real = _patched(fake)
        try:
            ota.apply(object(), manifest)
        finally:
            _restore(real)
        assert fake.kwargs[0]["budget"] == ota.FILE_BUDGET_S
        assert ota.FILE_BUDGET_S > httpclient.BUDGET_S


if __name__ == "__main__":
    n = 0
    for name in sorted(k for k in dir() if k.startswith("test_")):
        globals()[name]()
        print("ok", name)
        n += 1
    print("ok", n, "tests")
