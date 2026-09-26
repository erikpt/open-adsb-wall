// =====================================================================
//  TailWatch S3 enclosure -- shared, adjustable parameters
//  (included by every part file; edit values HERE, then run tools/build.sh)
// =====================================================================
//
//  COORDINATE SYSTEM ("back view") -- used by every part and parameter:
//    Stand BEHIND the panel, looking at its connectors.
//      +X = to your right, +Y = up, +Z = toward you (toward the wall).
//      z = 0 is the LED face.  (x,y) = (0,0) is the panel's lower-LEFT
//      corner AS SEEN FROM THE BACK (= lower-RIGHT corner seen from the front).
//    Measure every panel-specific position below this way.
//
//  Tags used in comments:
//    [VERIFIED]    taken from a published source (see README "Sources")
//    [MEASURE]     depends on your specific panel/board -- check with calipers
//    [PLACEHOLDER] a guess so the model renders; you MUST set it for your panel
//    [TUNE]        printer / fit tolerance, adjust to taste
// =====================================================================

/* ---------- Print volume (every part is checked against this) ---------- */
bed = [220, 220, 250];            // X, Y, Z build volume in mm

/* ---------- LED panel ---------- */
panel_w   = 256;                  // [VERIFIED] 128 px * 2.0 mm pitch
panel_h   = 128;                  // [VERIFIED]  64 px * 2.0 mm pitch
panel_thk = 13.0;                 // [MEASURE] LED face -> rearmost flat of the plastic
                                  //   back shell (ignore connectors). 13 mm is the value
                                  //   seen on typical P2 256x128 module listings.
panel_clr = 0.5;                  // [TUNE] gap per side between panel edge and frame wall

// Threaded M3 mounting posts on the back of the panel.  Only used for the
// assembly preview and the "is every strap on a hole?" check -- the printed
// parts do NOT depend on these, because the straps are slotted and can sit
// at any X.  Positions vary by manufacturer and even by batch.
panel_holes  = [[48, 24], [48, 104], [208, 24], [208, 104]];   // [PLACEHOLDER]
panel_hole_d = 3.0;               // M3 is the common size on these modules

// Centre of the panel's HUB75 *INPUT* header (the one the MatrixPortal
// plugs into), back-view coordinates.
hub75_in_xy = [176, 64];          // [PLACEHOLDER] measure yours

// Rotation of the MatrixPortal S3 (as seen from the back, component side up)
// about the header.  0 = board's USB/button edge points to -X (your left when
// behind the panel), 90 = points down (-Y), 180 = right (+X), 270 = up (+Y).
// Must be 0, 90, 180 or 270.
portal_rot = 0;                   // [MEASURE] match your board once plugged in

// LED face -> UNDERSIDE of the MatrixPortal PCB once it is fully seated on
// the panel's header.  Depends on the panel's box-header height and shell.
portal_pcb_z = 14.0;              // [MEASURE] most important depth number

/* ---------- Adafruit MatrixPortal S3 (PID 5778) ----------
   All [VERIFIED] values come from Adafruit's own Eagle board file
   (github.com/adafruit/Adafruit-MatrixPortal-S3-PCB) and 3D model
   (github.com/adafruit/Adafruit_CAD_Parts, "5778 Matrix Portal S3").
   Board frame: origin = PCB lower-left corner in the Eagle top view,
   x along the 63.5 mm edge, z = 0 at the PCB underside.               */
