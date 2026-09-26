#!/usr/bin/env python3
"""
Parametric CadQuery (OCCT/BREP) rebuild of the 6 TailWatch S3 printable
parts, for a real STEP export (the OpenSCAD source is a mesh/CSG kernel;
STL is a mesh, not a solid model -- STEP needs an actual BREP solid).

SOURCE OF TRUTH: enclosure/params.scad and enclosure/tailwatch_lib.scad.
Every dimension here is taken from tailwatch_params.py, itself a literal,
manually-kept-in-sync transcription of params.scad's own values and its
DERIVED VALUES section (see that file's docstring). Do not hand-tune
numbers here -- change params.scad's twin values in tailwatch_params.py
instead, then re-run this script.

SIMPLIFICATIONS vs. the OpenSCAD design (all subtractive/cosmetic, so they
do not change any part's overall envelope / bounding box):
  - No corner fillets on the frame's outer profile (frame_corner_r) and no
    front chamfer. Frame outer footprint is a sharp rectangle.
  - No diamond ventilation holes (vents()).
  - No power-cable notch (power_notch()) or USB-C / push-rod side notches
    (portal_notches()) cut into the frame walls.
  - No engraved text labels (labels(), the pod's "TailWatch" text, the
    rod D/U/R letters).
  - The MatrixPortal pod is a solid roof+skirt block (no hollowed-out
    skirt walls, no roof ventilation holes, no rounded corners).
  - The strap's 45-degree wedge-envelope corner relief (wedge_envelope())
    is omitted; the strap body is a plain slab + rib. This can make the
    CadQuery strap's Y extent up to a couple mm larger than the OpenSCAD
    part at the very corners -- within the documented tolerance.

KEPT FAITHFULLY (the mounting/interface features called out as critical):
  - Frame: overall envelope, wall thickness, the 45-degree wedge retention
    ledges on 3 sides of each half, the rear flange, both keyhole slots,
    the seam boss with its bowtie-key pocket.
  - Bowtie keys: exact hexagonal (bowtie) profile and length.
  - Strap: slab + panel-bearing rib + M3 clearance slot, at the correct Z.
  - MatrixPortal pod: correct footprint/roof height, the 4 M2.5 mounting
    posts (with pilot holes) at their exact hole coordinates, and the
    push-rod guide block with its 3 rod tunnels.
  - Button rods: the exact rod_profile() cross-section per button.

All 6 parts are built and exported in the SAME position/orientation as the
existing stl/*.stl files (i.e. the *print* orientation from tailwatch_lib.scad's
frame_print()/strap_print()/pod_print()/rods_print()/keys_print()), so that
tools/check_stl.py's bounding boxes can be compared directly, apples to apples,
against the original OpenSCAD exports.
"""
import math
import os

import cadquery as cq
from cadquery import exporters

import tailwatch_params as P

OUT_DIR = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------
def box(xlo, xhi, ylo, yhi, zlo, zhi):
    return (cq.Workplane("XY")
            .box(xhi - xlo, yhi - ylo, zhi - zlo, centered=(False, False, False))
            .translate((xlo, ylo, zlo)))


def cyl_z(cx, cy, zlo, zhi, d):
    h = zhi - zlo
    return (cq.Workplane("XY").workplane(offset=zlo)
            .center(cx, cy).circle(d / 2).extrude(h))


def wedge_along_x(xlo, xhi, y_edge, inward_sign):
    """45-deg ledge profile (ledge_profile()) extruded along world X."""
    zf, tip, w = P.zf, P.ledge_tip, P.ledge_w
    pts = [(y_edge, zf),
           (y_edge + inward_sign * w, zf),
           (y_edge + inward_sign * w, zf + tip),
           (y_edge, zf + tip + w)]
    length = xhi - xlo
    return (cq.Workplane("YZ").polyline(pts).close().extrude(length)
            .translate((xlo, 0, 0)))


def wedge_along_y(ylo, yhi, x_edge, inward_sign):
    zf, tip, w = P.zf, P.ledge_tip, P.ledge_w
    pts = [(x_edge, zf),
           (x_edge + inward_sign * w, zf),
           (x_edge + inward_sign * w, zf + tip),
           (x_edge, zf + tip + w)]
    length = yhi - ylo
    # XZ plane's normal is -Y; extrude(-length) advances in +Y.
    return (cq.Workplane("XZ").polyline(pts).close().extrude(-length)
            .translate((0, ylo, 0)))


