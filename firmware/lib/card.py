"""Real 128x64 display renderer (issue #27; DESIGN.md sec. 9 "Display card").

Builds one displayio.Group from a card dict (firmware/code.py:poll_card()'s
shape: flight/airline/logo/route/type/city/phase/alt/spd/track/hex/age_s) or
one of the two text-only states DESIGN.md sec. 9 specs: "NO TRAFFIC" (a
successful poll, empty sky) and "NO LINK" (code.py has decided the link is
down -- see its own docstring for that policy; this module only draws
whatever it's told).

Pure rendering: no network, no hero selection, no polling. route/type/city/
phase currently always arrive "" (issue #26: nothing on-device supplies that
data yet) -- an empty field's slot is simply left blank rather than drawing
placeholder text, so the layout already looks right the day those fields
start getting populated, with no rendering change needed here.

Layout (fixed slots; DESIGN.md sec. 9's pixel-budget diagram, y is each
label's vertical centre, matching lib/setupscreen.py's convention):

    Badge (0,0, up to 48x48)   | Airline               y=7
                               | FLIGHT  ROUTE          y=21
                               | TYPE                   y=35
    city / phase (full width, x=1)                      y=50
    ALT  SPD  TRK (full width, x=1)                      y=62

Exact spacing (particularly the last two rows, squeezed into the 16px left
below a full 48px badge) is a best-effort MVP pick, not verified on hardware
-- see DESIGN.md sec. 13.3.

Badge palette handling: adafruit_imageload.load() hands back a brand new
Palette object every call (a fresh one each hero swap, via firmware/lib/
enrich.py:badge_path()), so it's registered through lib/dim.py's
Dimmer.set_palette("badge", ...), not add_palette() -- add_palette would leak
one _palettes entry per swap (DESIGN.md sec. 9's badge-palette note).
"""
import displayio
import terminalio
from adafruit_display_text import bitmap_label

import adafruit_imageload
import enrich

BADGE_SLOT = 48  # px; DESIGN.md sec. 9's badge pixel budget
TEXT_X = BADGE_SLOT + 2

COLOR_TEXT = 0xFFFFFF    # DESIGN.md sec. 9 "Colors": white text
COLOR_LABEL = 0x999999   # ... dim gray labels

Y_AIRLINE = 7
Y_FLIGHT = 21
Y_TYPE = 35
Y_CITY_PHASE = 50
Y_TELEMETRY = 62
Y_MESSAGE = 28  # "NO TRAFFIC" / "NO LINK": roughly vertical centre of the panel


def _fmt_num(v):
    return "--" if v is None else str(int(round(v)))


def _flight_line(card):
    flight = card.get("flight") or ""
    route = card.get("route")
    if route:
        return "%s  %s" % (flight, route)
    return flight


def _city_phase_line(card):
    city = card.get("city") or ""
    phase = card.get("phase") or ""
    if city and phase:
        return "%s / %s" % (city, phase)
    return city or phase


def _telemetry_line(card):
    return "%sft  %skt  %s" % (_fmt_num(card.get("alt")), _fmt_num(card.get("spd")),
                                _fmt_num(card.get("track")))


class Card:
    """Owns the card's displayio.Group and every sub-widget in it. Build one
    instance at boot (its .group is the Dimmer's awake_group), then call
    show_card()/show_message() once per poll result or link-state change --
    never rebuild the group itself, so firmware/lib/dim.py's palette
    registrations and the displayio widget tree stay stable across the
    whole run.
    """

    def __init__(self):
        self.group = displayio.Group()
        self._badge_tile = None  # current badge TileGrid, or None if hidden
        self._badge_key = None   # last loaded badge key (skip a reload if unchanged)

        self.message = self._label(4, Y_MESSAGE, COLOR_TEXT)
        self.airline = self._label(TEXT_X, Y_AIRLINE, COLOR_TEXT)
        self.flight = self._label(TEXT_X, Y_FLIGHT, COLOR_TEXT)
        self.type = self._label(TEXT_X, Y_TYPE, COLOR_LABEL)
        self.city_phase = self._label(1, Y_CITY_PHASE, COLOR_LABEL)
        self.telemetry = self._label(1, Y_TELEMETRY, COLOR_TEXT)
        for lbl in (self.message, self.airline, self.flight, self.type,
                    self.city_phase, self.telemetry):
            self.group.append(lbl)

    @staticmethod
    def _label(x, y, color):
        lbl = bitmap_label.Label(terminalio.FONT, text="", color=color)
        lbl.x = x
        lbl.y = y
        return lbl

    def _set_badge(self, key, dimmer):
        if key == self._badge_key:
            return
        self._badge_key = key
        bitmap, palette = adafruit_imageload.load(
            enrich.badge_path(key), bitmap=displayio.Bitmap, palette=displayio.Palette)
        base_colors = tuple(palette[i] for i in range(len(palette)))
        dimmer.set_palette("badge", palette, base_colors)
        if self._badge_tile is not None:
            self.group.remove(self._badge_tile)
        self._badge_tile = displayio.TileGrid(bitmap, pixel_shader=palette)
        self.group.insert(0, self._badge_tile)

    def _hide_badge(self):
        if self._badge_tile is not None:
            self.group.remove(self._badge_tile)
            self._badge_tile = None
            self._badge_key = None

    def show_card(self, card, dimmer, clock_hhmm=None):
        """card: firmware/code.py:poll_card()'s dict shape. A null flight
        (empty sky, a successful poll with no candidate) shows NO TRAFFIC
        (+ clock_hhmm, see show_message()), not a blank card."""
        if card.get("flight") is None:
            self.show_message("NO TRAFFIC", clock_hhmm)
            return
        self.message.text = ""
        self._set_badge(card.get("logo"), dimmer)
        self.airline.text = card.get("airline") or ""
        self.flight.text = _flight_line(card)
        self.type.text = card.get("type") or ""
        self.city_phase.text = _city_phase_line(card)
        self.telemetry.text = _telemetry_line(card)

    def show_message(self, text, clock_hhmm=None):
        """A full-panel text state (NO TRAFFIC / NO LINK) -- clears every
        card field and hides the badge so nothing reads as stale data.
        clock_hhmm: an already-formatted local "HH:MM" string to append
        (DESIGN.md sec. 9's "NO TRAFFIC + local time"); omit (None) when the
        clock isn't trusted yet rather than show a wrong/epoch time -- see
        firmware/lib/schedule.py:clock_trusted()."""
        self._hide_badge()
        self.airline.text = ""
        self.flight.text = ""
        self.type.text = ""
        self.city_phase.text = ""
        self.telemetry.text = ""
        self.message.text = "%s  %s" % (text, clock_hhmm) if clock_hhmm else text