mp_pcb      = [63.5, 44.45];      // [VERIFIED] 2.50" x 1.75" outline
mp_pcb_t    = 1.6;                // [VERIFIED] 1.57 mm in the 3D model
mp_corner_r = 2.54;               // [VERIFIED]
mp_holes    = [[7.62, 15.875], [7.62, 35.56], [48.26, 15.875], [48.26, 35.56]]; // [VERIFIED] 2.5 mm plated
mp_hole_d   = 2.5;                // [VERIFIED] -> M2.5 hardware
mp_socket_c = [57.15, 22.225];    // [VERIFIED] centre of 2x10 socket (underside) == 2x8 IDC (top)
mp_socket   = [5.33, 25.4, 5.55]; // [VERIFIED 3D model] socket body x/y size and depth below PCB
mp_idc_lo   = [52.24, 5.02];      // [VERIFIED 3D model] top-side 2x8 IDC shroud footprint
mp_idc_hi   = [61.90, 39.34];
mp_top_max  = 10.64;              // [VERIFIED 3D model] tallest part above PCB top (IDC shroud)
mp_usb_y    = 8.255;              // [VERIFIED] USB-C centre (mouth flush with the x=0 edge)
mp_usb_bz   = 3.17;               // [VERIFIED 3D model] USB-C centre height above PCB underside
// Right-angle buttons on the x=0 edge: [label, centre y, plunger tip x]
mp_buttons_all = [["DN", 18.542, -1.07],   // [VERIFIED] DOWN
                  ["UP", 28.321, -0.94],   // [VERIFIED] UP (hold at boot = USB-writable)
                  ["RST", 38.100, -0.44]]; // [VERIFIED] RESET
mp_btn_bz   = 3.37;               // [VERIFIED 3D model] plunger centre height above PCB underside
include_reset_pusher = true;      // also make a pusher for RESET (README uses UP + RESET)

/* ---------- Printed-part general ---------- */
wall_t      = 2.5;                // frame wall thickness (>= 2 mm)
face_proud  = 1.0;                // frame lip stands this far IN FRONT of the LED face
                                  //   (protects edges; no overlap onto pixels)
frame_corner_r = 3.0;             // outer corner radius of the frame

/* ---------- Panel retention ledge (45-degree wedge behind the panel edge) ---------- */
ledge_w   = 6.0;                  // how far the ledge reaches in behind the panel edge
ledge_tip = 2.0;                  // thickness of the ledge at its inner tip
ledge_gap = 0.2;                  // [TUNE] panel back shell -> ledge front clearance

/* ---------- Rear flange (sits flat on the wall, carries keyholes) ---------- */
flange_w = 8.0;
flange_t = 3.0;
frame_back_z_override = 0;        // 0 = automatic (just behind the MatrixPortal pod)
wall_gap_min = 3.0;               // min air gap between pod roof and the wall

/* ---------- Frame split (two halves joined by printed bowtie keys) ---------- */
seam_x    = panel_w / 2;          // where the frame is split
boss_len  = 28;                   // seam boss length along X
boss_d    = 12;                   // seam boss depth, inward from wall
bt_len    = 20;                   // bowtie key length (across the seam)
bt_waist  = 4.0;                  // bowtie width at the seam
bt_end    = 8.0;                  // bowtie width at its ends
bt_clr    = 0.15;                 // [TUNE] key clearance per side (tight = glue optional)

/* ---------- Wall hanging: keyhole slots in the top flange ---------- */
keyhole_spacing = 160;            // centre-to-centre of the two wall screws
kh_head_d  = 9.0;                 // entry hole (fits a ~8 mm pan/round screw head)
kh_shank_d = 4.5;                 // slot width (#6-#8 / 3.5-4 mm wood screw shank)
kh_slot    = 8.0;                 // slot length (entry-hole centre -> hang position)
kh_boss_w  = 20;                  // flange widened to this around each keyhole
kh_boss_d  = 18;

/* ---------- Ventilation (diamond holes in top and bottom walls) ---------- */
vent_d     = 6.0;                 // diamond diagonal (no bridging needed)
vent_pitch = 9.0;

/* ---------- Panel 5 V cable entry (bottom wall, open from the rear) ---------- */
power_notch_x = 200;              // [PLACEHOLDER] put it near your panel's power input
power_notch_w = 9.0;              // fits a 5.5x2.1 DC-plug cable or 2x 18 AWG leads
power_notch_bottom_z = 18.0;      // notch floor, measured from LED face

/* ---------- USB-C cable exit (frame wall facing the board's USB edge) ---------- */
usb_notch_w  = 10.0;
usb_notch_dz = 3.5;               // notch floor sits this far below the USB-C centre

