"""Read/write the two Wi-Fi keys in /settings.toml (AP-mode provisioning).

Only CIRCUITPY_WIFI_SSID and CIRCUITPY_WIFI_PASSWORD are ever written; every
other line (comments, other keys) is kept verbatim, after the Wi-Fi keys.
The Wi-Fi keys go FIRST so they sit before any [table] header (CircuitPython's
settings.toml reader only handles top-level key = value lines).

Pure Python (os only): runs under desktop CPython for tests/test_wifisettings.py.
Wi-Fi credentials are deliberately NOT part of the prefs schema (lib/prefs.py):
they live only in settings.toml, which CircuitPython reads at hard reset.
"""
import os

PATH = "/settings.toml"
KEYS = ("CIRCUITPY_WIFI_SSID", "CIRCUITPY_WIFI_PASSWORD")
_HEX = "0123456789abcdefABCDEF"
_TRUTHY = ("1", "true", "on", "yes")


def toml_str(s):
    """s as a TOML basic string that CircuitPython's settings.toml reader accepts.

    Escaped: backslash -> \\\\, double quote -> \\", and C0 controls / DEL ->
    \\uXXXX (validate() already rejects those; belt and braces). Everything
    else, including non-ASCII, is emitted raw: the file is written as UTF-8,
    which TOML allows in basic strings, so a "Cafe" SSID with an accent does not
    depend on the reader's \\u decoder.
    """
    out = ['"']
    for ch in s:
        o = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif o < 0x20 or o == 0x7F:
            out.append("\\u%04x" % o)
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def validate(ssid, password):
    """Raise ValueError(message for the UI) unless ssid/password are joinable."""
    if not isinstance(ssid, str) or not isinstance(password, str):
        raise ValueError("ssid and password must be strings")
    n = len(ssid.encode("utf-8"))
    if n < 1 or n > 32:
        raise ValueError("network name must be 1-32 bytes")
    for ch in ssid:
        o = ord(ch)
        if o < 0x20 or o == 0x7F:
            raise ValueError("network name contains control characters")
    if password == "":
        return  # open network
    if len(password) == 64 and all(c in _HEX for c in password):
        return  # raw 256-bit PSK as 64 hex digits
    if len(password) < 8 or len(password) > 63:
        raise ValueError("password must be 8-63 characters (or tick Open network)")
    for ch in password:
        if not 0x20 <= ord(ch) <= 0x7E:
            raise ValueError("password must be printable ASCII (WPA2 rule)")


def _truthy(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        return v.strip().lower() in _TRUTHY
    return False


def from_form(form):
    """(ssid, password) from a POSTed dict {ssid, password, open}; ValueError if bad.

    Allow-list: only these three keys are read; anything else is ignored.
    Blank password is an error unless `open` is truthy (no silent open network).
    """
    ssid = form.get("ssid", "")
    pw = form.get("password", "")
    if _truthy(form.get("open", False)):
        pw = ""
    elif pw == "":
        raise ValueError("enter the Wi-Fi password, or tick Open network")
    validate(ssid, pw)
    return ssid, pw


def _key(line):
    s = line.strip()
    if not s or s[0] in "#[" or "=" not in s:
        return None
    return s.split("=", 1)[0].strip().strip('"')


def render(existing, ssid, password):
    """New settings.toml text: Wi-Fi keys first, all other lines kept in order."""
    lines = existing.replace("\r\n", "\n").split("\n")
    kept = [ln for ln in lines if _key(ln) not in KEYS]
    while kept and kept[-1].strip() == "":
        kept.pop()
    head = [
        "CIRCUITPY_WIFI_SSID = " + toml_str(ssid),
        "CIRCUITPY_WIFI_PASSWORD = " + toml_str(password),
    ]
    return "\n".join(head + kept) + "\n"


def save(ssid, password, path=PATH):
    """Validate, then replace path via path.new -> (path -> path.bak) -> path.

    Raises ValueError (bad input) or OSError (read-only CIRCUITPY: booted with
    UP held). A power cut between the two renames leaves only path.new;
    recover() finishes the swap on the next boot.
    """
    validate(ssid, password)
    try:
        with open(path, "rb") as f:
            existing = f.read().decode("utf-8")
    except OSError:
        existing = ""  # first boot: no settings.toml yet
    data = render(existing, ssid, password).encode("utf-8")
    new = path + ".new"
    bak = path + ".bak"
    with open(new, "wb") as f:
        f.write(data)
    try:
        os.remove(bak)
    except OSError:
        pass
    try:
        os.rename(path, bak)
    except OSError:
        pass  # no existing settings.toml
    os.rename(new, path)
    try:
        os.sync()
    except (AttributeError, OSError):
        pass


def recover(path=PATH):
    """If path is missing but path.new exists (interrupted save), promote it.

    Call before the first os.getenv() of the Wi-Fi keys. Returns True if it
    renamed something. Silently does nothing on a read-only filesystem.
    """
    try:
        os.stat(path)
        return False
    except OSError:
        pass
    try:
        os.stat(path + ".new")
        os.rename(path + ".new", path)
        return True
    except OSError:
        return False
