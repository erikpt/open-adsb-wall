"""Host-side checks for lib/enrich.py, lib/filters.py and lib/logos/.

Run: python3 tests/test_enrich_filters.py
Optional: pip install --no-deps adafruit-circuitpython-imageload  (then the
badges are also decoded with the real on-device loader).
"""
import os
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "firmware", "lib"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import convert_logos  # noqa: E402
import enrich  # noqa: E402
import filters  # noqa: E402
import gen_badges  # noqa: E402
from enrich import AIRLINES, UNKNOWN_KEY, badge_path, lookup, prefix  # noqa: E402
from filters import MIL_RANGES, apply, hidden, is_ga, is_heli, is_mil  # noqa: E402
from hero import candidates  # noqa: E402

LOGOS = os.path.join(ROOT, "firmware", "lib", "logos")
SOURCES = os.path.join(ROOT, "tools", "logo_sources")
ALL_ON = {"hide_heli": True, "hide_mil": True, "hide_ga": True}


def c(hx="a1b2c3", cs="", cat=None):
    return {"hex": hx, "cs": cs, "lat": 0.0, "lon": 0.0, "dist": 1.0,
            "alt": 1000.0, "spd": 100.0, "trk": 0.0, "cat": cat, "age": 0}


def test_prefix_lookup():
    assert prefix("SWA1234 ") == "SWA" and prefix("ual2") == "UAL"
    for bad in (None, "", "N123AB", "N1", "SWA", "CGABC", "XAABC", "12345", "AB1234"):
        assert prefix(bad) is None, bad
    assert lookup("AAL100") == ("American", "aal")
    assert lookup("  fdx3421") == ("FedEx", "fdx")
    assert lookup("ZZZ123") is None and lookup("N123AB") is None and lookup(None) is None
    assert badge_path("swa") == "/lib/logos/swa.bmp"
    assert badge_path(None) == "/lib/logos/_unk.bmp" == badge_path("zzz")


def test_table():
    assert 30 <= len(AIRLINES) <= 60, len(AIRLINES)
    marks = set()
    for icao, row in AIRLINES.items():
        name, mark, bg = row
        assert len(icao) == 3 and icao.isalpha() and icao.isupper(), icao
        assert 0 < len(name) <= 16, name
        assert 2 <= len(mark) <= 3 and all(ch in gen_badges.FONT for ch in mark), mark
        assert 0 <= bg <= 0xFFFFFF, icao
        assert mark not in marks, "duplicate mark " + mark
        marks.add(mark)


def test_heli():
    assert is_heli(c(cat=8))
    for cat in (None, 0, 1, 2, 3, 4, 5, 6, 7, 9, 14):
        assert not is_heli(c(cat=cat)), cat
    assert hidden(c(cat=8), {"hide_heli": True}) == "heli"
    assert hidden(c(cat=8), {"hide_heli": False}) is None


def test_mil():
    for lo, hi in MIL_RANGES:
        assert lo <= hi
        assert is_mil(c(hx="%06x" % lo)) and is_mil(c(hx="%06X" % hi))
    assert is_mil(c(hx="ae1234")) and is_mil(c(hx="adf7c8"))
    assert not is_mil(c(hx="adf7c7"))     # N99999, last US civil address
    assert not is_mil(c(hx="a00001"))     # N1
    assert not is_mil(c(hx="c0cdf8"))     # Canadian civil
    assert is_mil(c(hx="a12345", cs="RCH821"))
    assert not is_mil(c(hx="", cs="")) and not is_mil(c(hx="zzz"))


def test_ga():
    assert is_ga(c(cs="N123AB", cat=2))
    assert is_ga(c(cs="N123AB", cat=0))          # no category: tail-number callsign
    assert is_ga(c(cs="", cat=None))             # no callsign, no category
    assert is_ga(c(cs="ZZZ12", cat=9))           # glider category wins over shape
    assert not is_ga(c(cs="FDX1234", cat=2))     # FedEx Caravan feeder: airline
    assert not is_ga(c(cs="SWA12", cat=None))
    assert not is_ga(c(cs="N123AB", cat=4))      # large aircraft
    assert not is_ga(c(cs="XYZ123", cat=3))      # operator-coded charter/biz jet
    assert not is_ga(c(cs="N911LF", cat=8))      # helicopter -> hide_heli's job
    assert not is_ga(c(hx="ae0001", cs="", cat=0))  # military -> hide_mil's job


