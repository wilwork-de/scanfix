#!/usr/bin/env python3
"""
Cut a handwritten signature out of a photograph and save it as a transparent PNG.

What it is for: it is the missing piece for having a real PDF instead of a
photograph of one. Shooting the whole sheet gives you an image — soft text, heavy
file, no selectable text. Taking only the signature and pasting it onto the original
digital PDF keeps the document crisp and machine-readable, while the signature is
still genuine ink written by hand.

How the strokes are separated from the background: the illumination is corrected
first (the same technique as clean_scan.py), then the ALPHA channel is built from
how dark each pixel is. Light paper becomes transparent, dark ink becomes opaque,
and the values in between stay semi-transparent, which keeps the edges smooth. A
hard threshold would produce a jagged signature that looks obviously cut out.

Usage:
    python3 extract_signature.py signed.pdf -o signature.png
    python3 extract_signature.py photo.jpg --box 0.5,0.75,1.0,0.95 -o signature.png
    python3 extract_signature.py photo.jpg --blue -o signature.png   # keep blue ink
    python3 extract_signature.py photo.jpg --preview grid.png        # pick the box

Then paste it onto the digital document:
    python3 add_date_signature.py document.pdf --signature signature.png
"""

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from clean_scan import light_field, load

# Where a signature sits on a signed document: right half, lower band. Expressed as
# fractions of the page so it holds at any photo resolution.
DEFAULT_BOX = (0.45, 0.70, 1.00, 0.97)


def remove_long_runs(alpha: np.ndarray, fraction: float) -> np.ndarray:
    """Erase the printed rule under the signature, keeping the pen strokes.

    MEASURED, AND IT DOES NOT WORK on a skewed photo — which is why the default is
    0, meaning off. On the case this was built for, the rule was tilted just enough
    that its longest unbroken run inside any single pixel row reached 75 out of 508,
    about 15 per cent, while the signature's own strokes reached 66. The two
    populations overlap, so no threshold removes the rule without eating the
    signature. Separating them properly would mean deskewing and running a line
    detector (Hough), which is another order of complexity.

    It is useful only on a straight scan, where the rule crosses few rows and fills
    them. The clean path is different anyway: sign on a BLANK sheet, where there is
    no rule to separate in the first place.
    """
    limit = max(int(alpha.shape[1] * fraction), 8)
    dark = (alpha > 20).astype(np.int8)
    for y in range(dark.shape[0]):
        edges = np.flatnonzero(np.diff(np.concatenate(([0], dark[y], [0]))))
        for start, end in zip(edges[::2], edges[1::2]):
            if end - start >= limit:
                alpha[y, start:end] = 0
    return alpha


def extract(img: Image.Image, box, light: float, dark: float, blue: bool,
            run_fraction: float = 0.0):
    w, h = img.size
    x0, y0, x1, y1 = (int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h))
    crop = img.crop((x0, y0, x1, y1))

    grey = np.asarray(crop.convert("L"), dtype=np.float32)
    illumination = np.maximum(light_field(grey), 1.0)
    flat = np.clip(grey * (255.0 / illumination), 0, 255)

    # A ramp, not a step: above 'light' it is paper (transparent), below 'dark' it
    # is solid ink (opaque), in between it fades. These are the two numbers to touch
    # if the signature comes out faint (raise 'light') or if background grime
    # survives (lower it).
    alpha = np.clip((light - flat) / max(light - dark, 1.0) * 255.0, 0, 255)

    if run_fraction:
        alpha = remove_long_runs(alpha, run_fraction)

    if blue:
        rgb = np.asarray(crop.convert("RGB"), dtype=np.float32)
        colour = np.clip(rgb * (255.0 / illumination)[:, :, None] * 0.75, 0, 255).astype(np.uint8)
    else:
        colour = np.zeros(flat.shape + (3,), dtype=np.uint8)   # black ink

    out = Image.fromarray(np.dstack([colour, alpha.astype(np.uint8)]), mode="RGBA")

    # Trim to the content: a PNG carrying half a page of transparency around the
    # strokes would scale badly when laid on a signature line.
    bbox = Image.fromarray((alpha > 30).astype(np.uint8) * 255).getbbox()
    if bbox:
        pad = 6
        out = out.crop((max(bbox[0] - pad, 0), max(bbox[1] - pad, 0),
                        min(bbox[2] + pad, out.width), min(bbox[3] + pad, out.height)))
    return out, alpha


def write_grid(img: Image.Image, path: str):
    """Save a copy with a labelled grid, to read the fractions for --box off it.

    Faster than guessing: red lines are x, blue lines are y, every 0.05.
    """
    g = img.convert("RGB").copy()
    d = ImageDraw.Draw(g)
    for i in range(1, 20):
        f = i / 20
        d.line([(f * g.width, 0), (f * g.width, g.height)], fill=(255, 0, 0), width=1)
        d.line([(0, f * g.height), (g.width, f * g.height)], fill=(0, 120, 255), width=1)
        d.text((f * g.width + 2, 2), f"{f:.2f}", fill=(255, 0, 0))
        d.text((2, f * g.height + 2), f"{f:.2f}", fill=(0, 120, 255))
    g.save(path)


def main():
    p = argparse.ArgumentParser(
        description="Extract a signature from a photograph -> transparent PNG.")
    p.add_argument("input", help="photo or PDF of the signed document")
    p.add_argument("-o", "--output", default="signature.png")
    p.add_argument("--box", default=None,
                   help="area to look in, as fractions: x0,y0,x1,y1 (default: lower right)")
    p.add_argument("--light", type=float, default=205.0,
                   help="above this value it is paper; raise it if the signature comes out faint")
    p.add_argument("--dark", type=float, default=95.0,
                   help="below this value it is solid ink")
    p.add_argument("--blue", action="store_true", help="keep the pen colour")
    p.add_argument("--line-fraction", type=float, default=0.0,
                   help="erase horizontal runs longer than this fraction. Only works on a "
                        "straight scan; on a skewed photo it does not, see the code")
    p.add_argument("--preview", default=None,
                   help="save a grid image with the fractions, to choose --box")
    a = p.parse_args()

    src = Path(a.input)
    if not src.is_file():
        p.error(f"file not found: {src}")

    box = DEFAULT_BOX
    if a.box:
        box = tuple(float(v) for v in a.box.split(","))
        if len(box) != 4:
            p.error("--box takes four numbers: x0,y0,x1,y1")

    img = load(src)

    if a.preview:
        write_grid(img, a.preview)
        print(f"Grid saved to {a.preview}: red is x, blue is y.")
        print("Read off the corners of the signature and rerun with --box x0,y0,x1,y1")
        return

    signature, alpha = extract(img, box, a.light, a.dark, a.blue, a.line_fraction)
    signature.save(a.output)

    coverage = float((alpha > 30).mean()) * 100
    print(f"Wrote: {a.output}  ({signature.width}x{signature.height} px)")
    print(f"Ink found in the area: {coverage:.1f}%")
    if coverage < 0.4:
        print("  Almost nothing: the signature is not in that area. Pass --box with the "
              "right fractions, e.g. --box 0.4,0.6,1.0,0.95, or use --preview first.")
    elif coverage > 25:
        print("  Too much: you have caught body text or the shadow of the sheet. "
              "Tighten the box, or lower --light.")
    print("Open it and look before using it: only the signature should be visible, "
          "on a checkerboard (transparent) background.")


if __name__ == "__main__":
    main()
