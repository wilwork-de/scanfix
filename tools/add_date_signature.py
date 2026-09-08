#!/usr/bin/env python3
"""
Add a place, a date and a signature line to the bottom of an existing PDF.

Unlike make_cv.py, which builds a document from scratch, this takes your PDF as it
is and writes only what is missing. Layout, fonts and pagination stay identical:
only the empty space at the bottom is touched.

Usage:
    python3 add_date_signature.py document.pdf
    python3 add_date_signature.py document.pdf --signature signature.png --place Turin
    python3 add_date_signature.py document.pdf --label Firma --locale it

TWO THINGS I TRIED THAT DO NOT WORK. They are documented here because both look
reasonable and both fail silently, which is the worst way to fail.

1. *Reusing the font embedded in the PDF* so the addition blends in. Embedded fonts
   are CID subsets: they carry only the glyphs that document needed, with their own
   internal encoding. Re-inserting one produces text that displays on screen but
   extracts as null bytes. The PDF looks right and a parser reads no date at all.
   Helvetica is used instead — one of the 14 fonts every reader guarantees. It does
   not match Carlito, but it is correct.

2. *Replacing placeholders ("name", "email@example.com") inside the PDF.* PyMuPDF's
   redaction deletes every piece of text whose box TOUCHES the chosen area, and
   those boxes are inflated by line spacing: the box of a 20pt heading reached y=63
   and grazed the contact line starting at y=56. The result was that the email and
   phone number vanished too, with no error. Tightening the area does not help,
   because it is box intersection that decides.
   Placeholders belong in the source file (.docx / .odt); re-export from there. The
   script below only reports them, and never touches them.
"""

import argparse
import re
from datetime import date
from pathlib import Path

import pymupdf

MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June",
           "July", "August", "September", "October", "November", "December"],
    "it": ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
           "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"],
}

INK = (0.10, 0.13, 0.17)

# Strings that give away an uncompiled template. A real case: an application portal
# rejected a CV because the heading still read "name" instead of a person's name.
PLACEHOLDERS = [
    (re.compile(r"^\s*name\s*$", re.I), "the name at the top"),
    (re.compile(r"email@|firstname\.lastname@|nome\.cognome@|your\.?mail@", re.I),
     "the email address"),
    (re.compile(r"\+?\s*3{4,}"), "the phone number"),
    (re.compile(r"\[[^\]]{2,}\]"), "a field in square brackets"),
]


def spelled_date(day: date, locale: str) -> str:
    """8 September 2026 — no leading zero, the way it is written by hand."""
    months = MONTHS.get(locale, MONTHS["en"])
    return f"{day.day} {months[day.month - 1]} {day.year}"


def geometry(page):
    """Real margins and the bottom of the text, read from the document.

    This is what anchors the signature block to the same left margin as the rest. At
    a fixed coordinate it would be a few millimetres out on any document with
    different margins, which is exactly the kind of detail that makes a file look
    tampered with.
    """
    blocks = [b for b in page.get_text("blocks") if b[4].strip()]
    if not blocks:
        return page.rect.x0 + 42, page.rect.x1 - 42, page.rect.y0 + 42
    return (min(b[0] for b in blocks),
            max(b[2] for b in blocks),
            max(b[3] for b in blocks))


def signature_block(doc, page, place, day, label, signature=None):
    """Place and date on the left, the label and a rule on the right, at the bottom.

    Returns (page, spilled) where 'spilled' says whether a new sheet had to be added.
    The caller reports that, because silently turning a one-page document into a
    two-page one with a nearly empty second page is the kind of surprise you only
    notice after uploading it somewhere.
    """
    left, right, bottom = geometry(page)
    y = bottom + 46          # breathing room between the last line and the block
    spilled = False

    if y + 34 > page.rect.y1 - 40:
        # Full page: a fresh sheet beats a signature crushed into the margin.
        page = doc.new_page(width=page.rect.width, height=page.rect.height)
        y = page.rect.y0 + 70
        left, right = 42.5, page.rect.x1 - 42.5
        spilled = True

    middle = left + (right - left) / 2
    # Without --place the line is just the date: "  , 8 September 2026" would be a
    # visible artefact of an unset option.
    stamp = f"{place}, {day}" if place else day
    page.insert_text((left, y), stamp, fontname="helv", fontsize=10, color=INK)
    page.insert_text((middle, y), label, fontname="helv", fontsize=10, color=INK)

    rule_y = y + 26
    if signature:
        # The image sits ON the rule, like a real signature. Proportions come from
        # the file: squashing a signature makes it look forged.
        img = pymupdf.Pixmap(str(signature))
        height = 20.0
        width = min(height * img.width / img.height, right - middle - 4)
        height = width * img.height / img.width
        page.insert_image(
            pymupdf.Rect(middle + 2, rule_y - height - 1, middle + 2 + width, rule_y - 1),
            filename=str(signature), keep_proportion=True)

    page.draw_line((middle, rule_y), (right, rule_y), color=INK, width=0.7)
    return page, spilled


