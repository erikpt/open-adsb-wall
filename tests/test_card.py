"""Host-side checks for lib/card.py (issue #27): layout helpers, blank-not-
placeholder empty fields, NO TRAFFIC / NO LINK states, and that the badge
palette goes through lib/dim.py:Dimmer.set_palette() (no _palettes leak
across hero swaps, no stale-pixel flash at the wrong brightness).

Run: python3 tests/test_card.py
"""
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "..", "firmware", "lib")
sys.path.insert(0, LIB)


def _mod(name, **kw):
    x = types.ModuleType(name)
    for k, v in kw.items():
        setattr(x, k, v)
    sys.modules[name] = x
    return x


class Bitmap:
    def __init__(self, w, h, n):
        self.w, self.h, self.n = w, h, n


class Palette(list):
    def __init__(self, n):
        super().__init__([0] * n)


class Group(list):
    pass


_mod("displayio", Bitmap=Bitmap, Palette=Palette, Group=Group,
     TileGrid=lambda bitmap, pixel_shader: types.SimpleNamespace(
         bitmap=bitmap, pixel_shader=pixel_shader))
_mod("terminalio", FONT=object())


class Label:
    def __init__(self, font, text="", color=0):
        self.font = font
        self.text = text
        self.color = color
        self.x = 0
        self.y = 0


bitmap_label_mod = _mod("adafruit_display_text.bitmap_label", Label=Label)
_mod("adafruit_display_text", bitmap_label=bitmap_label_mod)

LOAD_CALLS = []


def _imageload_load(path, bitmap=None, palette=None):
    LOAD_CALLS.append(path)
    bmp = Bitmap(2, 2, 2)
    pal = Palette(2)
    pal[0], pal[1] = 0x000000, 0xAABBCC
    return bmp, pal


_mod("adafruit_imageload", load=_imageload_load)

import card  # noqa: E402
from dim import Dimmer, min_visible  # noqa: E402


class Display:
    def __init__(self, group):
        self.root_group = group
        self.brightness = 1.0


def make():
    c = card.Card()
    d = Display(c.group)
    dimmer = Dimmer(d, c.group, Group(), floor=min_visible(4))
    dimmer.apply(1.0)
    LOAD_CALLS.clear()
    return c, dimmer


FULL_CARD = {
    "flight": "UAL123", "airline": "United", "logo": "ual",
    "route": "PDX-LAX", "type": "737 MAX 9", "city": "Portland Intl",
    "phase": "arriving", "alt": 11200.0, "spd": 342.0, "track": 175,
    "hex": "abc123", "age_s": 8,
}


def test_full_card_renders_every_field():
    c, dimmer = make()
    c.show_card(FULL_CARD, dimmer)
    assert c.message.text == ""
    assert c.airline.text == "United"
    assert c.flight.text == "UAL123  PDX-LAX"
    assert c.type.text == "737 MAX 9"
    assert c.city_phase.text == "Portland Intl / arriving"
    assert c.telemetry.text == "11200ft  342kt  175"
    assert c._badge_tile is not None
    assert LOAD_CALLS == [card.enrich.badge_path("ual")]


def test_empty_optional_fields_are_blank_not_placeholder():
    c, dimmer = make()
    bare = dict(FULL_CARD, route="", type="", city="", phase="")
    c.show_card(bare, dimmer)
    assert c.flight.text == "UAL123"       # no stray "  " for a missing route
    assert c.type.text == ""
    assert c.city_phase.text == ""
    assert "None" not in c.flight.text + c.type.text + c.city_phase.text


def test_city_or_phase_alone_shows_without_separator():
    c, dimmer = make()
    c.show_card(dict(FULL_CARD, phase=""), dimmer)
    assert c.city_phase.text == "Portland Intl"
    c.show_card(dict(FULL_CARD, city=""), dimmer)
    assert c.city_phase.text == "arriving"


def test_telemetry_none_values_show_dashes():
    c, dimmer = make()
    c.show_card(dict(FULL_CARD, alt=None, spd=None, track=None), dimmer)
    assert c.telemetry.text == "--ft  --kt  --"


def test_null_flight_is_no_traffic_not_a_blank_card():
    c, dimmer = make()
    c.show_card(FULL_CARD, dimmer)  # populate first, to prove it gets cleared
    c.show_card({"flight": None, "airline": "", "logo": None, "route": "",
                 "type": "", "city": "", "phase": "", "alt": None, "spd": None,
                 "track": None, "hex": None, "age_s": None}, dimmer)
    assert c.message.text == "NO TRAFFIC"
    assert c.flight.text == "" and c.airline.text == "" and c.telemetry.text == ""
    assert c._badge_tile is None and c._badge_key is None


def test_no_traffic_appends_local_time_when_given():
    c, dimmer = make()
    no_traffic = dict(flight=None, airline="", logo=None, route="", type="",
                       city="", phase="", alt=None, spd=None, track=None,
                       hex=None, age_s=None)
    c.show_card(no_traffic, dimmer, clock_hhmm="14:32")
    assert c.message.text == "NO TRAFFIC  14:32"
    c.show_card(no_traffic, dimmer, clock_hhmm=None)  # untrusted clock: omitted, not "None"
    assert c.message.text == "NO TRAFFIC"


def test_show_message_clears_fields_and_hides_badge():
    c, dimmer = make()
    c.show_card(FULL_CARD, dimmer)
    assert c._badge_tile is not None
    c.show_message("NO LINK")
    assert c.message.text == "NO LINK"
    assert c.flight.text == "" and c.city_phase.text == "" and c.telemetry.text == ""
    assert c._badge_tile is None and c._badge_key is None
    assert c._badge_tile not in c.group


def test_unchanged_badge_key_skips_reload():
    c, dimmer = make()
    c.show_card(FULL_CARD, dimmer)
    c.show_card(dict(FULL_CARD, flight="UAL456"), dimmer)  # same airline/logo
    assert LOAD_CALLS == [card.enrich.badge_path("ual")]  # loaded once, not twice


def test_badge_swap_uses_set_palette_no_leak():
    """Two different airlines in a row must not grow Dimmer._palettes --
    DESIGN.md sec. 9's badge-palette note; see also
    tests/test_dim.py:test_set_palette_replaces_in_place_no_leak."""
    c, dimmer = make()
    c.show_card(FULL_CARD, dimmer)
    assert len(dimmer._palettes) == 1
    c.show_card(dict(FULL_CARD, logo="dal", airline="Delta"), dimmer)
    assert len(dimmer._palettes) == 1
    assert LOAD_CALLS == [card.enrich.badge_path("ual"), card.enrich.badge_path("dal")]


def test_badge_painted_at_current_dimmer_level_immediately():
    from dim import scale_color
    c, dimmer = make()
    dimmer.apply(0.5, force=True)
    c.show_card(FULL_CARD, dimmer)
    # pal[1] is 0xAABBCC in the fake loader; scaled to 0.5 it must not still
    # read as the raw, undimmed colour.
    pal = dimmer._palettes[dimmer._slots["badge"]][0]
    assert pal[1] == scale_color(0xAABBCC, 0.5, dimmer.floor)


if __name__ == "__main__":
    n = 0
    for name in sorted(k for k in dir() if k.startswith("test_")):
        globals()[name]()
        print("ok", name)
        n += 1
    print("ok", n, "tests")
