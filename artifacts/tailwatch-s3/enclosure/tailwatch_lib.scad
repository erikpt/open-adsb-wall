// =====================================================================
//  TailWatch S3 enclosure -- geometry library
//  All modules build parts IN ASSEMBLED POSITION (back-view panel frame,
//  see params.scad).  The per-part files rotate them onto the print bed.
// =====================================================================
include <params.scad>

// ---------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------
module rrect(size, r) {                     // 2D rounded rectangle, corner at origin
    translate([r, r]) offset(r = r) square([size[0] - 2*r, size[1] - 2*r]);
}

// Place children in the MatrixPortal board frame.
module on_board() {
    translate([hub75_in_xy[0], hub75_in_xy[1], portal_pcb_z])
        rotate([0, 0, portal_rot])
            translate([-mp_socket_c[0], -mp_socket_c[1], 0])
                children();
}

// Run a "side feature" along each of the four frame sides.  Children are
// built for the BOTTOM side in local coords: x runs along the side from
// the inner corner (0 .. $L), +y points inward from the inner wall face.
module four_sides() {
    Lx = panel_w + 2*C;  Ly = panel_h + 2*C;
    translate([-C, -C, 0])                          let($L = Lx, $side = "bottom") children();
    translate([panel_w + C, panel_h + C, 0]) rotate(180) let($L = Lx, $side = "top")    children();
    translate([-C, panel_h + C, 0])        rotate(-90) let($L = Ly, $side = "left")   children();
    translate([panel_w + C, -C, 0])        rotate(90)  let($L = Ly, $side = "right")  children();
}

// Extrude a 2D profile given in (inward u, z) along local x for length L.
module along_side(L) {
    rotate([90, 0, 90]) linear_extrude(L) children();
}

// ---------------------------------------------------------------------
// FRAME (full ring; split into halves by frame_half())
// ---------------------------------------------------------------------
module frame_outer_solid() {
    z0 = -face_proud;  ch = 0.8;                    // small chamfer on the front outer edge
    o  = [panel_w + 2*(C + W), panel_h + 2*(C + W)];
    translate([-C - W, -C - W, 0])
    hull() {
        translate([0, 0, z0]) linear_extrude(eps)
            translate([ch, ch]) rrect([o[0] - 2*ch, o[1] - 2*ch], max(frame_corner_r - ch, 0.5));
        translate([0, 0, z0 + ch]) linear_extrude(frame_back_z - z0 - ch) rrect(o, frame_corner_r);
    }
}

module frame_walls() {
    difference() {
        frame_outer_solid();
        translate([-C, -C, -face_proud - 1]) cube([panel_w + 2*C, panel_h + 2*C, frame_back_z + face_proud + 2]);
    }
}

// 45-degree wedge ledge behind the panel edge: flat front face against the
// panel's back shell, sloped rear face -> prints without support rear-down.
module ledge_profile() {
    polygon([[0, zf], [ledge_w, zf], [ledge_w, zf + ledge_tip], [0, zf + ledge_tip + ledge_w]]);
}

module frame_ledges()  { four_sides() along_side($L) ledge_profile(); }

module frame_flange() {
    four_sides() along_side($L) translate([0, flange_front_z]) square([flange_w, flange_t]);
    // widened areas around the keyholes (top side)
    for (kx = keyhole_xs())
        translate([kx - kh_boss_w/2, panel_h + C - kh_boss_d, flange_front_z])
            linear_extrude(flange_t) rrect([kh_boss_w, kh_boss_d + 1], 3);
}

function keyhole_xs() = [seam_x - keyhole_spacing/2, seam_x + keyhole_spacing/2];

// Keyhole: big entry hole low, slot running UP from it (the frame drops onto the screws).
module keyholes() {
    for (kx = keyhole_xs()) {
        yb = panel_h + C - kh_boss_d + kh_head_d/2 + 2;           // entry-hole centre
        translate([kx, yb, flange_front_z - 1]) {
            cylinder(d = kh_head_d, h = flange_t + 2);
            translate([-kh_shank_d/2, 0, 0]) cube([kh_shank_d, kh_slot, flange_t + 2]);
            translate([0, kh_slot, 0]) cylinder(d = kh_shank_d, h = flange_t + 2);
        }
    }
}

