"""Host-side checks for tools/gen_ota_manifest.py (issue #29): the manifest it
emits for the real firmware/ tree passes the device's own validation, hashes
match the files on disk, and nothing the device's allow-list refuses (boot.py,
ota_recover.py, settings, prefs) ever sneaks in.

Run: python3 tests/test_gen_ota_manifest.py
"""
import hashlib
import importlib.util
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FIRMWARE = os.path.join(HERE, "..", "firmware")
spec = importlib.util.spec_from_file_location("gen_ota_manifest", os.path.join(HERE, "..", "tools", "gen_ota_manifest.py"))
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

BASE = "https://example.com/tailwatch/1.0.0"


def test_real_tree_manifest_passes_the_devices_own_validation():
    m = gen.build(BASE, gen.collect())
    gen.ota.parse_manifest(json.dumps(m))
    assert m["version"] == gen.VERSION
    paths = [f["path"] for f in m["files"]]
    assert "code.py" in paths and "lib/hero.py" in paths and "www/index.html" in paths
    assert "lib/badapple_frames.py" in paths and "lib/version.py" in paths


def test_hashes_sizes_and_urls_match_the_files():
    for f in gen.build(BASE, gen.collect())["files"]:
        with open(os.path.join(FIRMWARE, f["path"]), "rb") as fh:
            data = fh.read()
        assert f["sha256"] == hashlib.sha256(data).hexdigest(), f["path"]
        assert f["size"] == len(data), f["path"]
        assert f["url"] == BASE + "/" + f["path"], f["url"]


def test_never_includes_what_the_device_refuses_to_replace():
    paths = set(f["path"] for f in gen.build(BASE, gen.collect())["files"])
    for forbidden in ("boot.py", "ota_recover.py", "settings.toml.example", "prefs.example.json"):
        assert forbidden not in paths, forbidden
    assert not any(p.endswith(".pyc") or "__pycache__" in p for p in paths)


def test_version_py_is_always_included_even_when_filtered_out():
    m = gen.build(BASE, ["lib/hero.py"])
    assert [f["path"] for f in m["files"]] == ["lib/hero.py", "lib/version.py"]


def test_trailing_slash_in_base_url_does_not_double_up():
    m = gen.build(BASE + "/", ["code.py"])
    assert "//code.py" not in m["files"][0]["url"].split("://", 1)[1]


def test_non_https_base_url_is_refused():
    try:
        gen.build("http://example.com/x", ["code.py"])
        assert False
    except ValueError:
        pass


def test_oversize_manifest_is_refused_with_advice():
    real = gen.ota.MAX_MANIFEST_SIZE
    gen.ota.MAX_MANIFEST_SIZE = 500
    try:
        try:
            gen.build(BASE, gen.collect())
            assert False
        except ValueError as e:
            assert "--since" in str(e)
    finally:
        gen.ota.MAX_MANIFEST_SIZE = real


def test_file_over_the_per_file_cap_is_refused():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "lib"))
        for name, size in (("version.py", 10), ("big.py", gen.ota.MAX_FILE_SIZE + 1)):
            with open(os.path.join(d, "lib", name), "wb") as f:
                f.write(b"x" * size)
        try:
            gen.build(BASE, ["lib/big.py"], firmware=d)
            assert False
        except gen.ota.OTAError:
            pass


if __name__ == "__main__":
    n = 0
    for name in sorted(k for k in dir() if k.startswith("test_")):
        globals()[name]()
        print("ok", name)
        n += 1
    print("ok", n, "tests")
