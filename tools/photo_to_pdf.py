#!/usr/bin/env python3
"""
Turn photographs (or scans) of a document into an uploadable A4 PDF.

For when you printed something, signed it by hand and photographed it: the portal
wants a PDF, not a JPG, and a photo dropped into a PDF unprocessed weighs 8 MB,
comes out crooked and keeps the paper grey.

What it does, in order:
  1. rotates by the EXIF orientation — phone photos are almost always rotated in
     the metadata rather than in the pixels, so some viewers turn them and others
     do not, and your document arrives lying on its side;
  2. converts to greyscale — a document has no colour worth keeping, and grey cuts
     the weight by about two thirds;
  3. flattens the white of the paper, so the background does not stay beige;
  4. resamples to the chosen resolution (200 dpi is plenty for printed text);
  5. lays it out on A4 with a margin, one photo per page;
  6. compresses to JPEG, stepping the resolution down until it fits the size cap.

For heavier correction — uneven lighting, perspective — use clean_scan.py instead.
This one is the straight conversion.

Usage:
    python3 photo_to_pdf.py photo.jpg -o signed.pdf
    python3 photo_to_pdf.py page1.jpg page2.jpg -o signed.pdf --max-mb 1.5
    python3 photo_to_pdf.py scan.png --colour
"""

import argparse
import io
from pathlib import Path

import pymupdf
from PIL import Image, ImageOps

A4 = (595.276, 841.890)      # typographic points, 1 pt = 1/72 inch
MARGIN = 18.0


def prepare(path: Path, dpi: int, colour: bool, flatten_white: bool) -> bytes:
    """Open, straighten and normalise the image. Returns a JPEG in memory."""
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)          # metadata rotation -> pixels

    if not colour:
        img = img.convert("L")
        if flatten_white:
            # Autocontrast with the tails clipped: takes the paper to full white and
            # the ink to black, which is what a scanner app does. The cutoff is low
            # because clipping too hard eats thin pencil strokes and faint signatures.
            img = ImageOps.autocontrast(img, cutoff=(1, 6))
    else:
        img = img.convert("RGB")

    # Usable width on the A4 page in inches, to size the image for that resolution.
    inches = (A4[0] - 2 * MARGIN) / 72
    width_px = int(inches * dpi)
    if img.width > width_px:
        height = round(img.height * width_px / img.width)
        img = img.resize((width_px, height), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82, optimize=True)
    return buf.getvalue()


def build(images, out: Path, dpi: int, colour: bool, flatten_white: bool):
    doc = pymupdf.open()
    for path in images:
        data = prepare(path, dpi, colour, flatten_white)
        page = doc.new_page(width=A4[0], height=A4[1])
        frame = pymupdf.Rect(MARGIN, MARGIN, A4[0] - MARGIN, A4[1] - MARGIN)
        # keep_proportion avoids squashing: a squashed page is immediately visible
        # and makes the document look manipulated.
        page.insert_image(frame, stream=data, keep_proportion=True)
    doc.save(str(out), garbage=4, deflate=True)
    doc.close()


def main():
    p = argparse.ArgumentParser(
        description="Photo or scan of a signed document -> A4 PDF.")
    p.add_argument("images", nargs="+", help="one image per page, in order")
    p.add_argument("-o", "--output", default="document.pdf")
    p.add_argument("--dpi", type=int, default=200,
                   help="200 is enough for printed text; 300 if the signature is thin")
    p.add_argument("--colour", "--color", dest="colour", action="store_true",
                   help="keep the colour (only needed for blue ink you want visible)")
    p.add_argument("--no-flatten", action="store_true",
                   help="do not flatten the background (use if the paper comes out washed out)")
    p.add_argument("--max-mb", type=float, default=2.0,
                   help="size cap: below this, upload portals do not complain")
    a = p.parse_args()

    paths = [Path(x) for x in a.images]
    for x in paths:
        if not x.is_file():
            p.error(f"file not found: {x}")

    out = Path(a.output)
    dpi = a.dpi
    # If it overshoots the cap, retry at a lower resolution rather than hand over a
    # file the portal will reject. 120 dpi is the floor: below that, printed text
    # starts to break up.
    while True:
        build(paths, out, dpi, a.colour, not a.no_flatten)
        mb = out.stat().st_size / 1_048_576
        if mb <= a.max_mb or dpi <= 120:
            break
        dpi = max(120, int(dpi * 0.8))
        print(f"  {mb:.1f} MB over the cap, retrying at {dpi} dpi")

    doc = pymupdf.open(out)
    print(f"Wrote: {out}  ({mb:.2f} MB, {len(doc)} pages, {dpi} dpi)")
    if mb > a.max_mb:
        print(f"  WARNING: {mb:.2f} MB, over the {a.max_mb} MB cap. "
              "Retake the photo closer, framing the sheet alone.")
    print("Check at full screen that the signature is clearly visible before uploading.")


if __name__ == "__main__":
    main()
