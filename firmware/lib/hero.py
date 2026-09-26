"""Hero-aircraft selection with hysteresis (on-device; see issue #2).

Each poll turns an OpenSky /states/all bbox response into a small list of
candidate dicts (candidates()), then Hero.select() decides which ONE aircraft
the card shows. The shown aircraft is held across polls and only replaced when:

  (a) CLOSER  -- another candidate is meaningfully closer: at least
                 SWITCH_RATIO (20 %) closer AND at least MIN_GAP_MI closer,
                 and the current hero has been shown >= MIN_DWELL_S;
  (b) GONE    -- the hero's hex is absent from the latest successful response
                 (left the bbox, landed/on_ground, filtered, out of coverage);
  (c) STALE   -- the hero's position is older than max_stale_s, either in the
                 data (response time - time_position) or on the device clock
                 (no successful poll has confirmed it for max_stale_s; see
                 expired()).

Distances are statute miles, matching lib/bbox.py (69 mi/deg) and the prefs
"nm" field, which DESIGN.md sec. 6 defines as miles each way.
CircuitPython-safe: only math, no f-strings, no typing.
"""
import math

MI_PER_DEG = 69.0     # same constant as lib/bbox.py
SWITCH_RATIO = 0.20   # (a) challenger must be >= 20 % closer than the hero ...
MIN_GAP_MI = 0.5      # ... and >= 0.5 mi closer in absolute terms
MIN_DWELL_S = 30      # (a) only: a new hero stays up >= 30 s before a "closer" swap

# OpenSky state-vector indices (REST API docs, /states/all)
_ICAO24 = 0
_CALLSIGN = 1
_TIME_POS = 3
_LAST_CONTACT = 4
_LON = 5
_LAT = 6
_BARO_ALT = 7
_ON_GROUND = 8
_VELOCITY = 9
_TRACK = 10
_GEO_ALT = 13
_CATEGORY = 17  # only present with ?extended=1


def stale_limit(poll_s):
    """max_stale_s for a poll interval: 3 polls, clamped to 30..90 s."""
    return min(90, max(30, 3 * poll_s))


def distance_mi(lat0, lon0, lat, lon):
    """Equirectangular distance in statute miles; < 0.1 % error inside 50 mi."""
    dy = (lat - lat0) * MI_PER_DEG
    dx = (lon - lon0) * MI_PER_DEG * math.cos(math.radians((lat + lat0) * 0.5))
    return math.sqrt(dx * dx + dy * dy)


def candidates(resp, lat0, lon0):
    """OpenSky JSON dict -> list of candidate dicts (airborne, with a position).

    Each dict: hex (lowercase icao24), cs (callsign or ""), lat, lon,
    dist (mi from the pin), alt (m, baro then geo, or None), spd (m/s or None),
    trk (deg or None), cat (int or None), age (s since position fix, >= 0).
    """
    out = []
    if not resp:
        return out
    states = resp.get("states") or ()
    t_resp = resp.get("time")
    for s in states:
        try:
            if s[_ON_GROUND]:
                continue
            lat = s[_LAT]
            lon = s[_LON]
            if lat is None or lon is None:
                continue
            ts = s[_TIME_POS]
            if ts is None:
                ts = s[_LAST_CONTACT]
            age = 0
            if t_resp is not None and ts is not None:
                age = max(0, t_resp - ts)
            alt = s[_BARO_ALT]
            if alt is None:
                alt = s[_GEO_ALT]
            out.append({
                "hex": (s[_ICAO24] or "").strip().lower(),
                "cs": (s[_CALLSIGN] or "").strip(),
                "lat": lat,
                "lon": lon,
                "dist": distance_mi(lat0, lon0, lat, lon),
                "alt": alt,
                "spd": s[_VELOCITY],
                "trk": s[_TRACK],
                "cat": s[_CATEGORY] if len(s) > _CATEGORY else None,
                "age": age,
            })
        except (IndexError, TypeError, ValueError):
            continue  # malformed row: skip it, never kill the poll
    return out


def _rank(c):
    # DESIGN.md sec. 8: closest to pin; tie-break lower altitude, then faster.
    alt = c["alt"]
    spd = c["spd"]
    return (c["dist"], 1e9 if alt is None else alt, -(spd or 0))


def select(current_hex, cands, held_s=0, max_stale_s=45):
    """Pure hysteresis rule. Returns (candidate_dict_or_None, reason).

    current_hex: hex shown now, or None.
    cands: list from candidates().
    held_s: seconds the current hero has been shown (for MIN_DWELL_S).
    reason: "none" | "new" | "keep" | "dwell" | "closer" | "gone" | "stale".
    """
    fresh = [c for c in cands if c["age"] <= max_stale_s and c["hex"]]
    best = min(fresh, key=_rank) if fresh else None

    if current_hex is None:
        return best, ("new" if best else "none")

    cur = None
    for c in fresh:
        if c["hex"] == current_hex:
            cur = c
            break
    if cur is None:  # (b) gone, or (c) stale in the data
        why = "gone"
        for c in cands:
            if c["hex"] == current_hex:
                why = "stale"
                break
        return best, why

    if best["hex"] == current_hex:
        return cur, "keep"
    gap = cur["dist"] - best["dist"]
    if best["dist"] <= cur["dist"] * (1.0 - SWITCH_RATIO) and gap >= MIN_GAP_MI:
        if held_s < MIN_DWELL_S:
            return cur, "dwell"
        return best, "closer"  # (a)
    return cur, "keep"


class Hero:
    """Holds the shown aircraft across polls. One module-level instance in code.py."""

    def __init__(self, poll_s=15):
        self.max_stale_s = stale_limit(poll_s)
        self.clear()

    def clear(self):
        self.hex = None
        self.card = None   # last chosen candidate dict (for the renderer)
        self.since = 0.0   # monotonic time this hex became hero
        self.seen = 0.0    # monotonic time of last successful poll that kept it

    def select(self, cands, now):
        """Call once per SUCCESSFUL poll. Returns (candidate_or_None, reason)."""
        held = now - self.since if self.hex else 0
        c, why = select(self.hex, cands, held, self.max_stale_s)
        if c is None:
            self.clear()
        else:
            if c["hex"] != self.hex:
                self.hex = c["hex"]
                self.since = now
            self.card = c
            self.seen = now
        return c, why

    def expired(self, now):
        """(c) on the device clock: True when a hero is held but no successful
        poll has confirmed it for max_stale_s (e.g. repeated fetch failures)."""
        return self.hex is not None and now - self.seen > self.max_stale_s
