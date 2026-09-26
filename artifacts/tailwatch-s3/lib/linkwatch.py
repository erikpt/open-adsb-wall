"""Station-mode Wi-Fi watchdog for code.py: notice a dropped link, re-join
with a bounded number of attempts, and tell code.py when to restart the web
UI server (link back / IP changed) or give up and hard reset.

CircuitPython does not reliably re-join after a drop (router reboot, AP
restart, DHCP lease change): its ESP-IDF glue makes a few immediate retries
and then stops, and adafruit_httpserver keeps a listening socket bound to the
old address. Without this, the settings UI silently stops answering.

Pure Python: `radio` is wifi.radio on the device, a fake under desktop CPython
(tests/test_linkwatch.py). Never prints the Wi-Fi password.
"""
import time

UP = "up"
DOWN = "down"
GAVE_UP = "gave_up"

CHECK_S = 2.0                         # radio property poll interval
GRACE_S = 10.0                        # let CircuitPython's own retries run first
RETRY_GAP_S = (10, 20, 30, 60, 60, 60)  # wait after failed attempt n (1-based)
MAX_RECONNECTS = len(RETRY_GAP_S)     # then ("reset",): ~4 min after the drop


class LinkWatch:
    def __init__(self, radio, ssid, password_fn, host, connect_timeout=10,
                 clock=time.monotonic):
        self.radio = radio
        self.ssid = ssid
        self._pw = password_fn          # called per attempt; value never stored/printed
        self.host = host                # last known station IPv4, as a string
        self.connect_timeout = connect_timeout
        self._clock = clock
        self.state = UP
        self.tries = 0                  # reconnect attempts in the current outage
        self.drops = 0                  # outages since boot (for /api/status)
        self._down_at = 0.0
        self._next_try = 0.0
        self._next_check = 0.0

    def ip(self):
        """Current station IPv4 as a string, or None if not associated / no lease."""
        try:
            if not getattr(self.radio, "connected", True):
                return None
            a = self.radio.ipv4_address
        except Exception:
            return None
        return None if a is None else str(a)

    def tick(self):
        """Call every main-loop pass. Cheap except while DOWN, when a due
        reconnect attempt blocks for up to connect_timeout seconds.

        Returns None, or an event tuple:
          ("down",)             link just dropped
          ("up", old_ip, new_ip) link back or IP changed: restart the HTTP server
          ("reset",)            MAX_RECONNECTS failed: caller hard-resets
        """
        now = self._clock()
        if now < self._next_check or self.state == GAVE_UP:
            return None
        self._next_check = now + CHECK_S
        ip = self.ip()

        if self.state == UP:
            if ip is None:
                self.state = DOWN
                self.tries = 0
                self.drops += 1
                self._down_at = now
                self._next_try = now + GRACE_S
                print("wifi: link lost (ip was %s); first reconnect in %d s"
                      % (self.host, int(GRACE_S)))
                return ("down",)
            if ip != self.host:
                return self._up(ip, "ip changed")
            return None

        # DOWN
        if ip is not None:
            return self._up(ip, "rejoined on its own")
        if now < self._next_try:
            return None
        if self.tries >= MAX_RECONNECTS:
            self.state = GAVE_UP
            print("wifi: still down after %d reconnects (%d s); hard reset"
                  % (self.tries, int(now - self._down_at)))
            return ("reset",)
        self.tries += 1
        print("wifi: reconnect %d/%d to %s" % (self.tries, MAX_RECONNECTS, self.ssid))
        try:
            self.radio.connect(self.ssid, self._pw(), timeout=self.connect_timeout)
        except Exception as e:  # ConnectionError: no AP / auth failed / already connecting
            print("wifi: reconnect %d/%d failed: %s" % (self.tries, MAX_RECONNECTS, e))
        ip = self.ip()
        if ip is not None:
            return self._up(ip, "reconnect %d/%d ok" % (self.tries, MAX_RECONNECTS))
        now = self._clock()  # connect() may have blocked for connect_timeout
        self._next_try = now + RETRY_GAP_S[self.tries - 1]
        self._next_check = now + CHECK_S
        return None

    def _up(self, ip, why):
        old = self.host
        self.host = ip
        self.state = UP
        self.tries = 0
        if ip == old:
            print("wifi: link up, ip %s unchanged (%s)" % (ip, why))
        else:
            print("wifi: link up, ip %s (was %s) (%s)" % (ip, old, why))
        return ("up", old, ip)