/* ---------- Rear straps (hold the panel in the frame) ---------- */
strap_xs      = [48, 208];        // [PLACEHOLDER] X of each strap = X of a column of
                                  //   panel M3 posts. One strap per frame half minimum.
strap_w       = 16;
strap_t       = 4.0;
strap_slot_w  = 3.4;              // M3 clearance
strap_overlap = 3.0;              // strap end reaches this far over the ledge wedge
strap_clr     = 0.2;              // [TUNE] strap end <-> ledge wedge clearance
strap_preload = 0.3;              // rib is this much short so screws clamp the ledge

/* ---------- MatrixPortal pod (hood screwed to the board's 4 M2.5 holes) ---------- */
pod_clear   = 11.8;               // PCB top -> roof underside (tallest part is 10.64)
pod_roof_t  = 2.4;
pod_margin  = 1.5;                // roof overhang past the PCB outline
pod_skirt_t = 2.0;
pod_skirt_gap = 5.0;              // open gap between PCB top and skirt bottom (air + cables)
pod_post_d  = 5.5;
pod_pilot_d = 2.2;                // [TUNE] M2.5 self-tapping pilot (2.5 = clearance)
pod_pilot_depth = 8.0;

/* ---------- Button push-rods ---------- */
rod_w     = 4.0;                  // rod width (along the board edge)
rod_h     = 4.5;                  // rod height (depth direction)
rod_clr   = 0.3;                  // [TUNE] tunnel / notch clearance per side
btn_gap   = 0.4;                  // rest gap between pusher leg and switch plunger
leg_t     = 2.5;                  // pusher leg thickness (for the most-protruding plunger)
leg_bot_bz = 1.8;                 // leg bottom, above PCB underside (plunger spans 2.07..4.67)
block_len = 10;                   // guide-tunnel length
block_floor = 1.6;                // material under the tunnels
pad_gap   = 2.0;                  // [TUNE] finger pad -> frame wall gap = hard overtravel stop
pad_t     = 2.5;
pad_drop  = 3.0;                  // pad extends this far below the rod (catches on the wall)

/* ---------- Engraved labels ---------- */
label_size  = 3.5;
label_depth = 0.6;

/* ---------- Render quality ---------- */
$fn = 40;
eps = 0.01;

// =====================================================================
//  DERIVED VALUES -- normally no need to edit below this line
// =====================================================================
C   = panel_clr;
W   = wall_t;
zf  = panel_thk + ledge_gap;                         // ledge front plane
wedge_top_z = zf + ledge_tip + ledge_w;              // wedge height where it meets the wall

roof_under_bz = mp_pcb_t + pod_clear;                // board frame
roof_top_bz   = roof_under_bz + pod_roof_t;
pod_top_z     = portal_pcb_z + roof_top_bz;          // panel frame

frame_back_z = frame_back_z_override > 0 ? frame_back_z_override
             : ceil((pod_top_z + wall_gap_min) * 2) / 2;
flange_front_z = frame_back_z - flange_t;

strap_front_z = zf + ledge_tip + strap_clr;
strap_rear_z  = strap_front_z + strap_t;
rib_h         = strap_front_z - panel_thk - strap_preload;

mp_buttons = include_reset_pusher ? mp_buttons_all
                                  : [for (b = mp_buttons_all) if (b[0] != "RST") b];
tip_min  = min([for (b = mp_buttons) b[2]]);
x_block_in = tip_min - btn_gap - leg_t;              // guide block inner face (board x)
x_block_out = x_block_in - block_len;
rod_top_bz = roof_under_bz - rod_clr;
rod_bz0    = rod_top_bz - rod_h;                     // rod underside (board frame)
btn_y_min  = min([for (b = mp_buttons) b[1]]);
btn_y_max  = max([for (b = mp_buttons) b[1]]);

