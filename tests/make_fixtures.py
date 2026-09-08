#!/usr/bin/env python3
"""
Build the test PDFs for the redaction check.

They are generated, not collected: no real document, nobody's data. The names and
numbers inside are invented and exist only to show that "covered" text reads back.

    python3 tests/make_fixtures.py            # writes into tests/fixtures/
"""

from pathlib import Path

import pymupdf

HERE = Path(__file__).parent
OUT = HERE / "fixtures"

CONFIDENTIAL = [
    "Name: Mario Rossi",
    "Tax code: RSSMRA80A01H501U",
    "IBAN: IT60X0542811101000000123456",
]


def _page_with_data(doc):
    page = doc.new_page()
    page.insert_text((60, 80), "Sample form", fontname="hebo", fontsize=16)
    page.insert_text((60, 110), "Generated for testing. All values are invented.",
                     fontname="helv", fontsize=9, color=(0.4, 0.4, 0.4))
    y = 160
    boxes = []
    for line in CONFIDENTIAL:
        page.insert_text((60, y), line, fontname="helv", fontsize=12)
        # The box is sized by MEASURING the string, not by guessing a width per
        # character. With a guess the cover fell short of the end of the line and
        # the test recovered only a truncated value, which made the fixture lie
        # about what a real fake redaction looks like.
        width = pymupdf.get_text_length(line, fontname="helv", fontsize=12)
        boxes.append(pymupdf.Rect(58, y - 11, 62 + width, y + 4))
        y += 34
    return page, boxes


def fake_redaction():
    """The case to catch: black rectangles over text that stays in the file."""
    doc = pymupdf.open()
    page, boxes = _page_with_data(doc)
    for r in boxes:
        page.draw_rect(r, color=(0, 0, 0), fill=(0, 0, 0))
    doc.save(OUT / "fake_redaction.pdf")
    doc.close()


def real_redaction():
    """The same document redacted properly: the content is removed."""
    doc = pymupdf.open()
    page, boxes = _page_with_data(doc)
    for r in boxes:
        page.add_redact_annot(r, fill=(0, 0, 0))
    page.apply_redactions()
    doc.save(OUT / "real_redaction.pdf")
    doc.close()


def photo_with_boxes():
    """The case seen in the wild: a page that is a photo, with rectangles on top.

    Under the rectangles there is no text but pixels, and the embedded image is
    untouched by anything drawn over it: it extracts back intact.
    """
    source = pymupdf.open()
    page, boxes = _page_with_data(source)
    pix = page.get_pixmap(dpi=110)
    source.close()

    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(pymupdf.Rect(0, 0, 595, 842), pixmap=pix, keep_proportion=True)
    for r in boxes:
        page.draw_rect(r, color=(0.31, 0.51, 0.74), fill=(0.31, 0.51, 0.74))
    doc.save(OUT / "photo_with_boxes.pdf")
    doc.close()


def clean_document():
    """An ordinary document, nothing over anything."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((60, 80), "Quarterly report", fontname="hebo", fontsize=16)
    page.insert_text((60, 120), "Ordinary text, no overlapping shapes.",
                     fontname="helv", fontsize=11)
    doc.save(OUT / "clean.pdf")
    doc.close()


def graphic_band():
    """The honest false positive: a coloured header band with white type on it.

    Seen from the file it is identical to a censorship — a filled rectangle with
    text inside it. That is why the tool does not return a bare verdict but shows
    the text it finds underneath: here it is the title itself, and a reader sees in
    a second that it is not a leak. Telling them apart automatically would mean
    guessing at the designer's intent.
    """
    doc = pymupdf.open()
    page = doc.new_page()
    page.draw_rect(pymupdf.Rect(0, 0, 595, 90), color=(0.1, 0.2, 0.5), fill=(0.1, 0.2, 0.5))
    page.insert_text((60, 55), "ANNUAL REPORT", fontname="hebo", fontsize=20,
                     color=(1, 1, 1))
    page.insert_text((60, 140), "Body of the document.", fontname="helv", fontsize=11)
    doc.save(OUT / "graphic_band.pdf")
    doc.close()


def page_photo():
    """A photographed page, as a JPEG: the input photo_to_pdf takes.

    Rendered rather than photographed, for the same reason as everything else here —
    a real photo of a real document would be somebody's document.
    """
    doc = pymupdf.open()
    page = doc.new_page(width=300, height=400)
    page.draw_rect(pymupdf.Rect(0, 0, 300, 400), color=(0.93, 0.92, 0.90),
                   fill=(0.93, 0.92, 0.90))
    page.insert_text((30, 60), "Delivery note", fontname="hebo", fontsize=14)
    for i in range(8):
        page.insert_text((30, 100 + i * 22), "Invented line of text, number %d" % (i + 1),
                         fontname="helv", fontsize=9)
    OUT.joinpath("page_photo.jpg").write_bytes(page.get_pixmap(dpi=96).tobytes("jpg"))
    doc.close()


def signature_png():
    """A cut-out signature: a squiggle whose alpha channel comes from its darkness.

    Built the way extract_signature.py builds one — dark pixels opaque, paper
    transparent — so what the PDF tools embed here is shaped like what the signature
    extractor hands them.
    """
    doc = pymupdf.open()
    page = doc.new_page(width=90, height=30)
    page.draw_polyline([(6, 22), (20, 8), (34, 24), (48, 7), (66, 21), (84, 11)],
                       color=(0.08, 0.08, 0.12), width=2.2)
    flat = page.get_pixmap(alpha=False)
    alpha = bytearray(flat.width * flat.height)
    for y in range(flat.height):
        for x in range(flat.width):
            r, g, b = flat.pixel(x, y)
            # The same ramp extract_signature.py uses: paper transparent, ink solid,
            # the values between left semi-transparent so the edges stay smooth.
            value = (205 - min(r, g, b)) / 110 * 255
            alpha[y * flat.width + x] = max(0, min(255, int(value)))
    pix = pymupdf.Pixmap(flat, 1)
    pix.set_alpha(bytes(alpha))
    pix.save(OUT / "signature.png")
    doc.close()


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for f in (fake_redaction, real_redaction, photo_with_boxes, clean_document,
              graphic_band, page_photo, signature_png):
        f()
        print(f"  {f.__name__}")
    print(f"Fixtures in {OUT}")
