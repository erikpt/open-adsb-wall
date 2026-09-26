# Nyan Cat easter egg.
# Plays on the caller's existing display (never creates its own RGBMatrix --
# a device only has one) and restores whatever was showing before it ran.

import time
import random
import displayio

SWAP_RB = False
FLIP_RAINBOW = True


def _rgb(c):
    if not SWAP_RB:
        return c
    r = (c >> 16) & 0xFF
    g = (c >> 8) & 0xFF
    b = c & 0xFF
    return (b << 16) | (g << 8) | r


# 0 empty 1 black 2 gray 3 white 4 frosting 5 crust 6 sprinkle 7 cheek
_PALETTE_COLORS = (
    0x000000, 0x000000, 0x999999, 0xFFFFFF, 0xFF99FF, 0xFFCC99,
    0xFF3399, 0xFF9999, 0xFF0000, 0xFF7900, 0xF2D000, 0x2DB800,
    0x0086E0, 0x6A28FF, 0x8AA0B8, 0x3A3A3A,
)

W, H = 64, 32

# Exact 34x21 grid sampled from the source PNG.
CAT0 = [
    [0,0,0,0,0,0,0,0,0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0,0,0,0,0,0,0,0],
    [0,0,0,0,0,0,0,0,1,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,1,0,0,0,0,0,0,0],
    [0,0,0,0,0,0,0,1,5,5,5,4,4,4,4,4,4,4,4,4,4,4,4,4,5,5,5,1,0,0,0,0,0,0],
    [0,0,0,0,0,0,0,1,5,5,4,4,4,4,4,4,6,4,4,6,4,4,4,4,4,5,5,1,0,0,0,0,0,0],
    [0,0,0,0,0,0,0,1,5,4,4,6,4,4,4,4,4,4,4,4,4,4,4,4,4,4,5,1,0,0,0,0,0,0],
    [0,0,0,0,0,0,0,1,5,4,4,4,4,4,4,4,4,4,4,1,1,4,4,6,4,4,5,1,0,1,1,0,0,0],
    [0,0,0,0,0,0,0,1,5,4,4,4,4,4,4,4,4,4,1,2,2,1,4,4,4,4,5,1,1,2,2,1,0,0],
    [0,1,1,1,1,0,0,1,5,4,4,4,4,4,4,6,4,4,1,2,2,2,1,4,4,4,5,1,2,2,2,1,0,0],
    [0,1,2,2,1,1,0,1,5,4,4,4,4,4,4,4,4,4,1,2,2,2,2,1,1,1,1,2,2,2,2,1,0,0],
    [0,1,1,2,2,1,1,1,5,4,4,4,6,4,4,4,4,4,1,2,2,2,2,2,2,2,2,2,2,2,2,1,0,0],
    [0,0,1,1,2,2,1,1,5,4,4,4,4,4,4,4,6,1,2,2,2,2,2,2,2,2,2,2,2,2,2,2,1,0],
    [0,0,0,1,1,2,2,1,5,4,6,4,4,4,4,4,4,1,2,2,2,3,1,2,2,2,2,2,3,1,2,2,1,0],
    [0,0,0,0,1,1,1,1,5,4,4,4,4,4,4,4,4,1,2,2,2,1,1,2,2,2,1,2,1,1,2,2,1,0],
    [0,0,0,0,0,0,1,1,5,4,4,4,4,4,6,4,4,1,2,7,7,2,2,2,2,2,2,2,2,2,7,7,1,0],
    [0,0,0,0,0,0,0,1,5,5,4,6,4,4,4,4,4,1,2,7,7,2,1,2,2,1,2,2,1,2,7,7,1,0],
    [0,0,0,0,0,0,0,1,5,5,5,4,4,4,4,4,4,4,1,2,2,2,1,1,1,1,1,1,1,2,2,1,0,0],
    [0,0,0,0,0,0,1,1,1,5,5,5,5,5,5,5,5,5,5,1,2,2,2,2,2,2,2,2,2,2,1,0,0,0],
    [0,0,0,0,0,1,2,2,2,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0,0,0,0],
    [0,0,0,0,0,1,2,2,1,1,0,1,2,2,1,0,0,0,0,0,1,2,2,1,0,1,2,2,1,0,0,0,0,0],
    [0,0,0,0,0,1,2,2,1,0,0,1,2,2,1,0,0,0,0,0,1,2,2,1,0,1,2,2,1,0,0,0,0,0],
    [0,0,0,0,0,1,1,1,0,0,0,1,1,1,0,0,0,0,0,0,1,1,1,0,0,1,1,1,0,0,0,0,0,0],
]
CAT1 = [row[:] for row in CAT0]
CAT1[18] = [0,0,0,0,1,2,2,1,0,0,0,0,1,2,2,1,0,0,0,0,0,1,2,2,1,0,0,1,2,2,1,0,0,0]
CAT1[19] = [0,0,0,0,1,2,2,1,0,0,0,0,1,2,2,1,0,0,0,0,0,1,2,2,1,0,0,1,2,2,1,0,0,0]
CAT1[20] = [0,0,0,0,1,1,1,0,0,0,0,0,1,1,1,0,0,0,0,0,0,1,1,1,0,0,0,1,1,1,0,0,0,0]

