"""Generate firmware/lib/badapple_frames.py from a source video clip (issue #30).

Host-only build tool (desktop python3, stdlib only); NOT copied to CIRCUITPY,
and its source video is NOT committed to this repo (deliberately -- the
output of this script, committed Python frame data, is what ships; the raw
clip is only ever a local, throwaway input to a one-off regeneration).

Needs `ffmpeg` on PATH (system binary, same spirit as enclosure/tools needing
openscad/blender) to decode/scale/threshold frames; everything else here is
stdlib. Sibling of tools/gen_badges.py and tools/convert_logos.py, which have
the same "host-only, output committed" shape for lib/logos/*.bmp.

  python3 tools/gen_badapple.py --source clip.mp4 --start 178 --duration 24

Pipeline
--------
1. ffmpeg decodes the clip, scales each frame to fit WIDTHxHEIGHT preserving
   aspect ratio (pillarboxed/letterboxed with black bars, same idea as
   lib/nyan.py's sprite sitting inset in its canvas rather than full-bleed),
   and emits raw 8-bit grayscale frames at the chosen --fps.
2. Each pixel thresholds to 1 bit at value 128 -- Bad Apple's shadow-puppet
   style source is already essentially binary, so a fixed midpoint threshold
   (no per-frame Otsu/adaptive logic) is enough; "on" follows the source's
   own brightness (a frame with a white background and black silhouette
   encodes mostly-on with an off silhouette, and vice versa on the black-
   background shots -- same as the real video, not normalized to one polarity).
3. Each frame is run-length encoded, one byte per run (0-128 fits a single
   byte since WIDTH <= 255), concatenated for the whole frame with NO row
   separators: lib/badapple.py's decoder infers a row boundary every time
   the running pixel count hits WIDTH and resets to "off" for the next row,
   so there is nothing to desync as long as every row truly sums to WIDTH
   (guaranteed here by construction). This is what makes Bad Apple's
   large, smooth silhouette regions compress to a few hundred bytes/frame
   instead of the raw 8192 (WIDTH*HEIGHT bits/8) a bitmap would cost.

Output is a single firmware/lib/badapple_frames.py with WIDTH, HEIGHT, FPS,
and a FRAMES tuple of bytes literals -- plain committed Python source, no
separate binary asset file, so CircuitPython loads it exactly like any other
lib/*.py module (same "pure code, not a shipped video file" idea issue #30's
discussion landed on).
"""
import argparse
import os
import subprocess
import sys

WIDTH = 128
HEIGHT = 64
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(HERE, "..", "firmware", "lib", "badapple_frames.py")


def extract_frames(source, start, duration, fps):
    """[frame_bytes, ...], each exactly WIDTH*HEIGHT grayscale bytes."""
    # Fit within a WIDTHxHEIGHT box at the source's own aspect ratio (a
    # 4:3-ish shadow-animation clip into a 2:1 panel needs pillarbars either
    # way); scale's force_original_aspect_ratio does the fitting, pad adds
    # the bars to reach exactly WIDTHxHEIGHT.
    vf = (
        "fps=%d,scale=%d:%d:force_original_aspect_ratio=decrease,"
        "pad=%d:%d:(ow-iw)/2:(oh-ih)/2:color=black,format=gray"
        % (fps, WIDTH, HEIGHT, WIDTH, HEIGHT)
    )
    cmd = [
        "ffmpeg", "-y", "-ss", str(start), "-i", source, "-t", str(duration),
        "-vf", vf, "-f", "rawvideo", "-pix_fmt", "gray", "-",
    ]
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    except FileNotFoundError:
        print("ffmpeg not found on PATH -- see this script's docstring", file=sys.stderr)
        raise
    except subprocess.CalledProcessError as e:
        print(e.stderr.decode("utf-8", "replace"), file=sys.stderr)
        raise
    data = p.stdout
    frame_size = WIDTH * HEIGHT
    n = len(data) // frame_size
    return [data[i * frame_size:(i + 1) * frame_size] for i in range(n)]


def rle_encode(frame, width=WIDTH, height=HEIGHT, threshold=128):
    """Grayscale frame bytes -> one run-length-encoded bytes object.

    See this module's docstring for the row-wrap scheme lib/badapple.py
    decodes. Each run is 1 byte (0-128); the per-row total always sums to
    exactly `width`, by construction (the inner loop always closes out
    width pixels before moving to the next row).
    """
    runs = bytearray()
    for row in range(height):
        base = row * width
        color = 0  # every row starts "off" by convention
        run = 0
        for col in range(width):
            on = 1 if frame[base + col] >= threshold else 0
            if on == color:
                run += 1
            else:
                runs.append(run)
                color = on
                run = 1
        runs.append(run)
    return bytes(runs)


def write_module(frames_rle, fps, out_path=OUT_PATH):
    with open(out_path, "w") as f:
        f.write(
            '"""Bad Apple!! (shadow animation) frame data for lib/badapple.py '
            "(issue #30).\n\n"
            "Generated by tools/gen_badapple.py -- do not hand-edit. Each "
            "entry in FRAMES is one\n"
            "run-length-encoded %dx%d frame; see that script's docstring "
            "for the encoding and\nlib/badapple.py for the decoder/player. "
            'Source clip is not tracked in this repo.\n"""\n' % (WIDTH, HEIGHT)
        )
        f.write("WIDTH = %d\n" % WIDTH)
        f.write("HEIGHT = %d\n" % HEIGHT)
        f.write("FPS = %d\n\n" % fps)
        f.write("FRAMES = (\n")
        for rle in frames_rle:
            f.write("    %r,\n" % rle)
        f.write(")\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True, help="path to the local source video clip")
    ap.add_argument("--start", type=float, default=178.0, help="clip start, seconds")
    ap.add_argument("--duration", type=float, default=24.0, help="clip length, seconds")
    ap.add_argument("--fps", type=int, default=12, help="playback frame rate")
    ap.add_argument("--out", default=OUT_PATH, help="output path (default: firmware/lib/badapple_frames.py)")
    args = ap.parse_args()

    frames = extract_frames(args.source, args.start, args.duration, args.fps)
    if not frames:
        print("ffmpeg produced no frames -- check --source/--start/--duration", file=sys.stderr)
        sys.exit(1)
    encoded = [rle_encode(f) for f in frames]
    write_module(encoded, args.fps, args.out)
    total = sum(len(e) for e in encoded)
    print("%d frames, %d bytes raw RLE, %d bytes written to %s" % (
        len(encoded), total, os.path.getsize(args.out), args.out))


if __name__ == "__main__":
    main()
