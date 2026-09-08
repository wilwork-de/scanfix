#!/usr/bin/env python3
"""
Generate a one-page CV as a PDF, with the date and signature block already in place.

Why a script and not a word processor: the PDF comes out identical every time, the
text stays selectable (upload portals sometimes parse it), and the date at the
bottom updates itself. Edit the DATA dictionary below and run it again.

The document renders in English or Italian (--locale). The Italian output is the
reason the tool exists: institutional portals in Italy reject a CV that has no date
and no handwritten signature, and they expect the GDPR authorisation line. Those
strings are document content, not code, so they live in LABELS.

Usage:
    python3 make_cv.py                              # today's date, empty signature line
    python3 make_cv.py --signature signature.png    # paste in a scanned signature
    python3 make_cv.py --locale it --place Torino -o cv.pdf

--signature is the clean way to sign: sign a blank sheet, photograph it, crop it
with extract_signature.py, and the image is laid on the signature rule. The rest of
the CV stays sharp text instead of a blurry scan of a printed page.
"""

import argparse
from datetime import date
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

# ---------------------------------------------------------------------------
# 1. YOUR DATA — the only part you need to touch.
#    Everything in [square brackets] is a placeholder to replace. Set an entry to
#    "" or empty a list and that section is simply not printed.
# ---------------------------------------------------------------------------

DATA = {
    "first_name": "[First name]",
    "last_name": "[Last name]",
    # One line under the name. Write the role you are applying for, not the one you
    # currently hold.
    "headline": "[Target role]",

    "born_on": "[dd/mm/yyyy]",
    "born_in": "[City]",
    "address": "[Street and number], [postcode] [City] ([Province])",
    "phone": "[+39 ...]",
    "email": "[first.last@example.com]",
    "linkedin": "",                 # e.g. "linkedin.com/in/yourname"; "" to omit
    "licence": "[Driving licence B]",
    "citizenship": "[Citizenship]",

    # Education, most recent first. Keep the diploma: institutional applications
    # cross-check it against the certificate you upload separately.
    "education": [
        {
            "title": "[Qualification]",
            "org": "[Institution] - [City]",
            "period": "[yyyy]",
            "notes": ["[Grade, if it helps you]"],
        },
    ],

    # Experience, most recent first. Every line says what you DID, with a verb up
    # front. "Responsible for" says nothing; "handled X" does.
    "experience": [
        {
            "title": "[Job title]",
            "org": "[Company] - [City]",
            "period": "[mm/yyyy] - [mm/yyyy or 'present']",
            "notes": [
                "[What you did, with a number in it if you have one]",
                "[Tools or technologies you used]",
            ],
        },
    ],

    "skills": [
        ("[Operating systems]", "[Windows, Linux, ...]"),
        ("[Networking]", "[TCP/IP, DNS, ...]"),
        ("[Languages and tools]", "[Python, Git, ...]"),
    ],

    "languages": [
        ("[Italian]", "[native]"),
        ("[English]", "[B2 - CEFR level]"),
    ],

    "other": ["[Anything else worth one line]"],
}

# Document strings. These are payload, not code: they are what an Italian or English
# reader sees on the page, so they stay in their own language.
LABELS = {
    "en": {
        "personal": "Personal details", "education": "Education",
        "experience": "Experience", "skills": "Skills", "languages": "Languages",
        "other": "Additional information", "signature": "Signature",
        "born_on": "Date of birth", "born_in": "Place of birth",
        "citizenship": "Citizenship", "licence": "Driving licence", "page": "page",
        "privacy": "",
    },
    "it": {
        "personal": "Dati personali", "education": "Istruzione e formazione",
        "experience": "Esperienza professionale", "skills": "Competenze tecniche",
        "languages": "Lingue", "other": "Altre informazioni", "signature": "Firma",
        "born_on": "Data di nascita", "born_in": "Luogo di nascita",
        "citizenship": "Cittadinanza", "licence": "Patente", "page": "pag.",
        # The GDPR line. Cite the Regulation first: it is the higher and current
        # source, and the Italian Code is the national law that was harmonised to it.
        #
        # Do NOT cite "art. 13 del D.Lgs. 196/2003": that article was REPEALED by
        # D.Lgs. 101/2018, which harmonised the Code with the GDPR. Disclosure is now
        # governed by articles 13-14 of the Regulation. Half the templates online
        # still cite the old article and nobody is rejected for it, but it points at
        # a rule that no longer exists.
        "privacy": ("Autorizzo il trattamento dei miei dati personali contenuti nel "
                    "presente curriculum vitae ai sensi del Regolamento UE 2016/679 "
                    "(GDPR) e del D. Lgs. 196/2003 come modificato dal D. Lgs. 101/2018."),
    },
}

MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June",
           "July", "August", "September", "October", "November", "December"],
    "it": ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
           "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"],
}

# Restrained palette: near-black for headings, grey for body. No bright colours —
# an institutional CV has to read when printed in black and white.
INK = (26, 32, 44)
GREY = (74, 85, 104)
LIGHT_GREY = (160, 174, 192)
RULE = (203, 213, 224)


class CV(FPDF):
    """FPDF with a few shortcuts, to avoid repeating set_font everywhere."""

    def __init__(self, data, labels):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.data = data
        self.labels = labels
        # A generous bottom margin keeps the signature block clear of the edge.
        self.set_auto_page_break(auto=True, margin=18)
        self.set_margins(18, 16, 18)
        self.set_title(f"Curriculum Vitae - {data['first_name']} {data['last_name']}")
        self.set_author(f"{data['first_name']} {data['last_name']}")

    def footer(self):
        """Page number. Harmless on a one-page CV, useful on two if the sheets
        get separated after printing."""
        self.set_y(-13)
        self.set_font("Helvetica", "", 7.5)
        self.set_text_color(*LIGHT_GREY)
        d = self.data
        text = (f"{d['first_name']} {d['last_name']} - "
                f"{self.labels['page']} {self.page_no()}/{{nb}}")
        self.cell(0, 4, text, align="C")

    def header_block(self):
        d = self.data
        self.set_font("Helvetica", "B", 21)
        self.set_text_color(*INK)
        self.cell(0, 9, f"{d['first_name']} {d['last_name']}".upper(),
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        if d.get("headline"):
            self.set_font("Helvetica", "", 10.5)
            self.set_text_color(*GREY)
            self.cell(0, 5.5, d["headline"], new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.ln(2.5)
        contacts = [v for v in (d.get("phone"), d.get("email"), d.get("linkedin")) if v]
        address = [v for v in (d.get("address"),) if v]
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*GREY)
        for line in (contacts, address):
            if line:
                # \xb7 is a middle dot: it exists in latin-1, unlike the bullet
                # character, which the core PDF fonts cannot encode.
                self.cell(0, 4.6, "  \xb7  ".join(line),
                          new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.ln(3)
        self.set_draw_color(*INK)
        self.set_line_width(0.5)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(5)

    def section(self, title):
        """Upper-case section heading with a hairline under it."""
        # With less than 22 mm left there is no point opening a section here: the
        # heading would be orphaned at the foot of the page.
        if self.h - self.b_margin - self.get_y() < 22:
            self.add_page()
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*INK)
        self.cell(0, 5.5, title.upper(), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*RULE)
        self.set_line_width(0.25)
        self.line(self.l_margin, self.get_y() + 0.4, self.w - self.r_margin, self.get_y() + 0.4)
        self.ln(3)

    def entry(self, title, org="", period="", notes=()):
        """One row of experience or education: title left, dates right."""
        date_width = 38
        y = self.get_y()

        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*INK)
        self.multi_cell(self.epw - date_width, 5, title,
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        if period:
            # The date is written afterwards, with Y sent back to the title's line,
            # so it stays top-aligned even when the title wraps.
            after = self.get_y()
            self.set_xy(self.w - self.r_margin - date_width, y)
            self.set_font("Helvetica", "", 9)
            self.set_text_color(*GREY)
            self.cell(date_width, 5, period, align="R")
            self.set_y(after)

        if org:
            self.set_font("Helvetica", "I", 9.5)
            self.set_text_color(*GREY)
            self.multi_cell(self.epw, 4.8, org, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        for line in notes:
            self.bullet(line)
        self.ln(2.6)

    def bullet(self, text, indent=3.5):
        """Bulleted line. The dot is drawn, not typed: the core PDF fonts have no
        bullet glyph and it would raise an encoding error."""
        self.set_font("Helvetica", "", 9.5)
        self.set_text_color(*GREY)
        x0 = self.l_margin + indent
        y0 = self.get_y()
        self.set_fill_color(*LIGHT_GREY)
        self.rect(x0, y0 + 1.9, 1.3, 1.3, style="F")
        self.set_xy(x0 + 3.6, y0)
        self.multi_cell(self.epw - indent - 3.6, 4.7, text,
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def pair(self, label, value, width=42):
        """Two-column row: bold label, value beside it."""
        y = self.get_y()
        self.set_font("Helvetica", "B", 9.5)
        self.set_text_color(*INK)
        self.cell(width, 5, label)
        self.set_font("Helvetica", "", 9.5)
        self.set_text_color(*GREY)
        self.set_xy(self.l_margin + width, y)
        self.multi_cell(self.epw - width, 5, value, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def signature_block(self, place, day, signature=None):
        """Privacy line, then place and date on the left with the signature right.

        This is the part institutional portals reject a CV over. It goes at the foot
        of the last page, always in this order: the data-protection authorisation
        first, then date and signature on the same line.
        """
        # Room needed: about 14 mm for the privacy line plus 30 for the signature.
        if self.h - self.b_margin - self.get_y() < 48:
            self.add_page()
        else:
            self.ln(4)

        if self.labels["privacy"]:
            self.set_font("Helvetica", "", 8)
            self.set_text_color(*GREY)
            self.multi_cell(self.epw, 3.9, self.labels["privacy"],
                            new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(8)

        y = self.get_y()
        half = self.epw / 2

        self.set_font("Helvetica", "", 10)
        self.set_text_color(*INK)
        self.cell(half, 5, f"{place}, {day}" if place else day)

        self.set_xy(self.l_margin + half, y)
        self.cell(half, 5, self.labels["signature"], align="L")

        rule_y = y + 18
        if signature:
            # The image sits ON the rule, like a real signature.
            height = 14
            self.image(str(signature), x=self.l_margin + half + 1,
                       y=rule_y - height - 0.5, h=height)

        self.set_draw_color(*INK)
        self.set_line_width(0.3)
        self.line(self.l_margin + half, rule_y, self.w - self.r_margin, rule_y)
        self.set_y(rule_y)


def spelled_date(day: date, locale: str) -> str:
    """8 September 2026 — no leading zero, the way it is written by hand."""
    return f"{day.day} {MONTHS[locale][day.month - 1]} {day.year}"


def build(data, labels, place, day, signature, output):
    pdf = CV(data, labels)
    pdf.add_page()
    pdf.header_block()

    personal = [(labels["born_on"], data.get("born_on")),
                (labels["born_in"], data.get("born_in")),
                (labels["citizenship"], data.get("citizenship")),
                (labels["licence"], data.get("licence"))]
    personal = [(k, v) for k, v in personal if v]
    if personal:
        pdf.section(labels["personal"])
        for k, v in personal:
            pdf.pair(k, v)
        pdf.ln(3)

    for key, heading in (("education", "education"), ("experience", "experience")):
        if data.get(key):
            pdf.section(labels[heading])
            for e in data[key]:
                pdf.entry(e["title"], e.get("org", ""), e.get("period", ""), e.get("notes", ()))

    for key, heading in (("skills", "skills"), ("languages", "languages")):
        if data.get(key):
            pdf.section(labels[heading])
            for k, v in data[key]:
                pdf.pair(k, v, width=46)
            pdf.ln(3)

    if data.get("other"):
        pdf.section(labels["other"])
        for line in data["other"]:
            pdf.bullet(line)
        pdf.ln(3)

    pdf.signature_block(place, day, signature)
    pdf.output(str(output))
    return output


def main():
    p = argparse.ArgumentParser(description="Generate a one-page CV as a PDF.")
    p.add_argument("--locale", default="en", choices=sorted(LABELS),
                   help="language of the headings and of the date (default: en)")
    p.add_argument("--place", default="", help="place printed next to the date")
    p.add_argument("--date", default=None, help="yyyy-mm-dd; default: today")
    p.add_argument("--signature", default=None,
                   help="PNG/JPG of the scanned signature, white or transparent background")
    p.add_argument("-o", "--output", default=None)
    a = p.parse_args()

    day = date.fromisoformat(a.date) if a.date else date.today()

    signature = Path(a.signature).expanduser() if a.signature else None
    if signature and not signature.is_file():
        p.error(f"signature file not found: {signature}")

    name = f"CV_{DATA['first_name']}_{DATA['last_name']}.pdf".replace(" ", "_")
    name = name.replace("[", "").replace("]", "")
    out = Path(a.output) if a.output else Path(__file__).parent / name

    build(DATA, LABELS[a.locale], a.place, spelled_date(day, a.locale), signature, out)
    print(f"Wrote: {out}")
    if not signature:
        print("NOTE: the signature line is empty. Institutional portals want a "
              "handwritten signature — print and sign it, or rerun with "
              "--signature signature.png")


if __name__ == "__main__":
    main()
