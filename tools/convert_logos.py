"""Convert real airline logo artwork into lib/logos/<key>.bmp (issue #18).

Host-only build tool (desktop python3, run manually); NOT copied to CIRCUITPY.
Sibling of tools/gen_badges.py, which generates non-trademarked letter-mark
badges from lib/enrich.py:AIRLINES for every airline. This script instead
converts a *real* sourced logo image (SVG or raster, saved under
tools/logo_sources/) for the airlines the project owner sourced one for.
Issue #18: the project owner has explicitly decided, for this personal,
non-commercial build, not to pursue trademark clearance -- see DESIGN.md's
badge section for that decision and gen_badges.py's docstring for the
fallback contract this script depends on.

Needs Pillow (`pip install Pillow`) for resizing/quantizing, and cairosvg
(`pip install cairosvg`, needs system libcairo) to rasterize .svg sources --
gen_badges.py deliberately avoids both since it only draws pixel art by
hand, but real-image conversion legitimately needs an imaging library. Only
this tool imports them; code.py and lib/*.py never do.

  python3 tools/convert_logos.py --dir tools/logo_sources        # convert everything sourced
  python3 tools/convert_logos.py aal tools/logo_sources/aal.svg  # convert one
  python3 tools/convert_logos.py --dir tools/logo_sources --dry-run

Output format
-------------
Same BMP container as gen_badges.py (BITMAPINFOHEADER, BI_RGB, bottom-up,
4-bit indexed -- see gen_badges.bmp4(), reused here), so the on-device loader
(adafruit_imageload.load() / displayio.OnDiskBitmap) needs no changes. Two
differences from a letter-mark badge:

  - Size: fit to the logo's own aspect ratio, longest side <= MAX_DIM (48,
    the layout budget in DESIGN.md sec. 9), not forced square. A wordmark-
    shaped logo (e.g. a wide "FedEx" glyph) ends up short and wide; card.py
    centers whatever it gets in the badge slot.
  - Palette: STEPS colors (default 8) interpolated from black (index 0) to
    an accent color (index STEPS-1), one per antialiasing level, instead of
    the letter-mark's fixed 3 colors. This is what actually saves these
    logos: naive 1-bit/3-color thresholding turns thin strokes (a wordmark's
    serifs, a crane's wingtip) into broken pixels or nothing at all; keeping
    ~8 gray^H^H^Hbrand-color steps of the source antialiasing lets a mostly-
    single-color logo mark survive the downscale to 30-50px looking like a
    logo instead of a blob. lib/dim.py's scale_palette() doesn't care how
    long a palette is -- it rescales every entry by the same fraction -- so
    this is a drop-in extension of the same night-dimming scheme the letter
    marks use, just with more steps.

Where the accent color comes from: lib/enrich.py:AIRLINES's existing color
(picked to be "distinct and legible on the LED panel", per that module's
docstring), NOT the source image's own colors -- pass --accent to override.
Several real brand colors are far too dark to read against the panel's black
background (UPS's own brand brown is near-black, for instance); AIRLINES's
curated color reads correctly and keeps the look consistent with airlines
that are still on the letter-mark fallback.

Two conversion modes (--mode, default: auto-detected from the source's own
extension/content):

  silhouette (used for every logo actually sourced so far -- see
  tools/logo_sources/*.svg, all from the CC0-licensed Simple Icons project,
  a single-color brand glyph): the source's alpha channel *is* the shape.
  Crop to its bounding box, downscale with Lanczos resampling (keeps
  antialiasing instead of hard-thresholding it away), quantize the
  remaining alpha into STEPS levels, each level a lerp(black, accent).

  photo (best-effort, for a raster logo that carries its own real colors --
  no such source is committed yet, so treat this path as less exercised):
  flatten transparency onto black, then Pillow-quantize the RGB to STEPS
  colors (median-cut), with a forced pure-black entry for anything that was
  fully transparent. Multi-color source logos with fine detail may still
  need per-image tuning (crop/contrast) this generic pass doesn't attempt.

Fallback contract (do not break this): an airline this script has not
produced a badge for keeps using tools/gen_badges.py's generated letter-mark
-- that script already exists and is unmodified in what it draws. This
script's only integration point is tools/logo_sources/sources.json, a
manifest {icao_lower: source_filename} that convert_logos.py appends to and
gen_badges.py reads (real_logo_keys()) so a plain re-run of gen_badges.py
does not overwrite or prune a real logo's .bmp. Real logos always win when
present: lib/enrich.py:badge_path() is a direct "lib/logos/<key>.bmp" path
lookup with no separate resolution step, so whichever tool last wrote that
path is what loads -- this script must run *after* gen_badges.py if both are
re-run, which is why gen_badges.py consults the manifest rather than the
other way around.
"""
import io
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
FIRMWARE = os.path.join(ROOT, "firmware")
sys.path.insert(0, os.path.join(FIRMWARE, "lib"))
sys.path.insert(0, HERE)

