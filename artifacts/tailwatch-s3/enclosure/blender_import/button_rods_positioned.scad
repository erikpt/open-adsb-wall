// TailWatch S3 enclosure -- button_rods (all 3: DN, UP, RST), ASSEMBLY position.
include <../tailwatch_lib.scad>
on_board() for (b = mp_buttons) rod_raw(b);