def flange_along_x(xlo, xhi, y_edge, inward_sign):
    z0, z1 = P.flange_front_z, P.flange_front_z + P.flange_t
    fw = P.flange_w
    pts = [(y_edge, z0), (y_edge + inward_sign * fw, z0),
           (y_edge + inward_sign * fw, z1), (y_edge, z1)]
    length = xhi - xlo
    return (cq.Workplane("YZ").polyline(pts).close().extrude(length)
            .translate((xlo, 0, 0)))


def flange_along_y(ylo, yhi, x_edge, inward_sign):
    z0, z1 = P.flange_front_z, P.flange_front_z + P.flange_t
    fw = P.flange_w
    pts = [(x_edge, z0), (x_edge + inward_sign * fw, z0),
           (x_edge + inward_sign * fw, z1), (x_edge, z1)]
    length = yhi - ylo
    return (cq.Workplane("XZ").polyline(pts).close().extrude(-length)
            .translate((0, ylo, 0)))


def print_transform(shape, tx, ty, tz_offset):
    """Reproduces OpenSCAD's
         translate([tx,ty,0]) rotate([180,0,0]) translate([0,0,-tz_offset])
       (used by frame_print / strap_print / pod_print)."""
    return shape.rotate((0, 0, 0), (1, 0, 0), 180).translate((tx, ty, tz_offset))


# ---------------------------------------------------------------------
# FRAME HALF
# ---------------------------------------------------------------------
def bowtie_half_pts(clr, keep):
    """Half of bowtie_2d(clr), local coords, keep='left' (x<=0) or 'right'."""
    h = P.bt_len / 2 + clr
    e = P.bt_end / 2 + clr
    wst = P.bt_waist / 2 + clr
    if keep == "left":
        return [(-h, -e), (0, -wst), (0, wst), (-h, e)]
    else:
        return [(0, -wst), (h, -e), (h, e), (0, wst)]


def frame_half(side):
    C, W = P.C, P.W
    pw, ph = P.panel_w, P.panel_h
    seam_x = P.seam_x
    face_proud = P.face_proud
    fbz = P.frame_back_z

    if side == 0:
        xlo, xhi = -C - W, seam_x
        end_x_edge = -C          # outer edge of the panel opening on this end
        end_inward = +1          # ledge/flange reach in +X (toward panel interior)
    else:
        xlo, xhi = seam_x, pw + C + W
        end_x_edge = pw + C
        end_inward = -1

    ylo, yhi = -C - W, ph + C + W
    zlo, zhi = -face_proud, fbz

    # outer solid minus the through panel opening -> 3-sided picture-frame wall
    outer = box(xlo, xhi, ylo, yhi, zlo, zhi)
    opening = box(-C, pw + C, -C, ph + C, zlo - 1, zhi + 2)
    solid = outer.cut(opening)

    # --- wedge ledges (bottom, top, and this half's outer end) ---
    ledge_x_lo, ledge_x_hi = (-C, seam_x) if side == 0 else (seam_x, pw + C)
    solid = solid.union(wedge_along_x(ledge_x_lo, ledge_x_hi, -C, +1))          # bottom
    solid = solid.union(wedge_along_x(ledge_x_lo, ledge_x_hi, ph + C, -1))      # top
    solid = solid.union(wedge_along_y(-C, ph + C, end_x_edge, end_inward))       # outer end

    # --- rear flange (same 3 sides) ---
    solid = solid.union(flange_along_x(ledge_x_lo, ledge_x_hi, -C, +1))
    solid = solid.union(flange_along_x(ledge_x_lo, ledge_x_hi, ph + C, -1))
    solid = solid.union(flange_along_y(-C, ph + C, end_x_edge, end_inward))

    # --- keyhole boss + keyhole slot (top side only, one per half) ---
    for kx in P.keyhole_xs():
        if (side == 0 and kx < seam_x) or (side == 1 and kx >= seam_x):
            solid = solid.union(box(kx - P.kh_boss_w / 2, kx + P.kh_boss_w / 2,
                                     ph + C - P.kh_boss_d, ph + C,
                                     P.flange_front_z, P.flange_front_z + P.flange_t))
            z0, z1 = P.flange_front_z - 1, P.flange_front_z + P.flange_t + 1
            entry = cyl_z(kx, P.kh_entry_y, z0, z1, P.kh_head_d)
            slot = box(kx - P.kh_shank_d / 2, kx + P.kh_shank_d / 2,
                       P.kh_entry_y, P.kh_entry_y + P.kh_slot, z0, z1)
            top_hole = cyl_z(kx, P.kh_entry_y + P.kh_slot, z0, z1, P.kh_shank_d)
            solid = solid.cut(entry).cut(slot).cut(top_hole)

    # --- seam boss + half bowtie-key pocket, bottom and top ---
    boss_half = P.boss_len / 2
    bx = (seam_x - boss_half, seam_x) if side == 0 else (seam_x, seam_x + boss_half)
    keep = "left" if side == 0 else "right"
    for s in (0, 1):
        by = (-C, -C + P.boss_d) if s == 0 else (ph + C - P.boss_d, ph + C)
        solid = solid.union(box(bx[0], bx[1], by[0], by[1], P.zf, fbz))
        yc = -C + P.boss_d / 2 - 0.5 if s == 0 else ph + C - P.boss_d / 2 + 0.5
        pts = bowtie_half_pts(P.bt_clr, keep)
        pocket = (cq.Workplane("XY").workplane(offset=P.zf - 1)
                  .center(seam_x, yc).polyline(pts).close()
                  .extrude(fbz - P.zf + 2))
        solid = solid.cut(pocket)

    return solid