from enrich import AIRLINES  # noqa: E402
import gen_badges  # noqa: E402  (reuses bmp4() -- identical BMP container)

try:
    from PIL import Image
except ImportError:
    sys.exit("convert_logos.py needs Pillow: pip install Pillow")

SOURCES_DIR = os.path.join(HERE, "logo_sources")
SOURCES_MANIFEST = os.path.join(SOURCES_DIR, "sources.json")
LOGOS_DIR = os.path.join(FIRMWARE, "lib", "logos")

MAX_DIM = 48        # DESIGN.md sec. 9 badge slot budget
STEPS = 8           # palette entries: black .. accent, must stay <= 16 (4-bit)
SUPERSAMPLE = 8     # rasterize this many px per output px before downscaling
SVG_EXTS = (".svg",)
RASTER_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")


def _lerp_color(c0, c1, t):
    r0, g0, b0 = (c0 >> 16) & 0xFF, (c0 >> 8) & 0xFF, c0 & 0xFF
    r1, g1, b1 = (c1 >> 16) & 0xFF, (c1 >> 8) & 0xFF, c1 & 0xFF
    r = round(r0 + (r1 - r0) * t)
    g = round(g0 + (g1 - g0) * t)
    b = round(b0 + (b1 - b0) * t)
    return (r << 16) | (g << 8) | b


def _load_rgba(path, ss_size):
    """Return an RGBA image, SVG rasterized at ss_size x ss_size (supersampled
    square canvas; non-square art still gets correct proportions since we crop
    to content bbox before ever resizing to the real, non-square, target)."""
    ext = os.path.splitext(path)[1].lower()
    if ext in SVG_EXTS:
        import cairosvg  # only needed for this branch
        png_bytes = cairosvg.svg2png(url=path, output_width=ss_size, output_height=ss_size)
        return Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    im = Image.open(path).convert("RGBA")
    # upscale a small raster source so the same crop/resize path has room to
    # antialias down from, matching the SVG branch's supersampling
    if max(im.size) < ss_size:
        scale = ss_size / max(im.size)
        im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    return im


def convert_silhouette(path, accent, max_dim=MAX_DIM, steps=STEPS):
    """Alpha-channel shape, tinted black->accent. See module docstring."""
    im = _load_rgba(path, max_dim * SUPERSAMPLE)
    alpha = im.split()[3]
    bbox = alpha.getbbox()
    if bbox is None:
        raise ValueError("source has no visible (non-transparent) pixels: " + path)
    cropped = alpha.crop(bbox)
    cw, ch = cropped.size
    scale = max_dim / max(cw, ch)
    tw, th = max(1, round(cw * scale)), max(1, round(ch * scale))
    small = cropped.resize((tw, th), Image.LANCZOS)
    colors = [_lerp_color(0x000000, accent, i / (steps - 1)) for i in range(steps)]
    grid = []
    for y in range(th):
        row = []
        for x in range(tw):
            v = small.getpixel((x, y)) / 255.0
            row.append(round(v * (steps - 1)))
        grid.append(row)
    return grid, colors


def convert_photo(path, max_dim=MAX_DIM, steps=STEPS):
    """Best-effort multi-color path: flatten onto black, then median-cut
    quantize. Less exercised than convert_silhouette (see module docstring)
    -- no committed source has needed it yet."""
    im = _load_rgba(path, max_dim * SUPERSAMPLE)
    bbox = im.split()[3].getbbox() or (0, 0, im.width, im.height)
    cropped = im.crop(bbox)
    cw, ch = cropped.size
    scale = max_dim / max(cw, ch)
    tw, th = max(1, round(cw * scale)), max(1, round(ch * scale))
    small = cropped.resize((tw, th), Image.LANCZOS)
    flat = Image.new("RGB", small.size, (0, 0, 0))
    flat.paste(small, mask=small.split()[3])
    # reserve index 0 for pure black, quantize the rest
    quant = flat.quantize(colors=max(1, steps - 1), method=Image.MEDIANCUT)
    pal = quant.getpalette()[: (steps - 1) * 3]
    colors = [0x000000] + [
        (pal[i * 3] << 16) | (pal[i * 3 + 1] << 8) | pal[i * 3 + 2] for i in range(steps - 1)
    ]
    src_alpha = small.split()[3]
    grid = []
    for y in range(th):
        row = []
        for x in range(tw):
            if src_alpha.getpixel((x, y)) < 8:
                row.append(0)
            else:
                row.append(quant.getpixel((x, y)) + 1)
        grid.append(row)
    return grid, colors


