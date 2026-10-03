# Brightness by color scaling.
#
# On rgbmatrix + framebufferio, display.brightness is effectively on/off:
# 0.0 blanks the panel and any nonzero value is full on -- it is not a PWM
# dimmer. So TailWatch keeps display.brightness at 1.0 while awake (0.0 only
# for the black sleep state) and dims by scaling the RGB values it draws with.
#
# Pure Python, no displayio import: runs (and is tested) under desktop CPython.
# A palette only needs item assignment (displayio.Palette, or a list in tests).


def min_visible(bit_depth):
    """Smallest 8-bit channel value that still lights at this bit_depth.

    rgbmatrix keeps roughly the top bit_depth bits of each channel (verify on
    hardware), so a channel below 256 >> bit_depth draws as off.
    """
    return 256 >> bit_depth


def _ch(c, fraction, floor):
    if c <= 0:
        return 0
    v = int(c * fraction + 0.5)
    lo = floor if floor < c else c  # never brighten above the undimmed value
    if v < lo:
        v = lo
    return 255 if v > 255 else v


def scale_color(color, fraction, floor=0):
    """Return color dimmed to fraction (0.0-1.0) of its value.

    color is a 0xRRGGBB int or an (r, g, b) tuple; the result is the same kind.
    fraction <= 0 gives black. floor (use min_visible(bit_depth)) stops a lit
    channel from rounding down to invisible at low fractions.
    """
    is_int = isinstance(color, int)
    if is_int:
        r, g, b = (color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF
    else:
        r, g, b = color
    if fraction <= 0.0:
        r = g = b = 0
    else:
        if fraction > 1.0:
            fraction = 1.0
        r, g, b = _ch(r, fraction, floor), _ch(g, fraction, floor), _ch(b, fraction, floor)
    if is_int:
        return (r << 16) | (g << 8) | b
    return (r, g, b)


def scale_palette(palette, base_colors, fraction, floor=0):
    """Write base_colors scaled by fraction into palette, index for index.

    Always scales from base_colors (the full-brightness originals), never from
    the palette's current contents -- rescaling in place would compound.
    """
    for i, c in enumerate(base_colors):
        palette[i] = scale_color(c, fraction, floor)


class Dimmer:
    """Owns panel brightness. apply() is cheap to call often: it only touches
    the display/palettes when the fraction actually changes (or force=True).

    fraction <= 0 (sleep, or a slider at 0) is a separate full-black state:
    root_group -> blank_group and display.brightness = 0.0. Any fraction > 0
    rescales every registered palette, restores awake_group if blanked, and
    pins display.brightness at 1.0.
    """

    def __init__(self, display, awake_group, blank_group, floor=0):
        self.display = display
        self.awake_group = awake_group
        self.blank_group = blank_group
        self.floor = floor
        self.level = None  # last applied fraction; None = never applied
        self._blanked = False
        self._palettes = []
        self._slots = {}  # slot key -> index into self._palettes, for set_palette()

    def add_palette(self, palette, base_colors):
        """Register a palette to be rescaled; paints it at the current level."""
        self._palettes.append((palette, tuple(base_colors)))
        if self.level is not None:
            scale_palette(palette, base_colors, self.level, self.floor)

    def set_palette(self, slot, palette, base_colors):
        """Like add_palette(), but for a palette whose underlying object is a
        different instance each time (e.g. firmware/lib/card.py's badge,
        freshly loaded by adafruit_imageload on every hero swap): registering
        under the same `slot` key again replaces the previous entry in place
        instead of appending, so repeated swaps don't leak one _palettes
        entry per poll (DESIGN.md sec. 9's badge-palette note). Paints
        immediately at the current level rather than waiting for the next
        apply() fraction change, since a swap can happen in between."""
        base_colors = tuple(base_colors)
        if slot in self._slots:
            self._palettes[self._slots[slot]] = (palette, base_colors)
        else:
            self._slots[slot] = len(self._palettes)
            self._palettes.append((palette, base_colors))
        if self.level is not None:
            scale_palette(palette, base_colors, self.level, self.floor)

    def apply(self, fraction, force=False):
        """Apply fraction (clamped to 0.0-1.0). Returns True if anything changed."""
        fraction = float(fraction)
        if fraction < 0.0:
            fraction = 0.0
        elif fraction > 1.0:
            fraction = 1.0
        if fraction == self.level and not force:
            return False
        self.level = fraction
        if fraction <= 0.0:
            self.display.root_group = self.blank_group
            self.display.brightness = 0.0
            self._blanked = True
            return True
        for pal, base in self._palettes:
            scale_palette(pal, base, fraction, self.floor)
        if self._blanked:
            self.display.root_group = self.awake_group
            self._blanked = False
        self.display.brightness = 1.0
        return True
