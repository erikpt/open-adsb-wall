# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

TailWatch: a wall-mounted LED display (Adafruit MatrixPortal S3 + 128×64 HUB75
panel, CircuitPython) that shows one live nearby aircraft at a time. Runs
entirely on-device — no cloud API, no server component, no subscription (see
`DESIGN.md` §2/§4 for why: issue #2 explicitly killed an earlier planned cloud
tier). `DESIGN.md` is the authoritative spec; read it, not this file, for
behavior/protocol details. `README.md` is the on-device file/flash-procedure
reference.

Only what actually gets copied to the CIRCUITPY drive lives under
`firmware/`; `DESIGN.md`, `README.md`, `docs/`, `enclosure/`, `tools/`, and
`tests/` are host-only and live at the repo root.

## Branches

- `main` — base branch, PRs land here.
- `website` — **unrelated git history** (orphan branch). Holds only the static
  marketing site (`index.html`, `styles.css`) for Cloudflare Pages, deployed
  from this branch directly. Never merge it with `main`; edit it via a
  separate worktree (`git worktree add <path> website`), not by checking it
  out in the main worktree.
- Feature work happens on `claude/*`-style branches and PRs into `main`.

## Commands

Firmware host-side tests (plain Python 3, stdlib only, no pytest, no
CircuitPython — these are never copied to the device):

```sh
for f in tests/test_*.py; do python3 "$f" || exit 1; done   # full suite
python3 tests/test_hero.py                                   # single file
```

`tests/test_code_*.py` run the real `firmware/code.py` under faked
CircuitPython modules (`board`, `wifi`, `displayio`, `adafruit_httpserver`, …)
with a simulated clock — they check control flow and serial output, not real
hardware.

Enclosure (3D-printable case) — regenerate/verify after any `.scad` change:

```sh
cd enclosure
tools/build.sh                                    # OpenSCAD: STLs + preview PNGs + checks
python3 tools/check_stl.py stl/*.stl              # manifold + bed-fit check only
tools/export_blender_stls.sh && blender --background --python tools/blender_build.py  # Blender + glTF
python3 step/cadquery_build.py                    # CadQuery/STEP rebuild (pip install cadquery)
```

`openscad` and `blender` are plain apt packages on this container's Ubuntu
base; `cadquery` is pip-installable. FreeCAD and snap are **not** usable here
(FreeCAD isn't in this Ubuntu mirror and its AppImage needs a blocked host;
snap needs systemd, which this container doesn't run) — CadQuery's STEP
export is the path to FreeCAD-compatible output instead.

## Architecture

`firmware/code.py` is the firmware entry point: brings up the matrix/display,
joins Wi-Fi (or falls back to a `TailWatch-XXXX` setup AP —
`firmware/lib/wifisettings.py`, `firmware/lib/setupscreen.py`), runs the local
settings HTTP server, and drives the poll loop. It is **not** a stub — see
`DESIGN.md` §9's module table for what's built vs. still `to build`
(`firmware/lib/net.py` the OpenSky HTTPS client, `firmware/lib/card.py` the
real display renderer — `poll_card()` is currently a documented placeholder).

Everything else lives in `firmware/lib/`, one concern per module: `prefs.py`
(load/save/validate), `hero.py` (which aircraft to show — has hysteresis to
avoid flapping between near-equidistant planes), `enrich.py`/`filters.py`/
`logos/` (on-device airline lookup, heli/mil/GA filtering, non-trademarked
letter-mark badges — no scraped logos, no network fetch),
`schedule.py`/`sun.py`/`tz.py` (sleep/night/brightness windows — has a
clock-trust gate so a failed NTP sync can't strand the panel dark),
`linkwatch.py`/`httpclient.py` (Wi-Fi reconnect watchdog and the shared
always-closing HTTP client pattern `firmware/lib/net.py` must use),
`reqguard.py` (same-origin/CSRF guard on the local API), `dim.py`
(color-scaled brightness — `rgbmatrix`'s `display.brightness` is effectively
binary on this hardware, not a real dimmer).

`nyan.py`/`buttons.py` is an easter egg (hold DOWN 5s), unrelated to the above.

**Hardware footgun, confirmed on real hardware**: the MatrixPortal S3's own
5V/GND screw terminals next to the HUB75 connector are USB-fed *output only*.
Wiring the panel's external power supply there instead of the panel's own
power input leaves the panel entirely USB-dependent (goes dark when USB-C is
unplugged despite a "connected" external supply). Full explanation in
`DESIGN.md` §3.

The enclosure (`enclosure/`) is maintained in three parallel,
cross-checked forms from one set of real measured dimensions
(`enclosure/params.scad`): OpenSCAD/STL (source of truth, print-ready),
Blender/glTF (for the website's interactive viewer — positioned by re-running
the *exact* OpenSCAD `assembly()` transform per part, not re-derived by hand),
and CadQuery/STEP (a from-scratch OCCT rebuild for FreeCAD/Fusion/etc., since
STL meshes can't convert to STEP BREP solids — cross-checked by bounding-box
diff against the OpenSCAD STLs, documented simplifications noted in
`step/cadquery_build.py`'s docstring). All three must stay dimensionally
consistent; changing `params.scad` means regenerating all three (commands
above).