def test_apply_with_hero_candidates():
    def row(hx, cs, cat):
        return [hx, cs, "United States", 1000, 1000, -95.75, 30.21, 1000.0, False,
                100.0, 90.0, 0.0, None, 1000.0, "1200", False, 0, cat]
    resp = {"time": 1000, "states": [
        row("a1b2c3", "SWA1234 ", 4),
        row("a2b2c3", "N123AB  ", 2),
        row("a3b2c3", "N911LF  ", 8),
        row("ae0001", "RCH821  ", 6),
    ]}
    cands = candidates(resp, 30.21, -95.75)
    assert [x["cat"] for x in cands] == [4, 2, 8, 6]
    assert apply(cands, {}) is cands
    assert [x["cs"] for x in apply(cands, ALL_ON)] == ["SWA1234"]
    assert [x["cs"] for x in apply(cands, {"hide_heli": True, "hide_mil": True})] \
        == ["SWA1234", "N123AB"]
    assert [x["cs"] for x in apply(cands, {"hide_ga": True})] == ["SWA1234", "N911LF", "RCH821"]


def _parse_bmp(data, expect=None):
    """expect: optional (w, h, used) to assert exactly (letter-mark badges);
    omitted for a real logo, whose size/palette length vary per source."""
    magic, fsize, _r1, _r2, off = struct.unpack_from("<2sIHHI", data, 0)
    hdr, w, h, planes, bpp, comp, isize, _xr, _yr, used, _imp = \
        struct.unpack_from("<IiiHHIIiiII", data, 14)
    assert magic == b"BM" and fsize == len(data) and hdr == 40 and planes == 1
    assert bpp == 4 and comp == 0, (bpp, comp)          # 4-bit indexed, uncompressed
    if expect is not None:
        assert (w, h, used) == expect, (w, h, used)
    row_bytes = ((w * 4 + 31) // 32) * 4
    assert off == 14 + 40 + 4 * used and isize == row_bytes * h == len(data) - off
    pal = [struct.unpack_from("<BBBB", data, 54 + 4 * i) for i in range(used)]
    return w, h, [(r << 16) | (g << 8) | b for b, g, r, _ in pal]


def test_badges_committed_and_current():
    """lib/logos/*.bmp: letter-mark fallbacks match tools/gen_badges.py byte
    for byte; real logos (issue #18: tools/convert_logos.py) are checked
    structurally instead, since their size/palette differ per source image,
    but still exactly reproducible from their committed source."""
    real = gen_badges.real_logo_keys()
    want = dict(gen_badges.badges(skip=real))
    all_names = set(k.lower() + ".bmp" for k in AIRLINES) | {UNKNOWN_KEY + ".bmp"}
    real_names = set(k + ".bmp" for k in real)
    assert real_names <= all_names, real_names - all_names
    assert set(want) == all_names - real_names
    on_disk = sorted(n for n in os.listdir(LOGOS) if n.endswith(".bmp"))
    assert on_disk == sorted(set(want) | real_names), \
        "lib/logos out of date: run python3 tools/gen_badges.py / tools/convert_logos.py"

    total = 0
    for name, data in want.items():
        with open(os.path.join(LOGOS, name), "rb") as f:
            got = f.read()
        assert got == data, name + " stale: run python3 tools/gen_badges.py"
        _w, _h, pal = _parse_bmp(got, expect=(24, 24, 3))
        assert pal[0] == 0x000000
        if name != UNKNOWN_KEY + ".bmp":
            assert pal[1] == AIRLINES[name[:-4].upper()][2]
        total += len(got)

    # real logos: reproducible from tools/logo_sources/, small indexed palette,
    # within the sec. 9 48x48 badge-slot budget
    manifest = convert_logos._load_manifest()
    assert set(manifest) == real, (manifest, real)
    for icao, src_name in manifest.items():
        assert icao.upper() in AIRLINES, icao
        src_path = os.path.join(SOURCES, src_name)
        assert os.path.isfile(src_path), src_path
        with open(os.path.join(LOGOS, icao + ".bmp"), "rb") as f:
            got = f.read()
        data, w, h = convert_logos.convert(icao, src_path)
        assert got == data, icao + ".bmp stale: run python3 tools/convert_logos.py --dir tools/logo_sources"
        pw, ph, pal = _parse_bmp(got)
        assert (pw, ph) == (w, h)
        assert 1 <= pw <= 48 and 1 <= ph <= 48, (icao, pw, ph)
        assert 2 <= len(pal) <= 16, (icao, len(pal))    # 4-bit indexed ceiling
        assert pal[0] == 0x000000, (icao, pal[0])       # index 0 always black
        # silhouette mode (single-color glyph) tints black->AIRLINES accent, so
        # its last palette entry is that accent exactly; photo mode (a raster
        # logo with its own real brand colors, issue #18's 34-carrier batch)
        # keeps the source's own colors instead -- see convert_logos.py's
        # docstring for why. Only assert the accent match for the mode it
        # actually applies to.
        if convert_logos.detect_mode(src_path) == "silhouette":
            assert pal[-1] == AIRLINES[icao.upper()][2], (icao, pal[-1])
        total += len(got)

    assert total < 64 * 1024, total
    # generator into a temp dir also works (and prunes stray files, but leaves
    # real logos' filenames alone even though it doesn't write them there)
    tmp = tempfile.mkdtemp()
    open(os.path.join(tmp, "old.bmp"), "wb").close()
    gen_badges.main(tmp)
    assert sorted(os.listdir(tmp)) == sorted(want)


def test_badges_decode_with_imageload():
    # imageload's type aliases import displayio at import time; stub it on desktop
    if "displayio" not in sys.modules:
        import types
        stub = types.ModuleType("displayio")
        stub.Bitmap = stub.Palette = stub.ColorConverter = object
        sys.modules["displayio"] = stub
    try:
        import adafruit_imageload
    except ImportError:
        print("  (adafruit_imageload not installed; skipped real-loader decode)")
        return

    class Bmp:
        def __init__(self, w, h, n):
            self.w, self.h, self.n = w, h, n
            self.px = [0] * (w * h)

        def __setitem__(self, i, v):
            self.px[i] = v

    class Pal:
        def __init__(self, n):
            self.c = [None] * n

        def __setitem__(self, i, v):
            self.c[i] = (v[0] << 16) | (v[1] << 8) | v[2]

    real = gen_badges.real_logo_keys()
    for icao, (_n, mark, bg) in AIRLINES.items():
        if icao.lower() in real:
            continue   # real logo: different size/palette, checked below
        with open(os.path.join(LOGOS, icao.lower() + ".bmp"), "rb") as f:
            bmp, pal = adafruit_imageload.load(f, bitmap=Bmp, palette=Pal)
        assert (bmp.w, bmp.h, bmp.n) == (24, 24, 3)
        assert pal.c == [0, bg, gen_badges.text_color(bg)], (icao, pal.c)
        assert bmp.px[0] == 0 and bmp.px[24 * 12] == 1   # corner black, left edge bg
        assert bmp.px == [v for row in gen_badges.mark_pixels(mark) for v in row], icao

    # real logos (issue #18): same loader, just a variable size/palette length
    manifest = convert_logos._load_manifest()
    for icao in real:
        with open(os.path.join(LOGOS, icao + ".bmp"), "rb") as f:
            bmp, pal = adafruit_imageload.load(f, bitmap=Bmp, palette=Pal)
        assert bmp.w <= 48 and bmp.h <= 48 and bmp.n == len(pal.c)
        assert pal.c[0] == 0, icao
        # see test_badges_committed_and_current: only silhouette mode tints
        # its last palette entry to the AIRLINES accent -- photo mode keeps
        # the source's own colors.
        src_path = os.path.join(SOURCES, manifest[icao])
        if convert_logos.detect_mode(src_path) == "silhouette":
            assert pal.c[-1] == AIRLINES[icao.upper()][2], icao
        assert len(bmp.px) == bmp.w * bmp.h


if __name__ == "__main__":
    for name in sorted(k for k in dir() if k.startswith("test_")):
        globals()[name]()
        print("ok", name)
    print("enrich/filters/logos: all passed")
