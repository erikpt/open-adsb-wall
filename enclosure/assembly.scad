// TailWatch S3 enclosure -- assembly preview (NOT a printable part).
// Shows every printed part in place on dummy panel / MatrixPortal models.
//   explode = 0      assembled; try 40 for an exploded view
//   upright = true   rotate so the display stands as it hangs on the wall
//                    (world +Z = up, the LED face looks toward world +Y)
include <tailwatch_lib.scad>
explode = 0;
upright = false;
run_checks();
if (upright) rotate([90, 0, 0]) assembly(explode);
else assembly(explode);