def remaining_placeholders(doc):
    found = []
    for page in doc:
        for line in page.get_text().splitlines():
            for rx, label in PLACEHOLDERS:
                if rx.search(line.strip()) and label not in found:
                    found.append(label)
    return found


def verify(path, expected_date, original_text):
    """Check the date is actually READABLE and that no text was lost.

    Not paranoia: the first version of this script wrote a date that displayed on
    screen but extracted as null bytes. Without this check the defect would have
    reached the portal it was uploaded to.
    """
    doc = pymupdf.open(path)
    text = "\n".join(p.get_text() for p in doc)
    problems = []
    if expected_date not in text:
        problems.append(f"the date {expected_date!r} is not extractable from the PDF")
    lost = [line for line in original_text.splitlines() if line.strip() and line not in text]
    if lost:
        problems.append(f"{len(lost)} lines of the original are gone: {lost[:3]}")
    doc.close()
    return problems


def main():
    p = argparse.ArgumentParser(
        description="Add a date and signature line to an existing PDF.")
    p.add_argument("pdf", help="the document to sign")
    p.add_argument("--place", default="", help="place printed before the date")
    p.add_argument("--date", default=None, help="yyyy-mm-dd (default: today)")
    p.add_argument("--locale", default="en", choices=sorted(MONTHS),
                   help="language of the month name (default: en)")
    p.add_argument("--label", default="Signature",
                   help='word printed above the rule (default: "Signature"; use "Firma" in Italian)')
    p.add_argument("--signature", default=None, help="PNG/JPG of the scanned signature")
    p.add_argument("-o", "--output", default=None)
    a = p.parse_args()

    src = Path(a.pdf)
    if not src.is_file():
        p.error(f"file not found: {src}")
    signature = Path(a.signature).expanduser() if a.signature else None
    if signature and not signature.is_file():
        p.error(f"signature file not found: {signature}")

    day = spelled_date(date.fromisoformat(a.date) if a.date else date.today(), a.locale)
    out = Path(a.output) if a.output else src.with_name(src.stem + "_signed.pdf")

    doc = pymupdf.open(src)
    original = "\n".join(pg.get_text() for pg in doc)
    pages_before = doc.page_count
    place = a.place.rstrip(", ") if a.place else ""

    # A document that already carries a date and a signature label is being signed
    # twice. Worth saying: the usual cause is running this on its own output.
    tail = doc[-1].get_text()
    if a.label in tail and str(day.split()[-1]) in tail:
        print(f"NOTE: the last page already contains {a.label!r} and a date. "
              "Adding a second block — is this the original document?")

    _, spilled = signature_block(doc, doc[-1], place, day, a.label, signature)
    doc.save(str(out), garbage=4, deflate=True)

    problems = verify(out, day, original)
    print(f"Wrote: {out}")
    if spilled:
        print(f"NOTE: the last page was full, so the signature block went onto a new "
              f"sheet — the document is now {pages_before + 1} pages. To keep it to "
              f"{pages_before}, shorten the content or reduce its bottom margin.")
    for x in problems:
        print(f"  PROBLEM: {x}")

    left = remaining_placeholders(pymupdf.open(out))
    if left:
        print("STILL TO FILL IN, in the source file (.docx/.odt), then re-export: "
              + ", ".join(left))
    if not signature:
        print("The signature line is empty: print and sign it by hand, "
              "or rerun with --signature signature.png")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
