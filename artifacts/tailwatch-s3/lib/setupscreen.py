# AP-mode setup screen: up to four lines of terminalio text on the 128x64
# panel (21 chars/line at 6 px). Used only when code.py falls back to the
# TailWatch-XXXX access point; needs adafruit_display_text from the bundle.
import displayio
import terminalio
from adafruit_display_text import bitmap_label

LINE_PX = 15


def build(lines, color):
    group = displayio.Group()
    y = 7  # label y is the vertical centre of its first line
    for text in lines[:4]:
        lbl = bitmap_label.Label(terminalio.FONT, text=text, color=color)
        lbl.x = 1
        lbl.y = y
        group.append(lbl)
        y += LINE_PX
    return group
