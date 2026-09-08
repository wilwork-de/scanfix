#!/usr/bin/env python3
"""
Check whether a PDF's redaction actually hides anything, or is just a box on top.

The problem. A PDF is not a flattened image: it is a stack of objects drawn one
over another. Putting a black rectangle over a name ADDS an object, it does not
remove one. The name stays in the file, underneath, and anyone gets it back with
three lines of code or by selecting it with the mouse. This is how court filings
and government documents have leaked while their authors believed them censored.

It applies to rectangles drawn in Word or Preview, to highlighter annotations, and
to the online "AI PDF tools" that promise to censor a document for you.

What this script does. For every page it collects the filled shapes (rectangles and
vector fills) and the opaque annotations, then looks at what sits UNDER each one:

  - if there is extractable text underneath, it prints that text. If what comes out
    is a name or an account number, the redaction is fake and the data is readable;
  - if there is an image underneath, it reports that the content is recoverable by
    extracting the embedded image, which is untouched by anything drawn on top of it.

Why it prints the recovered text instead of just returning a verdict: a filled
rectangle over text is not always a censorship. A coloured header band with white
type on it is the same thing as seen from the file. By showing what is underneath,
a person makes the distinction in a second, and the program never has to guess at
intent.

How to redact for real:
  1. a true redaction, which removes the content instead of covering it. In PyMuPDF
     that is page.add_redact_annot(rect) followed by page.apply_redactions();
  2. or flatten it: render the page to an image, cover, re-export. Crude but
     effective, because it rebuilds the pixels from scratch;
  3. either way, reopen the finished file and check it again. With this script.

Usage:
    python3 check_redaction.py document.pdf
    python3 check_redaction.py *.pdf --quiet        # verdict only
    python3 check_redaction.py doc.pdf --json       # to build a pipeline on

Exit codes: 0 nothing suspicious, 1 possible leak, 2 read error.
"""

import argparse
import json
import sys
from pathlib import Path

import pymupdf

# A very light fill is usually a page background or a watermark, not a censorship:
# nobody hides a value with white on white. Below this "how dark is the tint"
# threshold a shape is not treated as covering anything.
DARKNESS_THRESHOLD = 0.12

# Tiny shapes are decorations, bullets, table borders. A censorship is the size of
# what it hides, so it needs at least a few points on each side.
MIN_AREA = 60.0     # square points


def darkness(colour) -> float:
    """0 = white, 1 = black. Used to discard near-white fills."""
    if colour is None:
        return 0.0
    if isinstance(colour, (int, float)):
        return 1.0 - float(colour)
    values = list(colour)[:3]
    if not values:
        return 0.0
    return 1.0 - sum(float(v) for v in values) / len(values)


def covering_shapes(page):
    """Rectangles and vector fills large enough and dark enough to hide something.

    Only drawings that carry a fill are considered ('f' = fill, 'fs' = fill and
    stroke). A stroke with no fill covers nothing: a line or a border still lets
    you see what is behind it, so it is not a censorship candidate.
    """
    found = []
    for d in page.get_drawings():
        if d.get("type") not in ("f", "fs"):
            continue
        r = pymupdf.Rect(d["rect"])
        if r.get_area() < MIN_AREA or not r.is_valid:
            continue
        dark = darkness(d.get("fill"))
        if dark < DARKNESS_THRESHOLD:
            continue
        found.append({"rect": r, "darkness": round(dark, 3), "source": "drawing"})

    # Opaque square annotations do the same job and are worse: in many readers they
    # can be deleted with a single click.
    for a in page.annots() or []:
        if a.type[1] not in ("Square", "Highlight", "Redact"):
            continue
        r = pymupdf.Rect(a.rect)
        if r.get_area() < MIN_AREA:
            continue
        colours = a.colors or {}
        dark = darkness(colours.get("fill") or colours.get("stroke"))
        if dark < DARKNESS_THRESHOLD and a.type[1] != "Redact":
            continue
        found.append({"rect": r, "darkness": round(dark, 3),
                      "source": f"{a.type[1]} annotation"})
    return found


