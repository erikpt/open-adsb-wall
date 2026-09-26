"""Local wall-clock time for schedule windows (sleep / fixed night hours).

LIMITATION -- this is NOT a timezone database. CircuitPython has no IANA
tz data, so local time is computed as:
    UTC + tz_offset_min (fixed STANDARD-time offset, minutes, east-positive)
        + 60 min when us_dst is true and the fixed US rule says DST is on.
Fixed US rule (in force since 2007), and nothing else:
    starts 02:00 local standard time on the 2nd Sunday of March
    ends   02:00 local daylight time (= 01:00 standard) on the 1st Sunday of November
Historic US rules, EU/AU/other DST schemes and zone changes are NOT modelled.
Outside the US: set us_dst false and adjust tz_offset_min by hand at clock
changes. Arizona / Hawaii: us_dst false.

The RTC stays on UTC (code.py: NTP with tz_offset=0) and sun.py works in UTC
epoch seconds; only schedule.py's clock-window comparisons use this module.
"""
import time

_DAY = 86400


def _days_from_civil(y, m, d):
    """Days since 1970-01-01 for a Gregorian date (H. Hinnant's algorithm)."""
    if m <= 2:
        y -= 1
    era = y // 400
    yoe = y - era * 400
    doy = (153 * (m - 3 if m > 2 else m + 9) + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def _year_of(days):
    """Calendar year containing `days` (days since 1970-01-01)."""
    y = 1970 + days // 365  # never too small; step back at most once or twice
    while _days_from_civil(y, 1, 1) > days:
        y -= 1
    return y


def _nth_sunday(y, m, n):
    """Day number (since 1970-01-01) of the n-th Sunday of month m in year y."""
    first = _days_from_civil(y, m, 1)
    # (days + 3) % 7 gives Mon=0..Sun=6; 1970-01-01 was a Thursday.
    return first + (6 - (first + 3) % 7) % 7 + 7 * (n - 1)


def us_dst_active(std_local_s):
    """True if US DST is in effect. std_local_s = UTC epoch s + standard offset."""
    y = _year_of(std_local_s // _DAY)
    start = _nth_sunday(y, 3, 2) * _DAY + 2 * 3600   # 02:00 std, 2nd Sun Mar
    end = _nth_sunday(y, 11, 1) * _DAY + 1 * 3600    # 02:00 DST = 01:00 std, 1st Sun Nov
    return start <= std_local_s < end


def utc_offset_min(tz_offset_min, us_dst, ts=None):
    """Effective UTC offset in minutes at UTC epoch time ts (default: now)."""
    if ts is None:
        ts = time.time()
    off = int(tz_offset_min)
    if us_dst and us_dst_active(int(ts) + off * 60):
        off += 60
    return off


def local_minutes(tz_offset_min, us_dst, ts=None):
    """Minutes past local midnight (0..1439) at UTC epoch time ts (default: now)."""
    if ts is None:
        ts = time.time()
    local = int(ts) + utc_offset_min(tz_offset_min, us_dst, ts) * 60
    return (local % _DAY) // 60