// Seam bosses (top and bottom) that carry the bowtie keys.
module seam_bosses() {
    for (s = [0, 1])
        translate([seam_x - boss_len/2, s == 0 ? -C : panel_h + C - boss_d, zf])
            cube([boss_len, boss_d, frame_back_z - zf]);
}

module bowtie_2d(clr = 0) {
    h = bt_len/2 + clr;
    polygon([[-h, -bt_end/2 - clr], [0, -bt_waist/2 - clr], [h, -bt_end/2 - clr],
             [h,  bt_end/2 + clr],  [0,  bt_waist/2 + clr], [-h, bt_end/2 + clr]]);
}

bt_key_len = frame_back_z - zf - 0.5;               // key is 0.5 mm shorter than the pocket

module bowtie_pockets() {
    for (s = [0, 1]) {
        yc = s == 0 ? -C + boss_d/2 - 0.5 : panel_h + C - boss_d/2 + 0.5;
        translate([seam_x, yc, zf - 1]) linear_extrude(frame_back_z - zf + 2) bowtie_2d(bt_clr);
    }
}

// Diamond vents through the top and bottom walls, between wedge and flange.
module vents() {
    zc = (wedge_top_z + flange_front_z) / 2;
    d  = min(vent_d, flange_front_z - wedge_top_z - 1.5);
    if (d > 2)
    for (x = [14 : vent_pitch : panel_w - 14])
        if (abs(x - seam_x) > boss_len/2 + d/2 + 1
            && abs(x - power_notch_x) > power_notch_w/2 + d/2 + 2)
            for (y = [-C - W - 1, panel_h + C - 1])
                translate([x, y, zc]) rotate([0, 45, 0])
                    translate([-d/(2*sqrt(2)), 0, -d/(2*sqrt(2))]) cube([d/sqrt(2), W + 2, d/sqrt(2)]);
}

// Rear-open notch for the panel's 5 V cable (bottom wall).
module power_notch() {
    translate([power_notch_x - power_notch_w/2, -C - W - 1, power_notch_bottom_z])
        cube([power_notch_w, W + max(ledge_w, flange_w) + 2, frame_back_z]);
}

// Rear-open notches for the USB cable and the push-rods, in whichever wall
// the board's button/USB edge faces.  Built in the board frame.
module portal_notches() {
    depth = W + max(ledge_w, flange_w) + 2;
    on_board() {
        // USB-C
        translate([wall_out_bx - 1, mp_usb_y - usb_notch_w/2, mp_usb_bz - usb_notch_dz])
            cube([depth + 1, usb_notch_w, 200]);
        // push-rods
        for (b = mp_buttons)
            translate([wall_out_bx - 1, b[1] - rod_w/2 - rod_clr - 0.2, rod_bz0 - rod_clr])
                cube([depth + 1, rod_w + 2*rod_clr + 0.4, 200]);
    }
}

// Engraved labels on the outside of the frame.
module _eng_text(t) {
    linear_extrude(label_depth + 1)
        text(t, size = label_size, font = "Liberation Sans:style=Bold", halign = "center", valign = "center");
}
module labels() {
    // next to the USB / button notches: baseline along the depth axis
    zc = (-face_proud + portal_pcb_z + rod_bz0 - rod_clr) / 2 - 1;
    items = concat([["USB", mp_usb_y]], [for (b = mp_buttons) [b[0], b[1]]]);
    on_board()
        for (it = items)
            translate([wall_out_bx + label_depth, it[1], zc - portal_pcb_z])
                rotate([0, -90, 0]) rotate(portal_rot == 180 ? 180 : 0) _eng_text(it[0]);
    // under the power notch (bottom wall), readable from below
    translate([power_notch_x, -C - W + label_depth, (power_notch_bottom_z - face_proud)/2])
        rotate([90, 0, 0]) _eng_text("5V");
}

module frame_full() {
    difference() {
        union() {
            frame_walls();
            frame_ledges();
            frame_flange();
            seam_bosses();
        }
        keyholes();
        bowtie_pockets();
        vents();
        power_notch();
        portal_notches();
        labels();
    }
}

