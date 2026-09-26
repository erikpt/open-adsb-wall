"""
Numeric transcription of enclosure/params.scad + the DERIVED VALUES section
at the bottom of that file, plus the coordinate-frame helpers from
tailwatch_lib.scad, translated to plain Python floats/lists.

This is NOT parsed from the .scad automatically -- it is a manual, literal
copy of the same numbers and formulas, kept in the same order as the source
so a diff against params.scad is easy. If you change params.scad, update
this file the same way, then re-run cadquery_build.py.

Source of truth: ../params.scad and ../tailwatch_lib.scad (read 2026-09-26).
"""
import math

# ---------- Print volume ----------
bed = [200, 200, 250]

# ---------- LED panel ----------
panel_w = 256
panel_h = 128
panel_thk = 13.0
panel_clr = 0.5

panel_holes = [[48, 24], [48, 104], [208, 24], [208, 104]]
panel_hole_d = 3.0

hub75_in_xy = [176, 64]
portal_rot = 0
portal_pcb_z = 15.5

# ---------- Adafruit MatrixPortal S3 ----------
mp_pcb = [63.5, 44.45]
mp_pcb_t = 1.6
mp_corner_r = 2.54
mp_holes = [[7.62, 15.875], [7.62, 35.56], [48.26, 15.875], [48.26, 35.56]]
mp_hole_d = 2.5
mp_socket_c = [57.15, 22.225]
mp_socket = [5.33, 25.4, 5.55]
mp_idc_lo = [52.24, 5.02]
mp_idc_hi = [61.90, 39.34]
mp_top_max = 10.64
mp_usb_y = 8.255
mp_usb_bz = 3.17
mp_buttons_all = [["DN", 18.542, -1.07], ["UP", 28.321, -0.94], ["RST", 38.100, -0.44]]
mp_btn_bz = 3.37
include_reset_pusher = True

# ---------- Printed-part general ----------
wall_t = 2.5
face_proud = 1.0
frame_corner_r = 3.0

# ---------- Panel retention ledge ----------
ledge_w = 6.0
ledge_tip = 2.0
ledge_gap = 0.2

# ---------- Rear flange ----------
flange_w = 8.0
flange_t = 3.0
frame_back_z_override = 0
wall_gap_min = 3.0

# ---------- Frame split ----------
seam_x = panel_w / 2
boss_len = 28
boss_d = 12
bt_len = 20
bt_waist = 4.0
bt_end = 8.0
bt_clr = 0.15

# ---------- Keyhole slots ----------
keyhole_spacing = 160
kh_head_d = 9.0
kh_shank_d = 4.5
kh_slot = 8.0
kh_boss_w = 20

# ---------- Ventilation (skipped in CadQuery rebuild) ----------
vent_d = 6.0
vent_pitch = 9.0

# ---------- Power notch (skipped in CadQuery rebuild) ----------
power_notch_x = 200
power_notch_w = 9.0
power_notch_bottom_z = 18.0

# ---------- USB-C notch (skipped in CadQuery rebuild) ----------
usb_notch_w = 10.0
usb_notch_dz = 3.5

# ---------- Rear straps ----------
strap_xs = [48, 208]
strap_w = 16
strap_t = 5.0
strap_slot_w = 3.4
strap_overlap = 3.0
strap_clr = 0.2
strap_preload = 0.3

# ---------- MatrixPortal pod ----------
pod_clear = 11.8
pod_roof_t = 2.4
pod_margin = 1.5
pod_skirt_t = 2.0
pod_skirt_gap = 5.0
pod_post_d = 4.6
pod_fix = "screws"
pod_pilot_d = 2.2
pod_pilot_depth = 8.0
pod_pin_d = 2.3

# ---------- Button push-rods ----------
rod_w = 4.0
rod_h = 4.5
rod_clr = 0.3
btn_gap = 0.4
leg_t = 2.5
leg_bot_bz = 1.8
block_len = 10
block_floor = 1.6
pad_gap = 2.0
pad_t = 2.5
pad_drop = 3.0

