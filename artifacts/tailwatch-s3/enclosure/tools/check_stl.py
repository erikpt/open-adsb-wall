#!/usr/bin/env python3
"""Sanity-check STL files exported by OpenSCAD.

For each file: facet count, bounding box vs. the print volume, enclosed
volume, and a manifold test (every edge must be used by exactly two
triangles, once in each direction).  Pure standard library.

usage: check_stl.py [--bed X Y Z] file.stl [file.stl ...]
exit status 1 if any file is empty, non-manifold or too big for the bed.
"""
import struct
import sys
from collections import Counter


def read_stl(path):
    data = open(path, "rb").read()
    tris = []
    if data[:5] == b"solid" and b"facet" in data[:1000]:
        verts = []
        for line in data.decode("ascii", "replace").splitlines():
            parts = line.split()
            if parts and parts[0] == "vertex":
                verts.append(tuple(float(v) for v in parts[1:4]))
                if len(verts) == 3:
                    tris.append(tuple(verts))
                    verts = []
    else:
        n = struct.unpack("<I", data[80:84])[0]
        for i in range(n):
            v = struct.unpack("<12f", data[84 + 50 * i: 84 + 50 * i + 48])
            tris.append((v[3:6], v[6:9], v[9:12]))
    return tris


def check(path, bed):
    tris = read_stl(path)
    if not tris:
        return False, f"{path}: EMPTY"
    pts = [p for t in tris for p in t]
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    size = [hi[i] - lo[i] for i in range(3)]

    # manifold: each directed edge exactly once, and its reverse exactly once
    key = lambda p: (round(p[0], 4), round(p[1], 4), round(p[2], 4))
    directed = Counter()
    for t in tris:
        k = [key(p) for p in t]
        for a, b in ((0, 1), (1, 2), (2, 0)):
            directed[(k[a], k[b])] += 1
    bad = sum(1 for e, c in directed.items() if c != 1 or directed.get((e[1], e[0]), 0) != 1)

    vol = 0.0
    for a, b, c in tris:
        vol += (a[0] * (b[1] * c[2] - b[2] * c[1])
                - a[1] * (b[0] * c[2] - b[2] * c[0])
                + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0

    fits = all(size[i] <= bed[i] for i in range(3))
    ok = fits and bad == 0 and vol > 0
    msg = (f"{path}: {len(tris)} facets, bbox {size[0]:.1f} x {size[1]:.1f} x {size[2]:.1f} mm "
           f"(bed {bed[0]}x{bed[1]}x{bed[2]}: {'FITS' if fits else 'TOO BIG'}), "
           f"volume {vol / 1000:.1f} cm3, "
           f"{'manifold' if bad == 0 else f'NON-MANIFOLD ({bad} bad edges)'}, "
           f"z-min {lo[2]:.2f}")
    return ok, msg


def main(argv):
    bed = [220.0, 220.0, 250.0]
    if len(argv) > 1 and argv[1] == "--bed":
        bed = [float(v) for v in argv[2:5]]
        argv = argv[:1] + argv[5:]
    all_ok = True
    for path in argv[1:]:
        ok, msg = check(path, bed)
        all_ok &= ok
        print(("OK   " if ok else "FAIL ") + msg)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
