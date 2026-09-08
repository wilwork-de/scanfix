#!/usr/bin/env python3
"""
Turn a photograph of a document into something that looks scanned.

The problem it solves: when you photograph a sheet of paper the light is never
even. One half catches the lamp, the other stays in shadow, and the result is a PDF
whose top looks like a document and whose bottom looks like a snapshot. Raising the
brightness of the whole image does not help: it lightens the text too and washes out
the half that was already fine.

The right technique is called flat-field correction, and it is what scanner apps do:

  1. Estimate the illumination. Blurring the image hard makes the text and the
     signature disappear and leaves only the way light fell across the sheet: a map
     that is bright where the lamp was and dark in the shadow.
  2. DIVIDE the original by that map. Where the paper was dark you divide by a small
     number and brighten a lot; where it was already bright you divide by a large one
     and almost nothing changes. The shadow goes, and the contrast between ink and
     paper survives everywhere.

It is a local correction, not a global one: every area is treated according to the
light it actually received. That is why it works where plain brightness fails.

The second thing it fixes is geometry. A sheet photographed at an angle is a
trapezoid, not a rotated rectangle, so no single rotation angle can straighten it.
See straighten() below.

Usage:
    python3 clean_scan.py photo.jpg -o clean.pdf
    python3 clean_scan.py scan.pdf -o clean.pdf --colour
    python3 clean_scan.py photo.jpg --no-straighten --no-fit -o raw.pdf
"""

import argparse
import io
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image, ImageFilter, ImageOps

A4 = (595.276, 841.890)
MARGIN = 18.0


def load(path: Path) -> Image.Image:
    """Accept either an image or a PDF whose page is a full-page photograph."""
    if path.suffix.lower() == ".pdf":
        doc = pymupdf.open(path)
        page = doc[0]
        images = page.get_images(full=True)
        if images:
            # Take the original embedded image rather than re-rendering the page:
            # re-rendering would add a second round of lossy compression.
            info = doc.extract_image(images[0][0])
            return Image.open(io.BytesIO(info["image"]))
        raise SystemExit("This PDF holds text, not a photograph: nothing to clean.")
    return Image.open(path)