eps = 0.01

# =====================================================================
# DERIVED VALUES (mirrors params.scad's own derived section)
# =====================================================================
C = panel_clr
W = wall_t
zf = panel_thk + ledge_gap
wedge_top_z = zf + ledge_tip + ledge_w

roof_under_bz = mp_pcb_t + pod_clear
roof_top_bz = roof_under_bz + pod_roof_t
pod_top_z = portal_pcb_z + roof_top_bz

frame_back_z = (frame_back_z_override if frame_back_z_override > 0
                else math.ceil((pod_top_z + wall_gap_min) * 2) / 2)
flange_front_z = frame_back_z - flange_t

strap_front_z = zf + ledge_tip + strap_clr
strap_rear_z = strap_front_z + strap_t
rib_h = strap_front_z - zf - strap_preload

kh_top_y = panel_h + C - kh_head_d / 2 - 1
kh_entry_y = kh_top_y - kh_slot
kh_boss_d = panel_h + C - kh_entry_y + kh_head_d / 2 + 2.5

mp_buttons = mp_buttons_all if include_reset_pusher else [b for b in mp_buttons_all if b[0] != "RST"]
tip_min = min(b[2] for b in mp_buttons)
x_block_in = tip_min - btn_gap - leg_t
x_block_out = x_block_in - block_len
rod_top_bz = roof_under_bz - rod_clr - 0.4
rod_bz0 = rod_top_bz - rod_h
btn_y_min = min(b[1] for b in mp_buttons)
btn_y_max = max(b[1] for b in mp_buttons)

pr_c = round(math.cos(math.radians(portal_rot)))
pr_s = round(math.sin(math.radians(portal_rot)))


def b2p(p):
    z = portal_pcb_z + (p[2] if len(p) > 2 else 0)
    return [
        hub75_in_xy[0] + pr_c * (p[0] - mp_socket_c[0]) - pr_s * (p[1] - mp_socket_c[1]),
        hub75_in_xy[1] + pr_s * (p[0] - mp_socket_c[0]) + pr_c * (p[1] - mp_socket_c[1]),
        z,
    ]


edge_dist = (hub75_in_xy[0] + C + W if portal_rot == 0
             else hub75_in_xy[1] + C + W if portal_rot == 90
             else panel_w + C + W - hub75_in_xy[0] if portal_rot == 180
             else panel_h + C + W - hub75_in_xy[1])
wall_out_bx = mp_socket_c[0] - edge_dist
x_pad_in = wall_out_bx - pad_gap

pod_x0 = x_block_out - 0.5
pod_x1 = mp_pcb[0] + pod_margin + pod_skirt_t
pod_y0 = -pod_margin - pod_skirt_t
pod_y1 = mp_pcb[1] + pod_margin + pod_skirt_t

bt_key_len = frame_back_z - zf - 0.5


def keyhole_xs():
    return [seam_x - keyhole_spacing / 2, seam_x + keyhole_spacing / 2]


if __name__ == "__main__":
    print("frame_back_z =", frame_back_z, "(total depth", frame_back_z + face_proud, ")")
    print("zf =", zf, "wedge_top_z =", wedge_top_z)
    print("strap_front_z =", strap_front_z, "strap_rear_z =", strap_rear_z, "rib_h =", rib_h)
    print("pod_x0..pod_x1 =", pod_x0, pod_x1, "pod_y0..pod_y1 =", pod_y0, pod_y1)
    print("roof_under_bz =", roof_under_bz, "roof_top_bz =", roof_top_bz)
    print("rod_bz0 =", rod_bz0, "rod_top_bz =", rod_top_bz)
    print("x_block_out =", x_block_out, "x_pad_in =", x_pad_in)
    print("keyhole_xs =", keyhole_xs(), "kh_entry_y =", kh_entry_y, "kh_boss_d =", kh_boss_d)
    print("bt_key_len =", bt_key_len)
