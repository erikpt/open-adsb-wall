"""Bad Apple!! easter egg (issue #30): plays firmware/lib/badapple_frames.py's
embedded clip on the panel. Second easter egg alongside lib/nyan.py's Nyan
Cat (hold DOWN 5s) -- this one triggers on hold UP 5s (lib/buttons.py).

Frame data is run-length encoded per row, concatenated for the whole frame
with no row separators (see tools/gen_badapple.py's docstring for why that's
safe): decode_frame() below is the one place that scheme gets unpacked, and
it is plain Python with no displayio dependency, so tests/test_badapple.py
can exercise it on desktop CPython against small synthetic fixtures instead
of the real (large) embedded clip.

Unlike lib/nyan.py's play() (a single blocking while-loop), Player is
cooperative: tick(now) advances at most one frame per call and must be
called once per firmware/code.py main-loop iteration while self.active, so
the HTTP server and ADS-B poll keep running between frames -- issue #30 is
explicit that this egg must not add a second, multi-second stall to a loop
whose other long-running things (OpenSky, NTP, Wi-Fi reconnect) already
budget themselves around DESIGN.md sec. 9's "never block the UI server for
more than one poll" rule.
"""
import displayio

from badapple_frames import WIDTH, HEIGHT, FPS, FRAMES

OFF = 0x000000
ON = 0xFFFFFF


def decode_frame(rle, width=WIDTH, height=HEIGHT, bitmap=None):
    """RLE bytes -> a displayio.Bitmap (2-color: 0 off, 1 on).

    Reuses `bitmap` in place when given (the steady-state playback path:
    one bitmap object for the whole clip, not one allocation per frame).
    Decodes row by row; a row's runs always sum to exactly `width` (by
    construction -- see tools/gen_badapple.py), so a row boundary is just
    "the running total hit width", no separators to track.
    """
    if bitmap is None:
        bitmap = displayio.Bitmap(width, height, 2)
    row = 0
    col = 0
    color = 0
    for run in rle:
        for _ in range(run):
            bitmap[col, row] = color
            col += 1
        color ^= 1
        if col >= width:
            col = 0
            row += 1
            color = 0
    return bitmap


class Player:
    """One instance for the whole run (firmware/code.py), same shape as
    lib/hero.py:Hero / lib/cycle.py:Cycle: call start() to begin, then
    tick(now) once per main-loop iteration until it returns False."""

    def __init__(self, brightness=0.5, fps=FPS, frames=FRAMES):
        self.brightness = brightness
        self.frame_dt = 1.0 / fps
        self.frames = frames
        self.active = False
        self._bitmap = None
        self._root = None
        self._display = None
        self._prev_group = None
        self._prev_brightness = None
        self._manual_refresh = False
        self._i = 0
        self._last = None

    def start(self, display):
        """Begin playback from frame 0 on `display`, saving its current
        root_group/brightness to restore when the clip ends or stop() is
        called. Builds the bitmap/palette/group once and reuses them across
        every start() (no repeated allocation on a repeat trigger)."""
        if self._bitmap is None:
            self._bitmap = displayio.Bitmap(WIDTH, HEIGHT, 2)
            palette = displayio.Palette(2)
            palette[0] = OFF
            palette[1] = ON
            tg = displayio.TileGrid(self._bitmap, pixel_shader=palette)
            self._root = displayio.Group()
            self._root.append(tg)

        self._display = display
        self._prev_group = display.root_group
        self._prev_brightness = display.brightness
        self._manual_refresh = not display.auto_refresh

        display.brightness = self.brightness
        display.root_group = self._root

        self._i = 0
        self._last = None
        self.active = True

    def stop(self):
        """Restore the caller's display state (clip end, or an early/manual
        stop e.g. a repeat trigger). Safe to call when not active."""
        if self.active:
            self._display.root_group = self._prev_group
            self._display.brightness = self._prev_brightness
        self.active = False

    def tick(self, now):
        """Call once per main-loop iteration while self.active. Decodes at
        most one new frame, paced by fps (not every call); stops/restores
        the display on its own once the clip ends. Returns self.active, so
        callers can write `while egg.tick(now): ...` -- or, since it's only
        ever called once per loop iteration here, just check it afterward."""
        if not self.active:
            return False
        due = self._last is None or now - self._last >= self.frame_dt
        if due:
            self._last = now
            decode_frame(self.frames[self._i], bitmap=self._bitmap)
            if self._manual_refresh:
                self._display.refresh(minimum_frames_per_second=0)
            self._i += 1
            if self._i >= len(self.frames):
                self.stop()
        return self.active