def light_field(grey: np.ndarray, radius_rel: float = 0.045) -> np.ndarray:
    """Estimate the illumination by blurring all the content away.

    The radius is proportional to the width: it must be far larger than a letter,
    or it blurs the text and erases it along with the shadow, and far smaller than
    the sheet, or it stops following the gradient of the light. Four to five per
    cent of the width is the compromise that holds up on photographed A4 pages.
    """
    h, w = grey.shape
    # astype(uint8): from a float array Pillow builds an image in mode "F", which
    # GaussianBlur refuses. It needs 8 bits per channel, that is mode "L".
    small = Image.fromarray(grey.astype(np.uint8)).resize(
        (max(w // 8, 1), max(h // 8, 1)), Image.BILINEAR)
    small = small.filter(ImageFilter.GaussianBlur(radius=max(radius_rel * w / 8, 2)))
    return np.asarray(small.resize((w, h), Image.BILINEAR), dtype=np.float32)


def _flattened(img: Image.Image) -> Image.Image:
    """Greyscale with the illumination already corrected: the basis for measuring."""
    g = np.asarray(img.convert("L"), dtype=np.float32)
    return Image.fromarray(
        np.clip(g * (255.0 / np.maximum(light_field(g), 1.0)), 0, 255).astype(np.uint8))


def text_line_angle(im: Image.Image, limit=6.0) -> float:
    """Slant of the text lines, by the projection-profile method.

    The test image is rotated through a range of angles and for each one the dark
    pixels are summed row by row. When the text lines are horizontal that sum is
    spiky — full rows alternating with empty leading. When they are slanted the text
    smears across rows and the profile flattens out. Maximising the differences
    between neighbouring values finds the angle without recognising a single letter.

    A coarse half-degree pass locates the region, then a twentieth-of-a-degree pass
    refines it: searching fine across the whole range would cost twenty times as
    much for the same answer.
    """
    im = im.resize((700, max(int(700 * im.height / im.width), 40)), Image.BILINEAR)

    def score(a):
        r = np.asarray(im.rotate(a, resample=Image.BILINEAR, fillcolor=255), dtype=np.float32)
        return float((np.diff((255.0 - r).sum(axis=1)) ** 2).sum())

    coarse = max((score(a), a) for a in np.arange(-limit, limit + 0.01, 0.5))[1]
    return max((score(a), a) for a in np.arange(coarse - 0.6, coarse + 0.61, 0.05))[1]


def _one_pass(img: Image.Image):
    """One pass of perspective straightening, derived from the text itself.

    A sheet photographed at an angle is a trapezoid, not a rotated rectangle: on the
    case this was built for, the slant of the text lines went from 0.00 degrees at
    the top to 1.00 at the bottom. A single rotation cannot fix that, because there
    is no one angle that is right for the whole page.

    The edge of the sheet is not needed — and often is not there, because the photo
    has already been cropped or the background is as bright as the paper. The
    bounding box of the text plus two measured angles, one high and one low, are
    enough to reconstruct the actual trapezoid and map it back to a rectangle. A
    projective transform is fully determined by four points, and it redistributes
    the intermediate slant on its own.
    """
    flat = _flattened(img)
    W, H = flat.size
    ink = np.asarray(flat) < 170
    rows = np.flatnonzero(ink.sum(axis=1) > 3)
    cols = np.flatnonzero(ink.sum(axis=0) > 3)
    if len(rows) < 20 or len(cols) < 20:
        return img, 0.0
    y0, y1, x0, x1 = rows[0], rows[-1], cols[0], cols[-1]

    top = np.radians(text_line_angle(flat.crop((0, int(H * 0.08), W, int(H * 0.35)))))
    bottom = np.radians(text_line_angle(flat.crop((0, int(H * 0.65), W, int(H * 0.95)))))
    width = x1 - x0

    source = [(x0, y0), (x1, y0 + width * np.tan(top)),
              (x1, y1 + width * np.tan(bottom)), (x0, y1)]
    target = [(0, 0), (width, 0), (width, y1 - y0), (0, y1 - y0)]

    # PIL wants the coefficients of the target-to-source map: for each output pixel
    # it says where to take the colour from in the input.
    A, B = [], []
    for (xd, yd), (xs, ys) in zip(target, source):
        A += [[xd, yd, 1, 0, 0, 0, -xs * xd, -xs * yd],
              [0, 0, 0, xd, yd, 1, -ys * xd, -ys * yd]]
        B += [xs, ys]
    coeffs = np.linalg.solve(np.array(A, dtype=float), np.array(B, dtype=float))

    fill = (255, 255, 255) if img.mode == "RGB" else 255
    out = img.transform((width, y1 - y0), Image.PERSPECTIVE, coeffs, Image.BICUBIC,
                        fillcolor=fill)
    return out, abs(np.degrees(bottom - top))


def straighten(img: Image.Image, passes=3, threshold=0.15, verbose=True) -> Image.Image:
    """Apply the correction until the residual fan-out is negligible.

    It iterates because a single pass leaves a residual: the angles are estimated on
    an image that is still distorted, so the estimate is approximate. Re-measuring
    on the already-corrected image brings it below a tenth of a degree. Below
    'threshold' it stops, because going further would resample the pixels again for
    a gain nobody can see.

    Measured on the original case: 1.05 -> 0.25 -> 0.00 degrees.
    """
    for i in range(passes):
        img, fan = _one_pass(img)
        if verbose:
            print(f"  straighten, pass {i + 1}: fan-out {fan:.2f} degrees")
        if fan < threshold:
            break

    # Straightening crops to the bounding box of the TEXT, so it takes the sheet's
    # margins with it and the document comes out with its lines against the edge. A
    # margin proportional to the width is given back — proportional and not fixed,
    # so it holds at any photo resolution.
    border = int(img.width * 0.06)
    fill = (255, 255, 255) if img.mode == "RGB" else 255
    canvas = Image.new(img.mode, (img.width + 2 * border, img.height + 2 * border), fill)
    canvas.paste(img, (border, border))
    if verbose:
        print(f"  margin restored: {border} px per side")
    return canvas


def clean(img: Image.Image, colour: bool, strength: float) -> Image.Image:
    img = ImageOps.exif_transpose(img)
    grey = np.asarray(img.convert("L"), dtype=np.float32)

    light = np.maximum(light_field(grey), 1.0)

    if colour:
        rgb = np.asarray(img.convert("RGB"), dtype=np.float32)
        # The same correction factor on all three channels: it normalises the light
        # without shifting hues, so a signature in blue ink stays blue.
        out = np.clip(rgb * (255.0 / light)[:, :, None], 0, 255)
    else:
        out = np.clip(grey * (255.0 / light), 0, 255)

    # The paper is even now but greyish. Set a white point and a black point: white
    # at the typical value of the paper (a high percentile), black slightly above
    # zero so the thin strokes of a signature are not crushed into a blob.
    reference = out if out.ndim == 2 else out.mean(axis=2)
    white = np.percentile(reference, 92)
    black = np.percentile(reference, 2)
    white = max(white, black + 20)
    # 'strength' pulls the white point down: higher means whiter paper, but above
    # about 1.15 it starts eating light ink.
    white = black + (white - black) / strength

    out = np.clip((out - black) * (255.0 / (white - black)), 0, 255)
    image = Image.fromarray(out.astype(np.uint8), mode="RGB" if colour else "L")
    # A light unsharp mask: the division softens edges a little.
    return image.filter(ImageFilter.UnsharpMask(radius=1.2, percent=55, threshold=3))


def fit_to_a4(img: Image.Image, side=0.07, top=0.035, verbose=True) -> Image.Image:
    """Rebuild around the text the paper that the framing cut away.

    The problem: a phone photo has a ratio around 0.81, A4 has 0.707. Laid on the
    page it fills the width and leaves two white bands above and below, and the
    document looks like it is floating in the middle of the sheet instead of being
    the sheet.

    Cropping to even out the ratio is not an option: it would need more width than
    the blank margins hold, so it would cut into the text. So paper is added rather
    than removed.

    Where to add it is not arbitrary: the margins of a normal document are
    reproduced, seven per cent at the sides and three and a half at the top, and the
    remainder goes to the bottom. That is not an imbalance — a one-page CV that ends
    two thirds down has a lot of white below it, and re-centring the text would make
    it look like a letter instead.
    """
    grey = np.asarray(img.convert("L"), dtype=np.float32)
    ink = grey < 170
    rows = np.flatnonzero(ink.sum(axis=1) > 2)
    cols = np.flatnonzero(ink.sum(axis=0) > 2)
    if len(rows) < 10 or len(cols) < 10:
        return img

    x0, x1, y0, y1 = int(cols[0]), int(cols[-1]), int(rows[0]), int(rows[-1])
    text_w, text_h = x1 - x0, y1 - y0

    canvas_w = round(text_w / (1 - 2 * side))
    canvas_h = round(canvas_w / 0.70711)
    # If the text is too tall to sit with a decent bottom margin, height leads and
    # width follows: wide side margins beat text running off the bottom.
    minimum = round(text_h / (1 - top - 0.04))
    if canvas_h < minimum:
        canvas_h, canvas_w = minimum, round(minimum * 0.70711)

    mx, my = round(canvas_w * side), round(canvas_h * top)
    fill = (255, 255, 255) if img.mode == "RGB" else 255
    canvas = Image.new(img.mode, (canvas_w, canvas_h), fill)
    canvas.paste(img, (mx - x0, my - y0))

    if verbose:
        below = canvas_h - my - text_h
        print(f"  fitted to A4: canvas {canvas_w}x{canvas_h} px "
              f"(ratio {canvas_w / canvas_h:.4f}), margins side {mx} top {my} bottom {below} px")
    return canvas


def to_pdf(img: Image.Image, out: Path, dpi: int, margin: float = MARGIN):
    inches = (A4[0] - 2 * margin) / 72
    width_px = int(inches * dpi)
    if img.width > width_px:
        img = img.resize((width_px, round(img.height * width_px / img.width)),
                         Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85, optimize=True)

    doc = pymupdf.open()
    page = doc.new_page(width=A4[0], height=A4[1])
    page.insert_image(pymupdf.Rect(margin, margin, A4[0] - margin, A4[1] - margin),
                      stream=buf.getvalue(), keep_proportion=True)
    doc.save(str(out), garbage=4, deflate=True)
    doc.close()


def main():
    p = argparse.ArgumentParser(
        description="Photograph of a document -> PDF that looks scanned.")
    p.add_argument("input", help="an image, or a PDF holding the photograph")
    p.add_argument("-o", "--output", default="clean.pdf")
    p.add_argument("--colour", "--color", dest="colour", action="store_true",
                   help="keep the colour (for a signature in blue ink)")
    p.add_argument("--strength", type=float, default=1.06,
                   help="how hard to whiten the paper: 1.0 gentle, 1.15 aggressive")
    p.add_argument("--dpi", type=int, default=200)
    p.add_argument("--no-fit", action="store_true",
                   help="do not rebuild the margins: leave the white bands")
    p.add_argument("--no-straighten", action="store_true",
                   help="skip the perspective correction, keep the page as shot")
    a = p.parse_args()

    src = Path(a.input)
    if not src.is_file():
        p.error(f"file not found: {src}")

    original = load(src)
    real_dpi = original.width / ((A4[0] - 2 * MARGIN) / 72)
    working = original if a.no_straighten else straighten(ImageOps.exif_transpose(original))
    cleaned = clean(working, a.colour, a.strength)

    if a.no_fit:
        to_pdf(cleaned, Path(a.output), a.dpi)
    else:
        # Once fitted, the paper and the page share a ratio, so it goes edge to
        # edge: the margins are already inside the image.
        to_pdf(fit_to_a4(cleaned), Path(a.output), a.dpi, margin=0.0)

    mb = Path(a.output).stat().st_size / 1_048_576
    print(f"Wrote: {a.output}  ({mb:.2f} MB)")
    print(f"Source photo: {original.width}x{original.height} px "
          f"= about {real_dpi:.0f} dpi on the page")
    if real_dpi < 150:
        print("  NOTE: below 150 dpi the text stays soft. Cleaning removes the "
              "shadow but does not invent detail: if you can, retake the photo "
              "framing the sheet alone, with no table around it.")


if __name__ == "__main__":
    main()