CAT = [CAT0, CAT1]
CH = len(CAT0)
CW = len(CAT0[0])
CAT_X = 26

RAINBOW = (8, 9, 10, 11, 12, 13)
if FLIP_RAINBOW:
    RAINBOW = tuple(reversed(RAINBOW))

STAR_FRAMES = (
    ((0, 0),),
    ((0, -1), (0, 1), (-1, 0), (1, 0)),
    ((0, -2), (0, 2), (-2, 0), (2, 0)),
    ((0, -1), (0, 1), (-1, 0), (1, 0)),
    ((0, 0),),
    (),
)

WAVE = (0, 1, 1, 0, -1, -1)
BOB = (0, 1, 1, 0, -1, -1)
TART_LEFT = CAT_X + 8

# Packed (dx, dy, color) per frame so the draw loop skips empty cells.
_SPR = []
for _fr in CAT:
    _pts = []
    for _row in range(CH):
        _line = _fr[_row]
        for _col in range(CW):
            _c = _line[_col]
            if _c:
                _pts.append((_col, _row, _c))
    _SPR.append(_pts)


def play(display, duration_s=90.0, brightness=0.25, frame_dt=0.07, should_stop=None):
    """Play the Nyan Cat animation on an already-initialized display.

    Swaps in its own bitmap/root_group, runs for up to duration_s seconds
    (default 90s), then restores whatever root_group/brightness the caller
    had before this ran. Pass should_stop as a zero-arg callable (e.g.
    lambda: up_button.pressed() or down_button.pressed()) to return early --
    checked once per frame, not polled faster than that. Blocks the caller
    the whole time it runs (same single-loop model as the rest of this
    CircuitPython firmware -- there is no threading).
    """
    palette = displayio.Palette(16)
    for i, c in enumerate(_PALETTE_COLORS):
        palette[i] = _rgb(c)

    bitmap = displayio.Bitmap(W, H, 16)
    tg = displayio.TileGrid(bitmap, pixel_shader=palette)
    root = displayio.Group(scale=2)
    root.append(tg)

    prev_group = display.root_group
    prev_brightness = display.brightness
    manual_refresh = not display.auto_refresh

    display.brightness = brightness
    display.root_group = root

    stars = [[random.randrange(W), random.randrange(H), random.randrange(6)] for _ in range(10)]

    frame = 0
    start = time.monotonic()
    last = start
    try:
        while time.monotonic() - start < duration_s:
            if should_stop is not None and should_stop():
                break
            now = time.monotonic()
            if now - last < frame_dt:
                continue
            last = now
            bitmap.fill(0)

            for s in stars:
                s[0] -= 1
                if s[0] < -2:
                    s[0] = W + 1
                    s[1] = random.randrange(H)
                s[2] = (s[2] + 1) % 6
                sx, sy, sf = s[0], s[1], s[2]
                for dx, dy in STAR_FRAMES[sf]:
                    x = sx + dx
                    y = sy + dy
                    if 0 <= x < W and 0 <= y < H:
                        bitmap[x, y] = 14

            cy = 5 + BOB[frame % 6]
            rainbow_y = cy + 8
            for x in range(TART_LEFT):
                wave = WAVE[(x // 3 + frame) % 6]
                base = rainbow_y + wave
                for i, color in enumerate(RAINBOW):
                    y = base + i
                    if 0 <= y < H:
                        bitmap[x, y] = color

            for col, row, c in _SPR[frame & 1]:
                bitmap[CAT_X + col, cy + row] = c

            if manual_refresh:
                display.refresh(minimum_frames_per_second=0)
            frame += 1
    finally:
        display.root_group = prev_group
        display.brightness = prev_brightness