def image_rects(page):
    """Where the images sit on the page, with two fallbacks.

    A robust path is needed here because the first version of this check returned
    CLEAN on the very case it was written for: a page that was a photograph with
    four rectangles drawn over it. Cause: get_image_rects() returned [0,0,0,0], a
    degenerate rectangle, so no overlap was ever possible. That happens when the
    image is placed through a matrix the function does not reconstruct, and it
    raises nothing at all — it just answers with something empty.

    So three sources in cascade, from the most precise to the most cautious:
      1. get_image_rects(), discarding degenerate rectangles;
      2. the image-type blocks of the text extractor, which carry a bbox;
      3. if the page holds images but neither of those produced a usable position,
         treat the whole page as covered. That is the right cautious assumption: on
         a scanned document the image IS the page, and erring high here produces one
         extra warning rather than one silently missed leak.
    """
    rects = []
    for info in page.get_images(full=True):
        try:
            for r in page.get_image_rects(info[0]):
                r = pymupdf.Rect(r)
                if r.is_valid and not r.is_empty and r.get_area() > 1:
                    rects.append(r)
        except Exception:
            continue

    if not rects:
        try:
            for block in page.get_text("dict").get("blocks", []):
                if block.get("type") == 1:
                    r = pymupdf.Rect(block["bbox"])
                    if r.is_valid and not r.is_empty and r.get_area() > 1:
                        rects.append(r)
        except Exception:
            pass

    if not rects and page.get_images():
        rects.append(pymupdf.Rect(page.rect))
    return rects


def analyse(path: Path) -> dict:
    doc = pymupdf.open(path)
    pages = []
    for number, page in enumerate(doc, start=1):
        images = image_rects(page)

        findings = []
        for shape in covering_shapes(page):
            r = shape["rect"]
            # Shrink by one point so text that merely grazes the edge of the shape
            # is not counted as sitting underneath it.
            inner = pymupdf.Rect(r.x0 + 1, r.y0 + 1, r.x1 - 1, r.y1 - 1)
            text = ""
            if inner.is_valid and not inner.is_empty:
                text = page.get_textbox(inner).strip()

            over_image = any(r.intersects(ri) for ri in images)
            if not text and not over_image:
                continue    # it covers blank paper: graphics, not a censorship

            findings.append({
                "rect": [round(v, 1) for v in r],
                "source": shape["source"],
                "darkness": shape["darkness"],
                "text_underneath": text[:300],
                "over_image": over_image,
            })

        if findings:
            pages.append({"page": number, "findings": findings})

    result = {
        "file": str(path),
        "total_pages": doc.page_count,
        "suspect_pages": pages,
        "verdict": "SUSPECT" if pages else "CLEAN",
    }
    doc.close()
    return result


def report(result: dict, quiet: bool):
    name = Path(result["file"]).name
    if result["verdict"] == "CLEAN":
        print(f"CLEAN    {name} — no opaque shape over extractable content")
        return
    count = sum(len(p["findings"]) for p in result["suspect_pages"])
    print(f"SUSPECT  {name} — {count} opaque shapes over still-extractable content")
    if quiet:
        return
    for p in result["suspect_pages"]:
        for f in p["findings"]:
            print(f"  page {p['page']}  {f['source']}  rect {f['rect']}")
            if f["text_underneath"]:
                print(f"     readable text underneath: {f['text_underneath']!r}")
            if f["over_image"]:
                print("     covers an image: the content is recovered by extracting "
                      "the embedded image, which no rectangle drawn on top modifies")
    print("\n  Covering is not deleting. To redact for real: add_redact_annot() +")
    print("  apply_redactions(), or flatten the page to an image. Then check the")
    print("  finished file again with this same script.")


def main():
    p = argparse.ArgumentParser(
        description="Check whether a PDF's redaction holds, or is just a box on top.")
    p.add_argument("pdf", nargs="+", help="one or more PDFs to check")
    p.add_argument("--quiet", action="store_true", help="verdict only, one line per file")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    a = p.parse_args()

    results, errors = [], 0
    for name in a.pdf:
        path = Path(name)
        if not path.is_file():
            print(f"ERROR    {name} — file not found", file=sys.stderr)
            errors += 1
            continue
        try:
            results.append(analyse(path))
        except Exception as e:
            print(f"ERROR    {name} — {e}", file=sys.stderr)
            errors += 1

    if a.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        for r in results:
            report(r, a.quiet)

    if errors:
        return 2
    return 1 if any(r["verdict"] == "SUSPECT" for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
