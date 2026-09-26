"""On-device hide_heli / hide_mil / hide_ga filters (DESIGN.md sec. 10; issue #2).

Runs on the candidate dicts from lib/hero.py:candidates(), BEFORE
Hero.select(), so a filtered-out hero counts as rule (b) "gone".

Signals, strongest first:
  * OpenSky ADS-B emitter category (state vector index 17, only sent when the
    request has extended=1). Many rows carry 0/1 (no info) -- then the
    fallbacks below decide.
  * Military: bundled ICAO 24-bit address blocks (MIL_RANGES) plus a few US
    military callsign designators.
  * GA: category light/glider/ultralight/..., else a callsign that is not an
    airline-style "ABC123" flight ID (e.g. a US tail number "N123AB").

Heuristic and imperfect by design (DESIGN.md sec. 10): a helicopter with no
category reads as not-a-helicopter; the US block also holds some non-military
federal aircraft. CircuitPython-safe: no f-strings, no typing, no re.
"""
from enrich import AIRLINES, prefix

# OpenSky "category" values (REST API docs, /states/all, extended=1)
CAT_NO_INFO = 0         # no information at all
CAT_NO_ADSB_CAT = 1     # no ADS-B emitter category information
CAT_LIGHT = 2           # < 15500 lbs
CAT_SMALL = 3           # 15500 to 75000 lbs
CAT_LARGE = 4           # 75000 to 300000 lbs
CAT_HIGH_VORTEX = 5     # high vortex large (B757)
CAT_HEAVY = 6           # > 300000 lbs
CAT_HIGH_PERF = 7       # > 5g and 400 kt
CAT_ROTORCRAFT = 8      # the ONLY helicopter value
CAT_GLIDER = 9
CAT_LTA = 10            # lighter-than-air
CAT_PARACHUTIST = 11
CAT_ULTRALIGHT = 12     # ultralight / hang-glider / paraglider
CAT_UAV = 14

GA_CATS = (CAT_LIGHT, CAT_GLIDER, CAT_LTA, CAT_PARACHUTIST, CAT_ULTRALIGHT, CAT_UAV)
AIRLINER_CATS = (CAT_LARGE, CAT_HIGH_VORTEX, CAT_HEAVY)

# Military ICAO 24-bit address blocks, inclusive. Copied from readsb
# isMilRange() (github.com/wiedehopf/readsb aircraft.c, commit 3b5368a, 2026-09),
# the list tar1090/adsb.lol use for their "military" flag; ranges readsb
# disables (Slovenia, Chile) are left out for the same reason (civil aircraft
# inside them). The US block is exact: US civil N-numbers map algorithmically
# onto A00001-ADF7C7 (N99999 = ADF7C7), so everything above that in the US
# allocation (A00000-AFFFFF) is non-civil.
MIL_RANGES = (
    (0xADF7C8, 0xAFFFFF),  # United States
    (0xC20000, 0xC3FFFF),  # Canada
    (0x010070, 0x01008F),  # Egypt
    (0x0A4000, 0x0A4FFF),  # Algeria
    (0x33FF00, 0x33FFFF),  # Italy
    (0x350000, 0x37FFFF),  # Spain
    (0x3AA000, 0x3AFFFF),  # France 1
    (0x3B7000, 0x3BFFFF),  # France 2
    (0x3EA000, 0x3EBFFF),  # Germany 1
    (0x3F4000, 0x3FBFFF),  # Germany 2+3
    (0x400000, 0x40003F),  # United Kingdom 1
    (0x43C000, 0x43CFFF),  # United Kingdom 2
    (0x444000, 0x446FFF),  # Austria
    (0x44F000, 0x44FFFF),  # Belgium
    (0x457000, 0x457FFF),  # Bulgaria
    (0x45F400, 0x45F4FF),  # Denmark
    (0x468000, 0x4683FF),  # Greece
    (0x473C00, 0x473C0F),  # Hungary
    (0x478100, 0x4781FF),  # Norway
    (0x480000, 0x480FFF),  # Netherlands
    (0x48D800, 0x48D87F),  # Poland
    (0x497C00, 0x497CFF),  # Portugal
    (0x498420, 0x49842F),  # Czech Republic
    (0x4B7000, 0x4B7FFF),  # Switzerland
    (0x4B8200, 0x4B82FF),  # Turkey
    (0x70C070, 0x70C07F),  # Oman
    (0x710258, 0x71028F),  # Saudi Arabia 1-3
    (0x710380, 0x71039F),  # Saudi Arabia 4
    (0x738A00, 0x738AFF),  # Israel
    (0x7CF800, 0x7CFAFF),  # Australia
    (0x800200, 0x8002FF),  # India
    (0xE40000, 0xE41FFF),  # Brazil
)

# US DoD ICAO telephony designators: REACH (Air Mobility Command),
# CONVOY (US Navy), PAT (US Army Priority Air Transport). Backup for rows
# whose hex block is unknown; US aircraft are normally caught by MIL_RANGES.
MIL_CALLSIGNS = ("RCH", "CNV", "PAT")


def _hex_int(hx):
    try:
        return int(hx, 16)
    except (TypeError, ValueError):
        return -1


def is_heli(c):
    """True only when OpenSky says rotorcraft (category 8)."""
    return c.get("cat") == CAT_ROTORCRAFT


def is_mil(c):
    a = _hex_int(c.get("hex"))
    for lo, hi in MIL_RANGES:
        if lo <= a <= hi:
            return True
    return prefix(c.get("cs")) in MIL_CALLSIGNS


def is_ga(c):
    """General aviation: not an airline, not military, not a helicopter
    (helicopters belong to hide_heli so the two toggles stay independent)."""
    cat = c.get("cat")
    if cat == CAT_ROTORCRAFT or is_mil(c):
        return False
    p = prefix(c.get("cs"))
    if p is not None and p in AIRLINES:
        return False          # known carrier, even a Caravan feeder (cat 2)
    if cat in GA_CATS:
        return True
    if cat in AIRLINER_CATS:
        return False          # airliner-sized: unknown carrier / charter
    # cat 0/1/3/7/None: fall back to the callsign shape. Any operator-style
    # "ABC123" flight ID (charter, fractional, foreign airline not in the table)
    # is not GA; a tail number ("N123AB") or a missing callsign is.
    return p is None


def hidden(c, prefs):
    """Reason string ("heli" | "mil" | "ga") if prefs hide this candidate, else None."""
    if prefs.get("hide_heli") and is_heli(c):
        return "heli"
    if prefs.get("hide_mil") and is_mil(c):
        return "mil"
    if prefs.get("hide_ga") and is_ga(c):
        return "ga"
    return None


def apply(cands, prefs):
    """Candidates with every hidden one removed. Same list back if no filter is on."""
    if not (prefs.get("hide_heli") or prefs.get("hide_mil") or prefs.get("hide_ga")):
        return cands
    return [c for c in cands if hidden(c, prefs) is None]