def detect_mode(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in SVG_EXTS:
        return "silhouette"
    if ext in RASTER_EXTS:
        return "photo"
    raise ValueError("unrecognized source extension: " + path)


def convert(icao, path, mode=None, accent=None, max_dim=MAX_DIM, steps=None):
    icao = icao.upper()
    steps = steps or STEPS
    if accent is None:
        if icao not in AIRLINES:
            raise KeyError("not in lib/enrich.py:AIRLINES: " + icao)
        accent = AIRLINES[icao][2]
    mode = mode or detect_mode(path)
    if mode == "silhouette":
        grid, colors = convert_silhouette(path, accent, max_dim, steps)
    elif mode == "photo":
        grid, colors = convert_photo(path, max_dim, steps)
    else:
        raise ValueError("mode must be 'silhouette' or 'photo': " + mode)
    data = gen_badges.bmp4(grid, colors)
    w, h = len(grid[0]), len(grid)
    return data, w, h


def _load_manifest():
    try:
        with open(SOURCES_MANIFEST) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def manifest_entry(value):
    """A manifest value is either a bare filename (str, the common case: mode
    auto-detects from its extension, steps is the default), or a dict
    {"file": ..., "mode": ..., "steps": ...} for a source that needs a
    non-default conversion (e.g. a multi-color .svg that must be forced into
    "photo" mode, or a gradient-heavy source that washes out at the default
    STEPS). Returns (filename, mode_or_None, steps_or_None)."""
    if isinstance(value, dict):
        return value["file"], value.get("mode"), value.get("steps")
    return value, None, None


def _save_manifest(manifest):
    with open(SOURCES_MANIFEST, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")


def _sourced_files(directory):
    """(icao, path) pairs for every AIRLINES-matching file in directory."""
    out = []
    for name in sorted(os.listdir(directory)):
        key, ext = os.path.splitext(name)
        if key.upper() in AIRLINES and ext.lower() in SVG_EXTS + RASTER_EXTS:
            out.append((key.lower(), os.path.join(directory, name)))
    return out


def run(jobs, out_dir=LOGOS_DIR, dry_run=False, mode=None, accent=None, steps=None):
    """jobs: [(icao_lower, source_path), ...]. Returns manifest updates made.

    mode/steps here are an explicit override for this whole call (the CLI's
    --mode/--steps flags apply to every job in it). When not given (the usual
    --dir batch case), each job falls back to whatever override its manifest
    entry already recorded from a previous single-file run -- see
    manifest_entry() -- so a plain re-run reproduces every file, including
    ones that need non-default settings, without repeating the flags.
    """
    if not dry_run and not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    manifest = _load_manifest()
    total = 0
    for icao, path in jobs:
        _prev_file, prev_mode, prev_steps = manifest_entry(manifest.get(icao, path))
        job_mode = mode if mode is not None else prev_mode
        job_steps = steps if steps is not None else prev_steps
        data, w, h = convert(icao, path, mode=job_mode, accent=accent, steps=job_steps)
        total += len(data)
        verb = "would write" if dry_run else "wrote"
        print("%s %s.bmp  %dx%d  %d bytes  <- %s" % (verb, icao, w, h, len(data), path))
        if not dry_run:
            with open(os.path.join(out_dir, icao + ".bmp"), "wb") as f:
                f.write(data)
            basename = os.path.basename(path)
            if job_mode not in (None, detect_mode(path)) or (job_steps and job_steps != STEPS):
                manifest[icao] = {"file": basename, "mode": job_mode, "steps": job_steps}
            else:
                manifest[icao] = basename
    if not dry_run and jobs:
        _save_manifest(manifest)
    print(("would total " if dry_run else "total: ") + "%d bytes, %d logo(s)" % (total, len(jobs)))
    return manifest


def main(argv):
    dry_run = "--dry-run" in argv
    argv = [a for a in argv if a != "--dry-run"]
    mode = None
    if "--mode" in argv:
        i = argv.index("--mode")
        mode = argv[i + 1]
        del argv[i : i + 2]
    accent = None
    if "--accent" in argv:
        i = argv.index("--accent")
        accent = int(argv[i + 1], 16)
        del argv[i : i + 2]
    steps = None
    if "--steps" in argv:
        i = argv.index("--steps")
        steps = int(argv[i + 1])
        if not (2 <= steps <= 16):
            sys.exit("--steps must be 2..16 (4-bit indexed BMP)")
        del argv[i : i + 2]

    if "--dir" in argv:
        i = argv.index("--dir")
        directory = argv[i + 1]
        jobs = _sourced_files(directory)
        if not jobs:
            sys.exit("no AIRLINES-matching source files in " + directory)
    elif len(argv) == 2:
        jobs = [(argv[0].lower(), argv[1])]
    else:
        sys.exit("usage: convert_logos.py ICAO SOURCE_IMAGE | --dir SOURCES_DIR "
                  "[--mode silhouette|photo] [--accent RRGGBB] [--steps N] [--dry-run]")

    run(jobs, dry_run=dry_run, mode=mode, accent=accent, steps=steps)


if __name__ == "__main__":
    main(sys.argv[1:])