// Board frame -> panel frame
pr_c = round(cos(portal_rot));
pr_s = round(sin(portal_rot));
function b2p(p) = [hub75_in_xy[0] + pr_c * (p[0] - mp_socket_c[0]) - pr_s * (p[1] - mp_socket_c[1]),
                   hub75_in_xy[1] + pr_s * (p[0] - mp_socket_c[0]) + pr_c * (p[1] - mp_socket_c[1]),
                   portal_pcb_z + (len(p) > 2 ? p[2] : 0)];

// Distance from the socket centre to the OUTER face of the frame wall the
// button/USB edge points at (along the board's -x direction).
edge_dist = portal_rot == 0   ? hub75_in_xy[0] + C + W
          : portal_rot == 90  ? hub75_in_xy[1] + C + W
          : portal_rot == 180 ? panel_w + C + W - hub75_in_xy[0]
          :                     panel_h + C + W - hub75_in_xy[1];
wall_out_bx = mp_socket_c[0] - edge_dist;            // board-frame x of that wall's outer face
x_pad_in    = wall_out_bx - pad_gap;

// Pod footprint (board frame) and its panel-frame bounding box
pod_x0 = x_block_out;
pod_x1 = mp_pcb[0] + pod_margin + pod_skirt_t;
pod_y0 = -pod_margin - pod_skirt_t;
pod_y1 = mp_pcb[1] + pod_margin + pod_skirt_t;
_pc = [for (p = [[pod_x0, pod_y0], [pod_x1, pod_y0], [pod_x0, pod_y1], [pod_x1, pod_y1]]) b2p(p)];
pod_bb_lo = [min([for (p = _pc) p[0]]), min([for (p = _pc) p[1]])];
pod_bb_hi = [max([for (p = _pc) p[0]]), max([for (p = _pc) p[1]])];

// ---------------- sanity checks (printed in the OpenSCAD console) ----------------
assert(portal_rot == 0 || portal_rot == 90 || portal_rot == 180 || portal_rot == 270,
       "portal_rot must be 0, 90, 180 or 270");
assert(pod_clear > mp_top_max + 0.5, "pod_clear too small for the IDC shroud");
assert(rod_bz0 - rod_clr - block_floor > 0, "rods too low: raise pod_clear");
assert(wall_out_bx < x_block_out - 2, "HUB75 position puts the board edge outside the frame");

module _warn(cond, msg) { if (cond) echo(str("<b>WARNING:</b> ", msg)); }
module run_checks() {
    _warn(portal_pcb_z + rod_bz0 < strap_rear_z + 1,
          "push-rods would hit the rear straps; increase pod_clear");
    _warn(pod_top_z > flange_front_z - 1, "pod roof reaches the wall flange");
    _warn(pod_bb_lo[0] < C + flange_w || pod_bb_hi[0] > panel_w - C - flange_w
          || pod_bb_lo[1] < C + flange_w || pod_bb_hi[1] > panel_h - C - flange_w,
          "pod is inside the rear-flange band; check for collisions in assembly.scad");
    for (sx = strap_xs) {
        _warn(sx - strap_w/2 < ledge_w + 1 || sx + strap_w/2 > panel_w - ledge_w - 1,
              str("strap at x=", sx, " overlaps a side ledge"));
        _warn(abs(sx - seam_x) < boss_len/2 + strap_w/2 + 1,
              str("strap at x=", sx, " hits the seam boss"));
        _warn(sx + strap_w/2 > pod_bb_lo[0] - 2 && sx - strap_w/2 < pod_bb_hi[0] + 2,
              str("strap at x=", sx, " crosses the MatrixPortal/pod footprint"));
        _warn(len([for (h = panel_holes) if (abs(h[0] - sx) < strap_slot_w/2) 1]) == 0,
              str("no panel_holes entry lines up with the strap at x=", sx));
    }
    _warn(len([for (sx = strap_xs) if (sx < seam_x) 1]) == 0 ||
          len([for (sx = strap_xs) if (sx > seam_x) 1]) == 0,
          "each frame half needs at least one strap");
    echo(str("frame_back_z = ", frame_back_z, " mm (total frame depth ",
             frame_back_z + face_proud, " mm)"));
}
