"""Generate lib/logos/*.bmp letter-mark badges from lib/enrich.py:AIRLINES.

Host-only build tool (desktop python3, stdlib only -- no Pillow needed); NOT
copied to CIRCUITPY. Output is committed so deploying is just copying lib/.

  python3 tools/gen_badges.py            # (re)write lib/logos/
  python3 tools/gen_badges.py OUT_DIR    # write elsewhere (tests use this)

Each badge: 24x24, 4-bit indexed BMP (BITMAPINFOHEADER, BI_RGB, bottom-up,
3-entry palette), 354 bytes. Palette index 0 = black (rounded corners),
1 = tile background, 2 = mark color. The mark (IATA code, else ICAO) is drawn
with a baked-in 3x5 pixel font scaled 2x (6x10 glyphs, 2 px gap), centered.
Loadable with adafruit_imageload.load() or displayio.OnDiskBitmap; the
3-color palette is what lib/dim.py rescales for night mode.
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "lib"))

from enrich import AIRLINES, UNKNOWN_KEY  # noqa: E402

SIZE = 24          # badge is SIZE x SIZE px
SCALE = 2          # 3x5 font drawn at 2x -> 6x10 glyphs
GAP = 2            # px between glyphs (after scaling)
UNKNOWN_BG = 0x505A64
BLACK = 0x000000
WHITE = 0xFFFFFF

# 3x5 font: 5 rows per glyph, each row 3 chars ('#' = on).
FONT = {
    "A": (".#.", "#.#", "###", "#.#", "#.#"),
    "B": ("##.", "#.#", "##.", "#.#", "##."),
    "C": (".##", "#..", "#..", "#..", ".##"),
    "D": ("##.", "#.#", "#.#", "#.#", "##."),
    "E": ("###", "#..", "##.", "#..", "###"),
    "F": ("###", "#..", "##.", "#..", "#.."),
    "G": (".##", "#..", "#.#", "#.#", ".##"),
    "H": ("#.#", "#.#", "###", "#.#", "#.#"),
    "I": ("###", ".#.", ".#.", ".#.", "###"),
    "J": ("..#", "..#", "..#", "#.#", ".#."),
    "K": ("#.#", "#.#", "##.", "#.#", "#.#"),
    "L": ("#..", "#..", "#..", "#..", "###"),
    "M": ("#.#", "###", "###", "#.#", "#.#"),
    "N": ("##.", "#.#", "#.#", "#.#", "#.#"),
    "O": (".#.", "#.#", "#.#", "#.#", ".#."),
    "P": ("##.", "#.#", "##.", "#..", "#.."),
    "Q": (".#.", "#.#", "#.#", "##.", ".##"),
    "R": ("##.", "#.#", "##.", "#.#", "#.#"),
    "S": (".##", "#..", ".#.", "..#", "##."),
    "T": ("###", ".#.", ".#.", ".#.", ".#."),
    "U": ("#.#", "#.#", "#.#", "#.#", "###"),
    "V": ("#.#", "#.#", "#.#", "#.#", ".#."),
    "W": ("#.#", "#.#", "###", "###", "#.#"),
    "X": ("#.#", "#.#", ".#.", "#.#", "#.#"),
    "Y": ("#.#", "#.#", ".#.", ".#.", ".#."),
    "Z": ("###", "..#", ".#.", "#..", "###"),
    "0": ("###", "#.#", "#.#", "#.#", "###"),
    "1": (".#.", "##.", ".#.", ".#.", "###"),
    "2": ("##.", "..#", ".#.", "#..", "###"),
    "3": ("##.", "..#", ".#.", "..#", "##."),
    "4": ("#.#", "#.#", "###", "..#", "..#"),
    "5": ("###", "#..", "##.", "..#", "##."),
    "6": (".##", "#..", "###", "#.#", "###"),
    "7": ("###", "..#", ".#.", ".#.", ".#."),
    "8": ("###", "#.#", "###", "#.#", "###"),
    "9": ("###", "#.#", "###", "..#", "##."),
}

# Fallback badge glyph (top-view airplane), 16x16, drawn 1:1 centered.
PLANE = (
    ".......##.......",
    "......####......",
    "......####......",
    "......####......",
    ".....######.....",
    "...##########...",
    ".##############.",
    "################",
    "##....####....##",
    "......####......",
    "......####......",
    ".......##.......",
    ".....######.....",
    "....########....",
    "....##....##....",
    "................",
)


def text_color(bg):
    """Black mark on light tiles, white on dark (ITU-R 601 luma)."""
    r, g, b = (bg >> 16) & 0xFF, (bg >> 8) & 0xFF, bg & 0xFF
    return BLACK if (299 * r + 587 * g + 114 * b) // 1000 > 150 else WHITE


def blank_tile():
    px = [[1] * SIZE for _ in range(SIZE)]
    # round the 4 corners: 3 px each set to palette index 0 (black / unlit)
    for x, y in ((0, 0), (1, 0), (0, 1)):
        for cx, cy in ((x, y), (SIZE - 1 - x, y), (x, SIZE - 1 - y), (SIZE - 1 - x, SIZE - 1 - y)):
            px[cy][cx] = 0
    return px


def stamp(px, rows, x0, y0, scale):
    for gy, row in enumerate(rows):
        for gx, ch in enumerate(row):
            if ch != "#":
                continue
            for dy in range(scale):
                for dx in range(scale):
                    px[y0 + gy * scale + dy][x0 + gx * scale + dx] = 2


def mark_pixels(mark):
    mark = mark.upper()
    if not 2 <= len(mark) <= 3:
        raise ValueError("mark must be 2-3 chars: %r" % mark)
    gw, gh = 3 * SCALE, 5 * SCALE
    w = len(mark) * gw + (len(mark) - 1) * GAP
    x = (SIZE - w) // 2
    y = (SIZE - gh) // 2
    px = blank_tile()
    for ch in mark:
        if ch not in FONT:
            raise ValueError("no glyph for %r in %r" % (ch, mark))
        stamp(px, FONT[ch], x, y, SCALE)
        x += gw + GAP
    return px


def plane_pixels():
    px = blank_tile()
    off = (SIZE - len(PLANE)) // 2
    stamp(px, PLANE, off, off, 1)
    return px


def bmp4(px, colors):
    """px: SIZE rows (top first) of palette indices; colors: list of 0xRRGGBB."""
    h = len(px)
    w = len(px[0])
    row_bytes = ((w * 4 + 31) // 32) * 4           # 4-bit rows, padded to 4 bytes
    pal = b"".join(struct.pack("<BBBB", c & 0xFF, (c >> 8) & 0xFF, (c >> 16) & 0xFF, 0)
                   for c in colors)
    data_off = 14 + 40 + len(pal)
    img = bytearray()
    for y in range(h - 1, -1, -1):                 # BMP rows are bottom-up
        row = bytearray(row_bytes)
        for x in range(w):
            if x & 1:
                row[x >> 1] |= px[y][x]
            else:
                row[x >> 1] |= px[y][x] << 4        # high nibble = left pixel
        img += row
    file_hdr = struct.pack("<2sIHHI", b"BM", data_off + len(img), 0, 0, data_off)
    dib = struct.pack("<IiiHHIIiiII", 40, w, h, 1, 4, 0, len(img),
                      2835, 2835, len(colors), len(colors))
    return file_hdr + dib + pal + bytes(img)


def badges():
    """Yield (filename, bytes) for every badge, fallback last."""
    for icao in sorted(AIRLINES):
        _name, mark, bg = AIRLINES[icao]
        yield icao.lower() + ".bmp", bmp4(mark_pixels(mark), [BLACK, bg, text_color(bg)])
    yield UNKNOWN_KEY + ".bmp", bmp4(plane_pixels(), [BLACK, UNKNOWN_BG, WHITE])


def main(out_dir):
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    keep = set()
    total = 0
    for name, data in badges():
        with open(os.path.join(out_dir, name), "wb") as f:
            f.write(data)
        keep.add(name)
        total += len(data)
    for name in os.listdir(out_dir):       # drop badges for removed airlines
        if name.endswith(".bmp") and name not in keep:
            os.remove(os.path.join(out_dir, name))
    print("wrote %d badges, %d bytes -> %s" % (len(keep), total, out_dir))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "lib", "logos"))
