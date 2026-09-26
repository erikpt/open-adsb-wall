// TailWatch S3 enclosure -- bowtie key #1 (bottom seam boss, s=0), ASSEMBLY position.
include <../tailwatch_lib.scad>
translate([seam_x, -C + boss_d/2 - 0.5, zf + 0.25]) bowtie_key();
