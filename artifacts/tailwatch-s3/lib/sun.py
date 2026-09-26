import math
import time


def _julian(ts):
    return ts / 86400.0 + 2440587.5


def sunrise_sunset(lat, lon, ts=None):
    """Approximate local sunrise/sunset as seconds since epoch (UTC)."""
    if ts is None:
        ts = time.time()
    jd = _julian(ts)
    n = jd - 2451545.0 + 0.0008
    J = n - lon / 360.0
    M = (357.5291 + 0.98560028 * J) % 360
    Mr = math.radians(M)
    C = 1.9148 * math.sin(Mr) + 0.02 * math.sin(2 * Mr) + 0.0003 * math.sin(3 * Mr)
    lam = (M + C + 180 + 102.9372) % 360
    Jtransit = 2451545.0 + J + 0.0053 * math.sin(Mr) - 0.0069 * math.sin(2 * math.radians(lam))
    sin_d = math.sin(math.radians(lam)) * math.sin(math.radians(23.44))
    cos_d = math.cos(math.asin(sin_d))
    latr = math.radians(lat)
    w = (math.sin(math.radians(-0.83)) - math.sin(latr) * sin_d) / (math.cos(latr) * cos_d)
    w = max(-1.0, min(1.0, w))
    dt = math.degrees(math.acos(w)) / 360.0
    rise = (Jtransit - dt - 2440587.5) * 86400.0
    sett = (Jtransit + dt - 2440587.5) * 86400.0
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
