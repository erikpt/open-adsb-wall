#!/usr/bin/env bash
# Rebuild every STL and preview PNG for the TailWatch S3 enclosure, then
# check the STLs (bed fit + manifold).  Run from anywhere:
#     artifacts/tailwatch-s3/enclosure/tools/build.sh
# Needs: openscad (2021.01+), python3; xvfb-run for PNGs on a headless box.
set -euo pipefail
cd "$(dirname "$0")/.."

OPENSCAD=${OPENSCAD:-openscad}
XVFB=""
if [ -z "${DISPLAY:-}" ] && command -v xvfb-run >/dev/null; then XVFB="xvfb-run -a"; fi
# Printer build volume (X Y Z, mm) -- keep in sync with `bed` in params.scad
BED="200 200 250"
PARTS="frame_left frame_right strap portal_pod button_rods bowtie_keys"
mkdir -p stl preview logs

for p in $PARTS; do
    echo "== $p"
    $OPENSCAD -o "stl/$p.stl" "$p.scad" > "logs/$p.log" 2>&1 || { cat "logs/$p.log"; exit 1; }
    grep -E "WARNING|ERROR|Simple:|Volumes:|Vertices:|Facets:" "logs/$p.log" || true
    $XVFB $OPENSCAD --render -o "preview/$p.png" --imgsize=1000,800 --viewall --autocenter \
        --camera=0,0,0,55,0,25,0 --colorscheme=Tomorrow "$p.scad" > /dev/null 2>&1
done

echo "== assembly previews"
# upright = wall-hung orientation: world X = panel back-view X, world Z = up,
# LED face toward +Y.  Eye positions are [x, y, z] -> look-at centre.
$XVFB $OPENSCAD -o preview/assembly_back.png  --imgsize=1400,1000 --colorscheme=Tomorrow \
    -D upright=true --camera=470,-560,380,128,-15,64 assembly.scad > logs/assembly.log 2>&1
$XVFB $OPENSCAD -o preview/assembly_front.png --imgsize=1400,1000 --colorscheme=Tomorrow \
    -D upright=true --camera=-170,640,260,128,-15,64 assembly.scad > /dev/null 2>&1
$XVFB $OPENSCAD -o preview/assembly_exploded.png --imgsize=1400,1000 --colorscheme=Tomorrow \
    -D explode=40 --camera=128,64,30,55,0,-35,820 assembly.scad > /dev/null 2>&1
$XVFB $OPENSCAD -o preview/detail_buttons.png --imgsize=1200,900 --colorscheme=Tomorrow \
    --camera=40,82,25,60,0,-60,200 assembly.scad > /dev/null 2>&1
grep -E "WARNING|frame_back_z" logs/assembly.log || true

echo "== STL checks"
python3 tools/check_stl.py --bed $BED stl/*.stl
