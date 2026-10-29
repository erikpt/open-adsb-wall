"""Generate the OTA manifest the device checks and installs (issue #29).

Host-only build tool (desktop python3, stdlib only); NOT copied to CIRCUITPY.
Walks firmware/ for the files an update is allowed to replace
(firmware/lib/ota.py:safe_path(): code.py, lib/**, www/**), hashes each, and
writes manifest.json. Host the manifest and the files it lists anywhere HTTPS
(e.g. as GitHub release assets, or a raw/pages URL), then paste the manifest's
URL into the web UI's "Firmware update" box -- saving it there also turns on
the device's daily background check, which shows an "update available" notice
on the panel when this manifest's version is newer than the one running.

  python3 tools/gen_ota_manifest.py --base-url https://example.com/tailwatch/1.1.0
  python3 tools/gen_ota_manifest.py --base-url ... --since v1.0.0   # only files changed since a git ref
  python3 tools/gen_ota_manifest.py --base-url ... --only 'lib/h*.py' --only code.py

Each file is served at <base-url>/<its path>, e.g. <base-url>/lib/hero.py.

The manifest "version" is firmware/lib/version.py's VERSION: bump it BEFORE
generating, or a device already on that version will (correctly) see nothing
new. lib/version.py is always included so applying an update stamps the new
version, and --since can keep the download small -- every file in the manifest
is staged next to its live copy and then kept as a .ota_bak backup, so a full
update briefly needs roughly 2x the changed files' size free on the drive
(see DESIGN.md sec. 7 "OTA firmware updates").

Never included, by design: boot.py, ota_recover.py, settings.toml, prefs.json
-- the device's allow-list refuses them (ota_recover.py is what repairs an
interrupted update, so an update must never be able to leave it half-swapped;
boot.py/settings/prefs are owner state). Updating those still takes USB.
"""
import argparse
import fnmatch
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FIRMWARE = os.path.join(HERE, "..", "firmware")
sys.path.insert(0, FIRMWARE)                       # ota_recover.py (imported by ota.py)
sys.path.insert(0, os.path.join(FIRMWARE, "lib"))

import ota  # noqa: E402
from version import VERSION  # noqa: E402

ALWAYS = "lib/version.py"


def collect(firmware=FIRMWARE):
    """Sorted relative paths of every OTA-eligible file under `firmware`."""
    out = []
    for top in ("lib", "www"):
        for dirpath, dirnames, filenames in os.walk(os.path.join(firmware, top)):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for name in filenames:
                if name.endswith(".pyc") or name == ".DS_Store":
                    continue
                full = os.path.join(dirpath, name)
                out.append(os.path.relpath(full, firmware).replace(os.sep, "/"))
    if os.path.exists(os.path.join(firmware, "code.py")):
        out.append("code.py")
    return sorted(p for p in out if ota.safe_path(p))


def changed_since(ref, firmware=FIRMWARE):
    """Paths (firmware-relative) changed between git `ref` and the working tree."""
    root = os.path.abspath(os.path.join(firmware, ".."))
    res = subprocess.run(["git", "diff", "--name-only", ref, "--", "firmware"],
                         cwd=root, capture_output=True, text=True, check=True)
    return [l[len("firmware/"):] for l in res.stdout.splitlines() if l.startswith("firmware/")]


def build(base_url, paths, firmware=FIRMWARE, version=VERSION):
    """Manifest dict for `paths` (firmware-relative), validated the same way
    the device will validate it. Raises ota.OTAError / ValueError."""
    base = base_url.rstrip("/")
    if not base.lower().startswith("https://"):
        raise ValueError("--base-url must be https:// (the device refuses anything else)")
    files = []
    for path in sorted(set(paths) | {ALWAYS}):
        with open(os.path.join(firmware, path), "rb") as f:
            data = f.read()
        files.append({"path": path, "url": base + "/" + path,
                      "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)})
    manifest = {"version": version, "files": files}
    raw = json.dumps(manifest)
    if len(raw) > ota.MAX_MANIFEST_SIZE:
        raise ValueError("manifest is %d bytes, over the device's %d-byte limit -- "
                         "use --since or --only to ship fewer files" % (len(raw), ota.MAX_MANIFEST_SIZE))
    ota.parse_manifest(raw)  # size/path/hash-format checks, exactly as the device runs them
    return manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", required=True, help="https:// URL the files will be served under")
    ap.add_argument("--out", default="manifest.json", help="output path (default: ./manifest.json)")
    ap.add_argument("--since", help="only files changed since this git ref (lib/version.py is always added)")
    ap.add_argument("--only", action="append", help="only paths matching this glob (repeatable)")
    args = ap.parse_args()

    paths = collect()
    if args.since:
        keep = set(changed_since(args.since))
        paths = [p for p in paths if p in keep]
    if args.only:
        paths = [p for p in paths if any(fnmatch.fnmatch(p, g) for g in args.only)]
    try:
        manifest = build(args.base_url, paths)
    except (ValueError, ota.OTAError) as e:
        sys.exit("gen_ota_manifest: %s" % e)
    with open(args.out, "w") as f:
        json.dump(manifest, f, indent=1)
        f.write("\n")
    total = sum(x["size"] for x in manifest["files"])
    print("%s: version %s, %d files, %.1f KB -> %s" % (
        "manifest", manifest["version"], len(manifest["files"]), total / 1024, args.out))


if __name__ == "__main__":
    main()
