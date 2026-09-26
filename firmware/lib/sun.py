import math
import time

# Unix time of the J2000.0 epoch (2000-01-01 12:00:00 UTC, JD 2451545.0).
# Working in days-since-J2000 (instead of full Julian dates ~2.46e6) keeps
# the numbers small enough for CircuitPython's reduced-precision floats.
_J2000_UNIX = 946728000


def sunrise_sunset(lat, lon, ts=None):
    """Sunrise/sunset (seconds since epoch, UTC) for the solar day nearest ts.

    Standard sunrise equation. The day count since J2000 is rounded to a
    whole day (adjusted for longitude) so the result depends only on the
    date and lat/lon, not on the time of day ts falls at. The "day" rolls
    over at local solar midnight. lon is east-positive (degrees).
    """
    if ts is None:
        ts = time.time()
    lw = -lon  # west-positive longitude used by the sunrise equation
    # Whole number of days since J2000 for the local solar day containing ts.
    n = int(round((ts - _J2000_UNIX) / 86400.0 - 0.0009 - lw / 360.0))
    # Mean solar noon for that day, as a (fractional) day offset from J2000.
    j_star = n + 0.0009 + lw / 360.0
    M = (357.5291 + 0.98560028 * j_star) % 360
    Mr = math.radians(M)
    C = 1.9148 * math.sin(Mr) + 0.02 * math.sin(2 * Mr) + 0.0003 * math.sin(3 * Mr)
    lam = (M + C + 180 + 102.9372) % 360
    lamr = math.radians(lam)
    # Solar transit, split as whole days (n) + small fractional offset so the
    # final seconds value is built from an int plus a small float.
    transit_frac = 0.0009 + lw / 360.0 + 0.0053 * math.sin(Mr) - 0.0069 * math.sin(2 * lamr)
    sin_d = math.sin(lamr) * math.sin(math.radians(23.44))
    cos_d = math.cos(math.asin(sin_d))
    latr = math.radians(lat)
    w = (math.sin(math.radians(-0.83)) - math.sin(latr) * sin_d) / (math.cos(latr) * cos_d)
    w = max(-1.0, min(1.0, w))
    dt = math.degrees(math.acos(w)) / 360.0
    base = _J2000_UNIX + n * 86400
    rise = base + int(round((transit_frac - dt) * 86400.0))
    sett = base + int(round((transit_frac + dt) * 86400.0))
    return rise, sett


def is_after_sunset(lat, lon, ts=None):
    if ts is None:
        ts = time.time()
    rise, sett = sunrise_sunset(lat, lon, ts)
    # If clock is between sunset and next sunrise
    if sett <= rise:
        return ts >= sett or ts < rise
    # typical: rise < now? handle wrap by comparing to today's rise/set
    if ts >= sett:
        return True
    if ts < rise:
        return True
    return False
