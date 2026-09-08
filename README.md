# scanfix

Six tools for the paperwork nobody enjoys: clean up a phone photo of a signed sheet,
put a date and a signature at the foot of a PDF, build a one-page CV, and **check
whether a redaction actually holds**.

All six run in the browser, and the file never leaves the tab.

**<https://wilwork-de.github.io/scanfix/>**

| | |
|---|---|
| [Redaction checker](https://wilwork-de.github.io/scanfix/redaction-checker/) | reads back whatever is still under the black boxes |
| [Signature extractor](https://wilwork-de.github.io/scanfix/extract-signature/) | photo of your signature to a transparent PNG |
| [Scan cleanup](https://wilwork-de.github.io/scanfix/clean-scan/) | shadow gone, page straight, fitted to A4 |
| [Date and signature](https://wilwork-de.github.io/scanfix/sign-pdf/) | place, date and a rule at the foot of a PDF |
| [Photo to PDF](https://wilwork-de.github.io/scanfix/photo-to-pdf/) | light A4 PDF, right way up, under a size cap |
| [CV generator](https://wilwork-de.github.io/scanfix/make-cv/) | one page, English or Italian, signature block in place |

The same six exist as Python scripts in `tools/`, for when you have a folder of files
rather than one.

## Nothing is uploaded, and the browser is what guarantees it

Most tools that do these jobs ask you to upload first. Think about what that means for
a signature, or for a document you are checking precisely because its censorship may
have failed. You would be handing over the exact thing you are trying to protect.

So every page here is served with this policy:

```
default-src 'self'; connect-src 'none'; img-src 'self' data: blob:;
style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline';
worker-src 'self' blob:; object-src 'none'; base-uri 'none'; form-action 'none'
```

`connect-src 'none'` is the line that matters. No fetch, no XHR, no WebSocket, no
beacon. Not "we promise not to upload your file" but "this page is not permitted to
open a network connection", enforced by the browser rather than by our good intentions.

Two things follow from it. pdf.js and pdf-lib are committed in `docs/vendor/` instead
of loaded from a CDN, because `default-src 'self'` forbids the CDN and because a CDN
would otherwise see who reads a document and when. And the results come back as blob
URLs on a download link, since a page that cannot open a connection cannot fetch its
own output either.

Load a page, turn off your wi-fi, then use the tool. It keeps working.

## The redaction check

A PDF is a stack of objects drawn one over another, not a flat picture. Drawing a
black rectangle over a name adds an object. It does not delete one. The name stays in
the file, underneath, and it comes back by selecting it with a mouse or with three
lines of code. Court filings and government documents have leaked this way while the
people who published them believed the text was gone, and the same trap catches
rectangles drawn in Word, highlighter annotations, and the online tools that offer to
censor a PDF for you.

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

### Why it prints the text instead of a verdict

A filled rectangle over text is not always a censorship. A coloured header band with
white type on it looks identical from inside the file. Showing *what* is underneath
lets a person decide in a second: an account number is a leak, the document's own
title is graphics. Doing it automatically would mean guessing at the intent of whoever
laid the page out, and this tool does not try. The known false positive is one of the
seven test fixtures, on purpose.

### How to redact for real

1. **Remove instead of covering**: `page.add_redact_annot(rect)` followed by
   `page.apply_redactions()`.
2. **Or flatten**: render the page to an image, cover, re-export. Crude, and it works,
   because the pixels get rebuilt from scratch.
3. **Check the finished file.** Not optional, and it is the step skipped by everyone
   who has ever published a badly censored document.

## Two things worth more than the code

**Uneven light comes out by dividing, not by brightening.** When you photograph a
sheet, one half catches the lamp and the other stays in shadow. Raising the brightness
makes it worse, because it lightens the text too. *Flat-field correction* blurs the
content away to recover the map of the light, then divides the original by it. Where
the paper was dark you divide by a small number and brighten a lot; where it was
already bright, almost nothing changes. The correction is local, so every area gets
treated according to the light it actually received.

**A sheet photographed at an angle is a trapezoid, not a rotated rectangle.** On a real
case the slant of the text lines ran from 0.00° at the top to 1.00° at the bottom, and
no single rotation fixes that. The tool measures two angles, reconstructs the trapezoid
and maps it back to a rectangle with a projective transform, iterating until the
residual drops below 0.15° (measured: 1.05° → 0.25° → 0.00°). It never looks for the
edge of the sheet, which is often not detectable. All the geometry comes from the text.

## How it is put together

```
docs/
  imaging.js        flat-field correction, signature alpha, deskew, A4 fitting
  redaction-check.js  the redaction analysis
  sign-core.js      the date and signature block, and the check that it reads back
  cv-core.js        the CV layout, in millimetres, over pdf-lib
  pdfout.js         images onto A4 pages
  app/*.js          one file per page: file pickers, canvases, download links
  vendor/           pdf.js and pdf-lib, committed and checksummed
tools/*.py          the same six algorithms as command-line scripts
```

The split is the point. Nothing in `docs/imaging.js`, `sign-core.js`, `cv-core.js` or
`pdfout.js` touches the DOM: they take typed arrays and return typed arrays, and
pdf.js and pdf-lib are passed in rather than imported. That is what lets Node run the
exact files the site loads, instead of a parallel copy that drifts.

## Install the command-line tools

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
PY=.venv/bin/python bash tests/run_tests.sh   # 10 assertions, the Python checker
npm install
node tests/test_js.mjs                        # 10 assertions, the JS checker
node tests/test_imaging.mjs                   # 19 assertions, the image maths
node tests/test_pdf.mjs                       # 31 assertions, the PDFs it writes
```

`test_imaging.mjs` checks the ported maths against the Python it came from: the
reference numbers are printed by `tests/imaging_reference.py`, which runs the Python
functions on the same synthetic page the JavaScript builds. `test_pdf.mjs` writes real
PDFs with the vendored pdf-lib and opens each one again with pdf.js, because producing
bytes is easy and producing bytes a reader can parse is not.

There is a fifth suite that drives the pages in headless Chrome, with the CSP active,
and clicks each download link to check the file that lands on disk:

```bash
npm install --no-save puppeteer
node tests/test_browser.mjs                   # 19 assertions
```

Puppeteer is not in `package.json` because it drags a whole browser down with it, and
nobody cloning this to read six Python scripts should pay for that. The suite says so
and exits quietly if it is missing.

The fixtures are **generated, not collected**: `tests/make_fixtures.py` builds five
PDFs, a photographed page and a cut-out signature, all with invented names and numbers.
No real document, belonging to anyone, goes into this repository.

## The site

`python3 build_site.py` regenerates the HTML in `docs/`: one page per tool, plus the
hub, a sitemap and robots.txt. It is a generator rather than seven hand-written files
because every page needs the same head (title, description, canonical, Open Graph,
structured data, the CSP), and hand-copied heads drift apart the moment one page is
edited.

It writes only the HTML. `docs/style.css`, `docs/app/`, `docs/vendor/` and the core
modules are checked in and edited directly.

## Licence

MIT. The vendored libraries keep their own: pdf.js is Apache-2.0, pdf-lib is MIT.
See `docs/vendor/README.md`.
