"""Percent-decoding for application/x-www-form-urlencoded values.

CircuitPython has no urllib; adafruit_httpserver's FormData/QueryParams split
on '&'/'=' but leave values percent-encoded, so decode them here.
"""

_HEX = b"0123456789abcdefABCDEF"


def unquote_plus(s):
    """'+' -> space, %XX -> byte, then UTF-8 decode. Malformed escapes pass through."""
    if not isinstance(s, str):
        return s
    if "%" not in s and "+" not in s:
        return s
    b = s.replace("+", " ").encode("utf-8")
    n = len(b)
    out = bytearray()
    i = 0
    while i < n:
        c = b[i]
        if c == 0x25 and i + 2 < n and b[i + 1] in _HEX and b[i + 2] in _HEX:
            out.append(int(bytes(b[i + 1 : i + 3]).decode(), 16))
            i += 3
            continue
        out.append(c)
        i += 1
    try:
        return bytes(out).decode("utf-8")
    except UnicodeError:
        return s