// side = 0 -> left half (x < seam_x), 1 -> right half
module frame_half(side) {
    big = 1000;
    intersection() {
        frame_full();
        translate([side == 0 ? -big + seam_x : seam_x, -big/2, -big/2]) cube(big);
    }
}

// Bowtie key, standing (print orientation = as built)
module bowtie_key() { linear_extrude(bt_key_len) bowtie_2d(0); }

// ---------------------------------------------------------------------
// REAR STRAP (one per strap_xs entry; all identical)
// ---------------------------------------------------------------------
strap_y0 = -C + ledge_w - strap_overlap;              // strap spans y = strap_y0 .. panel_h - strap_y0
strap_len = panel_h - 2*strap_y0;
rib_y0 = -C + ledge_w + 1;

// Envelope of the ledge wedges (plus clearance) -- subtracted from the strap
// ends so they sit on the 45-degree slope.
module wedge_envelope() {
    for (s = [0, 1]) {
        yw = s == 0 ? -C : panel_h + C;
        translate([0, yw, 0]) mirror([0, s, 0])
            translate([-50, 0, 0]) along_side(panel_w + 100)
                offset(delta = strap_clr) ledge_profile();
    }
}

// strap in assembled position, centred on x = 0
module strap_raw() {
    difference() {
        union() {
            translate([-strap_w/2, strap_y0, strap_front_z]) cube([strap_w, strap_len, strap_t]);
            // rib that bears on the panel back shell
            translate([-strap_w/2, rib_y0, strap_front_z - rib_h]) cube([strap_w, panel_h - 2*rib_y0, rib_h + eps]);
        }
        wedge_envelope();
        // long slot for the M3 screws into the panel posts
        hull() for (y = [rib_y0 + 5, panel_h - rib_y0 - 5])
            translate([0, y, 0]) cylinder(d = strap_slot_w, h = 100);
        // "TOP" arrow is not needed: the strap is symmetric.
    }
}

// ---------------------------------------------------------------------
// MATRIXPORTAL POD (board frame; attaches with 4x M2.5 screws from below)
// ---------------------------------------------------------------------
module pod_raw() {
    by0 = btn_y_min - rod_w/2 - 2;
    by1 = btn_y_max + rod_w/2 + 2.5;
    difference() {
        union() {
            // roof
            translate([pod_x0, pod_y0, roof_under_bz])
                linear_extrude(pod_roof_t) rrect([pod_x1 - pod_x0, pod_y1 - pod_y0], 2);
            // skirts on the two long sides and the IDC end (USB/button side left open)
            skz = mp_pcb_t + pod_skirt_gap;
            for (y = [pod_y0, pod_y1 - pod_skirt_t])
                translate([pod_x0, y, skz]) cube([pod_x1 - pod_x0, pod_skirt_t, roof_under_bz - skz + eps]);
            translate([pod_x1 - pod_skirt_t, pod_y0, skz]) cube([pod_skirt_t, pod_y1 - pod_y0, roof_under_bz - skz + eps]);
            // posts onto the 4 mounting holes
            for (h = mp_holes)
                translate([h[0], h[1], mp_pcb_t]) cylinder(d = pod_post_d, h = roof_under_bz - mp_pcb_t + eps);
            // push-rod guide block
            translate([x_block_out, by0, rod_bz0 - rod_clr - block_floor])
                cube([block_len, by1 - by0, roof_under_bz - (rod_bz0 - rod_clr - block_floor) + eps]);
        }
        // screw pilots
        for (h = mp_holes)
            translate([h[0], h[1], mp_pcb_t - 1]) cylinder(d = pod_pilot_d, h = pod_pilot_depth + 1);
        // rod tunnels
        for (b = mp_buttons)
            translate([x_block_out - 1, b[1] - rod_w/2 - rod_clr, rod_bz0 - rod_clr])
                cube([block_len + 2, rod_w + 2*rod_clr, rod_h + 2*rod_clr]);
        // roof vents over the ESP32 / level shifters (vertical holes, no bridging)
        for (x = [15 : 5 : 45])
            hull() for (y = [19.5, 32]) translate([x, y, roof_under_bz - 1]) cylinder(d = 2.6, h = pod_roof_t + 2, $fn = 16);
        // name on the roof
        translate([(pod_x0 + pod_x1)/2 - 4, 8, roof_top_bz - 0.6])
            linear_extrude(1) text("TailWatch", size = 5, font = "Liberation Sans:style=Bold",
                                   halign = "center", valign = "center");
        // button labels on the guide block's outer face
        for (b = mp_buttons)
            translate([x_block_out + 0.6, b[1], rod_bz0 - rod_clr - block_floor + 0.1])
                rotate([0, -90, 0]) rotate(90) linear_extrude(1)
                    text(b[0] == "RST" ? "R" : b[0] == "UP" ? "U" : "D", size = 1.2,
                         halign = "center", valign = "bottom");
    }
}

