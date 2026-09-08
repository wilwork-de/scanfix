# scanfix

Command-line tools for putting PDF documents back in order: clean up a phone photo of
a sheet of paper, add a date and signature block, and **check whether a redaction
actually holds**.

**Live redaction checker:** https://wilwork-de.github.io/scanfix/ — it runs entirely
in your browser, the document is never uploaded anywhere.

---

## The redaction check

A PDF is not a flattened image: it is a stack of objects drawn one over another.
Putting a black rectangle over a name **adds** an object, it does not remove one. The
name stays in the file, underneath, and comes back by selecting it with the mouse or
with three lines of code. This is how court filings and government documents have
leaked while their authors believed them censored, and it holds just the same for
rectangles drawn in Word, for highlighter annotations, and for the online tools that
promise to censor a PDF for you.

```console
$ python3 tools/check_redaction.py document.pdf
SUSPECT  document.pdf — 3 opaque shapes over still-extractable content
  page 1  drawing  rect [58.0, 149.0, 158.4, 164.0]
     readable text underneath: 'Name: Mario Rossi'
  page 1  drawing  rect [58.0, 183.0, 247.1, 198.0]
     readable text underneath: 'Tax code: RSSMRA80A01H501U'
  page 1  drawing  rect [58.0, 217.0, 253.0, 232.0]
     readable text underneath: 'IBAN: IT60X0542811101000000123456'
```

It exits with `1` when it finds a possible leak and `0` when it finds nothing, so it
drops into a pipeline or a pre-commit hook.

### Why it prints the text instead of just a verdict

A filled rectangle over text is not always a censorship: a coloured header band with
white type on it, seen from the file, is exactly the same thing. By showing *what* is
underneath, a person makes the distinction in a second — an account number is a leak,
the document's own title is graphics. Doing it automatically would mean guessing at
the intent of whoever laid the page out, and this tool does not try: the known false
positive is one of the five test fixtures, on purpose.

### How to redact for real

1. **Remove instead of covering**: `page.add_redact_annot(rect)` followed by
   `page.apply_redactions()`.
2. **Or flatten**: render the page to an image, cover, re-export. Crude but effective,
   because it rebuilds the pixels from scratch.
3. **Check the finished file.** Not optional, and it is the step skipped by everyone
   who has ever published a badly censored document.

---

## The tools

| Tool | What it does |
|---|---|
| `check_redaction.py` | Checks whether a PDF's covers actually hide anything |
| `clean_scan.py` | From a photo of a sheet to a clean scan: removes the shadow, straightens the perspective, fits to A4 |
| `extract_signature.py` | Cuts a signature out of a photograph and saves it as a transparent PNG |
| `add_date_signature.py` | Adds a place, date and signature rule to the foot of an existing PDF |
| `photo_to_pdf.py` | From one or more photos to a light A4 PDF, under a size cap |
| `make_cv.py` | Generates a one-page CV as a PDF from a data dictionary, in English or Italian |

### Two things worth more than the code

**Uneven light is removed by dividing, not by brightening.** When you photograph a
sheet, one half catches the lamp and the other stays in shadow. Raising the brightness
makes it worse, because it lightens the text too. *Flat-field correction* blurs the
content away to recover the map of the light, then divides the original by it: a local
correction, every area treated according to the light it actually received.

**A sheet photographed at an angle is a trapezoid, not a rotated rectangle.** On a real
case the slant of the text lines ran from 0.00° at the top to 1.00° at the bottom: no
single rotation can fix that. `clean_scan.py` measures two angles, reconstructs the
trapezoid and maps it back to a rectangle with a projective transform, iterating until
the residual drops below 0.15° (measured: 1.05° → 0.25° → 0.00°). It does not use the
edge of the sheet, which is often not detectable — it derives the geometry from the text.

---

## Install

```bash
git clone https://github.com/wilwork-de/scanfix.git && cd scanfix
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python tools/check_redaction.py document.pdf
```

The virtual environment is not fussiness: on Debian and Ubuntu the system Python is
protected (PEP 668) and a direct `pip install` is refused, because the operating
system's own tooling depends on those packages.

## Tests

```bash
PY=.venv/bin/python bash tests/run_tests.sh   # 10 assertions, Python side
npm install && node tests/test_js.mjs         # 10 assertions, JavaScript side
```

The fixtures are **generated, not collected**: `tests/make_fixtures.py` builds five
PDFs with invented names and numbers. No real document, belonging to anyone, goes into
this repository.

The two suites run against the same fixtures and must return the **same verdicts**:
`docs/redaction-check.js`, the file the site loads, is the same one Node tests, not a
parallel rewrite that can drift apart in silence.

## Licence

MIT.