# ---------------------------------------------------------------------
# STRAP
# ---------------------------------------------------------------------
def strap_raw():
    C = P.C
    sw, st = P.strap_w, P.strap_t
    y0 = -C + P.ledge_w - P.strap_overlap
    slen = P.panel_h - 2 * y0
    rib_y0 = -C + P.ledge_w + 1
    ffz = P.strap_front_z

    body = box(-sw / 2, sw / 2, y0, y0 + slen, ffz, ffz + st)
    rib = box(-sw / 2, sw / 2, rib_y0, P.panel_h - rib_y0, ffz - P.rib_h, ffz)
    solid = body.union(rib)

    # M3 clearance slot (long slot for the two screws into the panel posts)
    y_a, y_b = rib_y0 + 5, P.panel_h - rib_y0 - 5
    slot = (cq.Workplane("XY").workplane(offset=0)
            .center(0, y_a).circle(P.strap_slot_w / 2)
            .center(0, y_b - y_a).circle(P.strap_slot_w / 2)
            .extrude(100))
    # build slot as hull-like capsule via two cylinders + connecting box
    c1 = cyl_z(0, y_a, 0, 100, P.strap_slot_w)
    c2 = cyl_z(0, y_b, 0, 100, P.strap_slot_w)
    mid = box(-P.strap_slot_w / 2, P.strap_slot_w / 2, y_a, y_b, 0, 100)
    solid = solid.cut(c1).cut(c2).cut(mid)
    return solid


# ---------------------------------------------------------------------
# MATRIXPORTAL POD (board-local frame; solid roof+skirt simplification)
# ---------------------------------------------------------------------
def pod_raw():
    skz = P.mp_pcb_t + P.pod_skirt_gap
    roof = box(P.pod_x0, P.pod_x1, P.pod_y0, P.pod_y1, skz, P.roof_top_bz)

    by0 = P.btn_y_min - P.rod_w / 2 - 2
    by1 = P.btn_y_max + P.rod_w / 2 + 2.5
    block_z0 = P.rod_bz0 - P.rod_clr - P.block_floor
    guide = box(P.x_block_out, P.x_block_out + P.block_len, by0, by1,
                block_z0, P.roof_under_bz + 0.5)

    posts = None
    for hx, hy in P.mp_holes:
        c = cyl_z(hx, hy, P.mp_pcb_t, P.roof_under_bz + 0.5, P.pod_post_d)
        posts = c if posts is None else posts.union(c)

    solid = roof.union(guide).union(posts)

    if P.pod_fix == "screws":
        for hx, hy in P.mp_holes:
            pilot = cyl_z(hx, hy, P.mp_pcb_t - 1, P.mp_pcb_t + P.pod_pilot_depth + 1,
                          P.pod_pilot_d)
            solid = solid.cut(pilot)

    for b in P.mp_buttons:
        tunnel = box(P.x_block_out - 1, P.x_block_out + P.block_len + 1,
                      b[1] - P.rod_w / 2 - P.rod_clr, b[1] + P.rod_w / 2 + P.rod_clr,
                      P.rod_bz0 - P.rod_clr, P.rod_bz0 - P.rod_clr + P.rod_h + 2 * P.rod_clr)
        solid = solid.cut(tunnel)

    return solid