// ---------------------------------------------------------------------
// PUSH-RODS (profile in board x/z, extruded rod_w along board y)
// ---------------------------------------------------------------------
module rod_profile(tip) {
    xc   = tip - btn_gap;                        // contact face
    legt = leg_t + (tip - tip_min);              // all leg backs line up with the guide block
    union() {
        translate([xc - legt, leg_bot_bz]) square([legt, rod_top_bz - leg_bot_bz]);
        translate([x_pad_in, rod_bz0]) square([xc - x_pad_in, rod_h]);
        translate([x_pad_in - pad_t, rod_bz0 - pad_drop]) square([pad_t, rod_h + pad_drop]);
    }
}

module rod_raw(b) {       // assembled position, board frame
    translate([0, b[1] + rod_w/2, 0]) rotate([90, 0, 0]) linear_extrude(rod_w) rod_profile(b[2]);
}

// ---------------------------------------------------------------------
// DUMMIES for the assembly preview (not printed)
// ---------------------------------------------------------------------
module panel_dummy() {
    color([0.12, 0.12, 0.14]) difference() {
        cube([panel_w, panel_h, panel_thk]);
        translate([3, 3, 2.5]) cube([panel_w - 6, panel_h - 6, panel_thk]);   // hollow back shell
    }
    color([0.9, 0.3, 0.1]) translate([0, 0, -0.3]) cube([panel_w, panel_h, 0.3]);   // LED face
    for (h = panel_holes) color("gold") translate([h[0], h[1], 2.5]) difference() {
        cylinder(d = 6, h = panel_thk - 2.5); cylinder(d = panel_hole_d, h = 50);
    }
    // HUB75 input box header on the panel PCB
    on_board() color([0.2, 0.2, 0.2])
        translate([mp_socket_c[0] - 4.45, mp_socket_c[1] - 15.3, 2.5 - portal_pcb_z])
            cube([8.9, 30.6, portal_pcb_z - 2.5 - 0.5]);
}

module portal_dummy() {
    on_board() {
        color([0.1, 0.1, 0.1]) difference() {
            linear_extrude(mp_pcb_t) rrect(mp_pcb, mp_corner_r);
            for (h = mp_holes) translate([h[0], h[1], -1]) cylinder(d = mp_hole_d, h = 5);
        }
        color("dimgray") translate([mp_idc_lo[0], mp_idc_lo[1], mp_pcb_t])
            cube([mp_idc_hi[0] - mp_idc_lo[0], mp_idc_hi[1] - mp_idc_lo[1], mp_top_max]);
        color("silver") translate([17.3, 18.5, mp_pcb_t]) cube([25.5, 18, 3.3]);        // ESP32-S3 module
        color("silver") translate([0.03, mp_usb_y - 4.47, mp_pcb_t]) cube([7.35, 8.94, 3.2]);   // USB-C
        for (b = mp_buttons_all) color("white") translate([0.3, b[1] - 3.4, mp_pcb_t]) cube([3.4, 6.8, 3.4]);
        for (b = mp_buttons_all) color("black") translate([b[2], b[1] - 1.5, 2.2]) cube([0.5 - b[2], 3, 2.4]);
        color("gray") translate([mp_socket_c[0] - mp_socket[0]/2, mp_socket_c[1] - mp_socket[1]/2, -mp_socket[2]])
            cube([mp_socket[0], mp_socket[1], mp_socket[2]]);
    }
}
