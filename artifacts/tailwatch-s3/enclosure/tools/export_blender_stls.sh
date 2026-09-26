#!/usr/bin/env bash
# Regenerate the ASSEMBLY-POSITION STLs under enclosure/blender_import/ from
# the *_positioned.scad wrapper files there. Each wrapper applies the exact
# transform assembly() uses (tailwatch_lib.scad) around one part's raw module
# at explode=0 -- these are NOT the print-orientation STLs in stl/.
#
# Run from anywhere:
#     artifacts/tailwatch-s3/enclosure/tools/export_blender_stls.sh
set -euo pipefail
cd "$(dirname "$0")/../blender_import"

OPENSCAD=${OPENSCAD:-openscad}
PARTS="frame_left frame_right strap_1 strap_2 portal_pod button_rods bowtie_key_1 bowtie_key_2 panel_dummy portal_dummy"

for p in $PARTS; do
    echo "== $p"
    $OPENSCAD -o "$p.stl" "${p}_positioned.scad"
done

echo "== done; run tools/blender_build.py in Blender to rebuild the .blend / previews / glb"
