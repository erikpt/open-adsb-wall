"""mDNS/Bonjour advertisement: tailwatch-XXXX.local (issue #31).

CircuitPython's `mdns` module is core (bundled with the build, not an
Adafruit bundle library) but DESIGN.md sec. 7's original note flagged it as
uneven across boards/CircuitPython versions -- this module is entirely
best-effort as a result: a missing `mdns` module, or any failure constructing
or starting the server, is caught, logged once to serial, and leaves the
device simply unadvertised for the rest of the run. The existing fallback
(reading the IP off serial, or the brief panel "SETUP" IP text) still works
either way -- this never raises and never blocks firmware/code.py's station
Wi-Fi / web UI bring-up on mDNS being available.
"""
try:
    import mdns
except ImportError:
    mdns = None


class Advertiser:
    """One instance for the whole run, station mode only (firmware/code.py);
    same restart-on-reconnect shape as its http.server.Server (restart_http())."""

    def __init__(self, radio, hostname):
        self.radio = radio
        self.hostname = hostname
        self.server = None

    def start(self):
        """(Re)start advertising _http._tcp on port 80 at self.hostname.

        Safe to call repeatedly (e.g. on every Wi-Fi reconnect): stops any
        server already running first, so it never leaks a prior advertiser.
        Returns True once actually advertising, False if mdns isn't
        available or construction/advertise_service() raised -- callers
        print their own one-line diagnostic either way, this only cleans up.
        """
        self.stop()
        if mdns is None:
            return False
        try:
            self.server = mdns.Server(self.radio)
            self.server.hostname = self.hostname
            self.server.advertise_service(service_type="_http", protocol="_tcp", port=80)
            return True
        except Exception as e:
            print("mdns: unavailable,", e)
            self.server = None
            return False

    def stop(self):
        if self.server is not None:
            try:
                self.server.deinit()
            except Exception as e:
                print("mdns stop", e)
            self.server = None