# ---------------------------------------------------------------------
# BUTTON RODS (built directly in rods_print() print-bed layout)
# ---------------------------------------------------------------------
def rod_profile_solid(tip, thickness):
    """rod_profile(tip) extruded along Z by `thickness` (matches rods_print(),
    which extrudes the 2D (x,z)-named profile straight along local Z)."""
    xc = tip - P.btn_gap
    legt = P.leg_t + (tip - P.tip_min)
    r1 = box(xc - legt, xc, P.leg_bot_bz, P.rod_top_bz, 0, thickness)
    r2 = box(P.x_pad_in, xc, P.rod_bz0, P.rod_bz0 + P.rod_h, 0, thickness)
    r3 = box(P.x_pad_in - P.pad_t, P.x_pad_in,
              P.rod_bz0 - P.pad_drop, P.rod_bz0 + P.rod_h, 0, thickness)
    return r1.union(r2).union(r3)


def rods_assembly():
    rod_prof_lo = min(P.leg_bot_bz, P.rod_bz0 - P.pad_drop)
    rod_prof_h = P.rod_top_bz - rod_prof_lo
    solid = None
    for i, b in enumerate(P.mp_buttons):
        tx = -(P.x_pad_in - P.pad_t)
        ty = i * (rod_prof_h + 4) - rod_prof_lo
        r = rod_profile_solid(b[2], P.rod_w).translate((tx, ty, 0))
        solid = r if solid is None else solid.union(r)
    return solid


# ---------------------------------------------------------------------
# BOWTIE KEYS (built directly in keys_print() print-bed layout)
# ---------------------------------------------------------------------
def bowtie_full_pts(clr):
    h = P.bt_len / 2 + clr
    e = P.bt_end / 2 + clr
    wst = P.bt_waist / 2 + clr
    return [(-h, -e), (0, -wst), (h, -e), (h, e), (0, wst), (-h, e)]


def keys_assembly():
    pts = bowtie_full_pts(0)
    solid = None
    for i in (0, 1):
        tx = P.bt_len / 2 + 1 + i * (P.bt_len + 4)
        ty = P.bt_end / 2 + 1
        k = (cq.Workplane("XY").polyline(pts).close().extrude(P.bt_key_len)
             .translate((tx, ty, 0)))
        solid = k if solid is None else solid.union(k)
    return solid


# ---------------------------------------------------------------------
# build + export everything
# ---------------------------------------------------------------------
def export_part(name, shape):
    stl_path = os.path.join(OUT_DIR, f"{name}_cq.stl")
    step_path = os.path.join(OUT_DIR, f"{name}.step")
    exporters.export(shape, stl_path)
    exporters.export(shape, step_path)
    print(f"exported {name}: {stl_path}, {step_path}")


def main():
    P.__name__  # touch to avoid unused import lint

    frame_left = print_transform(frame_half(0), P.C + P.W, P.panel_h + P.C + P.W, P.frame_back_z)
    frame_right = print_transform(frame_half(1), -P.seam_x, P.panel_h + P.C + P.W, P.frame_back_z)
    strap = print_transform(strap_raw(), P.strap_w / 2,
                             P.panel_h - (-P.C + P.ledge_w - P.strap_overlap), P.strap_rear_z)
    pod = print_transform(pod_raw(), -P.pod_x0, P.pod_y1, P.roof_top_bz)
    rods = rods_assembly()          # already in print-bed layout
    keys = keys_assembly()          # already in print-bed layout

    export_part("frame_left", frame_left)
    export_part("frame_right", frame_right)
    export_part("strap", strap)
    export_part("portal_pod", pod)
    export_part("button_rods", rods)
    export_part("bowtie_keys", keys)


if __name__ == "__main__":
    main()
