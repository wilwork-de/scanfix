#!/usr/bin/env python3
"""
Print what the Python tools compute on a synthetic page, so the JavaScript port can
be checked against it.

tests/test_imaging.mjs builds the same image pixel for pixel and asserts these
numbers with a tolerance. They are written into that file by hand rather than read
from here, so the JavaScript suite runs without Python; this script is how you
re-derive them if the Python side ever changes.

    .venv/bin/python tests/imaging_reference.py
"""

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from clean_scan import light_field, text_line_angle          # noqa: E402

W, H = 320, 240


def page():
    """A lit-from-one-corner sheet with a few lines of 'text' on it."""
    yy, xx = np.mgrid[0:H, 0:W]
    img = 120 + 110 * (1 - (xx / W) * 0.7 - (yy / H) * 0.55)
    for row in range(30, H - 30, 24):
        img[row:row + 6, 30:W - 40] -= 130
    return np.clip(img, 0, 255).astype(np.uint8)


def main():
    grey = page().astype(np.float32)
    light = light_field(grey)
    flat = np.clip(grey * (255.0 / np.maximum(light, 1.0)), 0, 255)
    alpha = np.clip((205.0 - flat) / 110.0 * 255.0, 0, 255)

    print(f"lightMean      {light.mean():.4f}")
    print(f"flatMean       {flat.mean():.4f}")
    print(f"alphaMean      {alpha.mean():.4f}")
    print(f"alphaCoverage  {(alpha > 30).mean() * 100:.4f}")
    print(f"p2             {np.percentile(flat, 2):.4f}")
    print(f"p92            {np.percentile(flat, 92):.4f}")

    ink = flat < 170
    rows = np.flatnonzero(ink.sum(axis=1) > 2)
    cols = np.flatnonzero(ink.sum(axis=0) > 2)
    print(f"inkBox         {cols[0]} {rows[0]} {cols[-1]} {rows[-1]}")

    # The angle, measured on a page tilted by a known amount.
    tilted = Image.fromarray(page()).rotate(-1.5, resample=Image.BILINEAR, fillcolor=255)
    print(f"tiltAngle      {text_line_angle(tilted):.4f}")

    lut = ImageOps.autocontrast(Image.fromarray(page()), cutoff=(1, 6))
    out = np.asarray(lut, dtype=np.int32)
    print(f"autocontrast   {out.min()} {out.max()} {out.mean():.4f}")


if __name__ == "__main__":
    main()
