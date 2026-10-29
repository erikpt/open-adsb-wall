# boot.py -- runs once on hard reset / power-up (not on soft reload).
# Default: remount CIRCUITPY read-write for code.py so /prefs.json and
# /prefs.bak can be saved. The USB host then sees the drive as read-only.
# Hold the UP button while pressing RESET (or while powering up) to skip
# the remount: the USB drive stays writable for updating code/lib/www,
# and prefs saves from the web UI will fail until the next normal boot.
import board
import digitalio
import storage

usb_write = False
try:
    btn = digitalio.DigitalInOut(board.BUTTON_UP)
    btn.switch_to_input(pull=digitalio.Pull.UP)
    usb_write = not btn.value  # active-low: pressed == False
    btn.deinit()
except Exception as e:  # missing pin name etc. -> fail safe (USB writable)
    print("boot: button read failed", e)
    usb_write = True

if usb_write:
    print("boot: UP held -> CIRCUITPY writable over USB, read-only to code.py")
else:
    storage.remount("/", readonly=False)
    print("boot: CIRCUITPY writable by code.py, read-only over USB")

# Finish an interrupted OTA file swap (issue #29) while only boot.py's own
# imports have run: if the cut left code.py itself as just code.py.ota_new
# there would be nothing for the supervisor to run. Needs the writable
# remount above (skipped with UP held -- code.py retries before its imports).
if not usb_write:
    try:
        import ota_recover
        ota_recover.recover()
    except Exception as e:  # never let recovery trouble block the boot itself
        print("boot: ota recover failed", e)
