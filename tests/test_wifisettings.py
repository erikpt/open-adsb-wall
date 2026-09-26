"""Host-side check for lib/wifisettings.py (settings.toml Wi-Fi writer).

Run: python3 tests/test_wifisettings.py   (needs Python 3.11+ for tomllib)
"""
import os
import sys
import tempfile
import tomllib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "firmware", "lib"))

import wifisettings as ws  # noqa: E402

TRICKY = [
    "Home",
    'My "Home" Net',
    "back\\slash\\",
    "Café ☕",
    "emoji \U0001F4F6",
    "  spaces  ",
    "#not-a-comment = [x]",
    "'single'",
]


def parse(text):
    return tomllib.loads(text)


def test_toml_str_roundtrip():
    for s in TRICKY + ["ctl\tx\x7f"]:
        doc = parse("K = " + ws.toml_str(s) + "\n")
        assert doc["K"] == s, (s, ws.toml_str(s))
    assert ws.toml_str('a"b\\c') == '"a\\"b\\\\c"'
    assert ws.toml_str("\x01") == '"\\u0001"'


def test_validate():
    ok = [("Home", "password1"), ("Home", ""), ("x" * 32, "p" * 63),
          ("Home", "0123456789abcdef" * 4), ("é" * 16, "12345678")]
    for s, p in ok:
        ws.validate(s, p)
    bad = [("", "password1"), ("x" * 33, "password1"), ("é" * 17, "password1"),
           ("a\nb", "password1"), ("Home", "short"), ("Home", "p" * 64),
           ("Home", "péssword1"), ("Home", "pass\tword"), (None, "password1"), ("Home", 12345678)]
    for s, p in bad:
        try:
            ws.validate(s, p)
        except ValueError:
            continue
        raise AssertionError("accepted %r / %r" % (s, p))


def test_from_form():
    assert ws.from_form({"ssid": "Home", "password": "password1"}) == ("Home", "password1")
    assert ws.from_form({"ssid": "Cafe", "password": "ignored!!", "open": "1"}) == ("Cafe", "")
    assert ws.from_form({"ssid": "Cafe", "open": True}) == ("Cafe", "")
    for form in ({"ssid": "Home"}, {"ssid": "Home", "password": "", "open": False},
                 {"ssid": "", "password": "password1"}, {"password": "password1"}):
        try:
            ws.from_form(form)
        except ValueError:
            continue
        raise AssertionError("accepted %r" % (form,))
    # allow-list: unrelated keys are ignored, never written anywhere
    assert ws.from_form({"ssid": "H", "password": "password1", "token": "x", "lat": 1}) == ("H", "password1")


EXISTING = (
    "# my board\r\n"
    'CIRCUITPY_WIFI_SSID = "old"\r\n'
    'CIRCUITPY_WIFI_PASSWORD = "oldpassword"\r\n'
    "\r\n"
    "CIRCUITPY_PYSTACK_SIZE = 4000\r\n"
    '"CIRCUITPY_WIFI_SSID" = "quoted-dup"\r\n'
    "\r\n\r\n"
)


def test_render():
    for s in TRICKY:
        out = ws.render(EXISTING, s, 'p"w\\d 123')
        doc = parse(out)
        assert doc["CIRCUITPY_WIFI_SSID"] == s
        assert doc["CIRCUITPY_WIFI_PASSWORD"] == 'p"w\\d 123'
        assert doc["CIRCUITPY_PYSTACK_SIZE"] == 4000
        lines = out.split("\n")
        assert lines[0].startswith("CIRCUITPY_WIFI_SSID = ")
        assert lines[1].startswith("CIRCUITPY_WIFI_PASSWORD = ")
        assert "# my board" in lines and "old" not in out and "quoted-dup" not in out
        assert out.endswith("\n") and not out.endswith("\n\n")
    # keys land before any [table] header
    out = ws.render("A = 1\n[t]\nB = 2\n", "Home", "password1")
    assert out.index("CIRCUITPY_WIFI_SSID") < out.index("[t]")
    assert parse(out)["t"]["B"] == 2
    assert parse(ws.render("", "Home", ""))["CIRCUITPY_WIFI_PASSWORD"] == ""


def test_save_and_recover():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "settings.toml")
        ws.save("First", "password1", path)  # no existing file
        assert parse(open(path, encoding="utf-8").read())["CIRCUITPY_WIFI_SSID"] == "First"
        assert not os.path.exists(path + ".new")
        ws.save("Café", "password2", path)
        assert parse(open(path, encoding="utf-8").read())["CIRCUITPY_WIFI_SSID"] == "Café"
        assert parse(open(path + ".bak", encoding="utf-8").read())["CIRCUITPY_WIFI_SSID"] == "First"
        ws.save("Third", "password3", path)  # .bak replaced, not EEXIST
        assert parse(open(path + ".bak", encoding="utf-8").read())["CIRCUITPY_WIFI_SSID"] == "Café"
        try:
            ws.save("x" * 40, "password1", path)
            raise AssertionError("bad ssid saved")
        except ValueError:
            pass
        assert parse(open(path, encoding="utf-8").read())["CIRCUITPY_WIFI_SSID"] == "Third"
        # interrupted swap: settings.toml renamed away, .new complete
        os.rename(path, path + ".new")
        assert ws.recover(path) is True
        assert parse(open(path, encoding="utf-8").read())["CIRCUITPY_WIFI_SSID"] == "Third"
        assert ws.recover(path) is False
        os.remove(path)
        assert ws.recover(path) is False  # nothing to recover


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all wifisettings tests passed")
