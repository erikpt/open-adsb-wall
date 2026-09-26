# Hold-to-trigger detector for the MatrixPortal S3's onboard buttons.
#
# board.BUTTON_UP / board.BUTTON_DOWN have no onboard pull-up resistors and
# read low when pressed, so the internal pull-up must be enabled here.

import time
import digitalio


class HoldButton:
    """Fires once after `pin` has been held continuously for hold_s seconds.

    Call poll() frequently from the main loop. Returns True exactly once per
    qualifying hold; the button must be released before it can fire again.
    """

    def __init__(self, pin, hold_s=5.0):
        self._io = digitalio.DigitalInOut(pin)
        self._io.direction = digitalio.Direction.INPUT
        self._io.pull = digitalio.Pull.UP
        self.hold_s = hold_s
        self._press_start = None
        self._fired = False

    def _pressed(self):
        return not self._io.value  # active-low

    def poll(self):
        if self._pressed():
            if self._press_start is None:
                self._press_start = time.monotonic()
                self._fired = False
            elif not self._fired and time.monotonic() - self._press_start >= self.hold_s:
                self._fired = True
                return True
        else:
            self._press_start = None
            self._fired = False
        return False
