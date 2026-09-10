# Open work and the reasoning behind the current shape

Written 10 Sep 2026, after a privacy audit of the published site and tools. The two
issues below were found by testing, not by reading, and neither is fixed yet.

## Known issues

### 1. Signing a PDF carries over every piece of the source document's metadata

Reproduced. Build a PDF with metadata, sign it, read the metadata back:

```python
import pymupdf
doc = pymupdf.open(); page = doc.new_page()
page.insert_text((60, 90), "A contract.", fontname="helv", fontsize=12)
doc.set_metadata({"title": "Draft contract v3", "author": "Jane Doe",
                  "producer": "SecretCorp Editor 4.2", "subject": "internal only",
                  "keywords": "confidential, do-not-share"})
doc.save("source.pdf")
# python3 tools/add_date_signature.py source.pdf --place Turin -o signed.pdf
print(pymupdf.open("signed.pdf").metadata)
```

Every field survives verbatim: `author: Jane Doe`, `subject: internal only`,
`keywords: confidential, do-not-share`, `producer: SecretCorp Editor 4.2`. You sign a
document, send it on, and it travels with the name of whoever drafted it, an
internal-only marking and the name of the corporate software that produced it. None
of it is visible on the page and all of it reads back in two seconds.

The browser path has the same hole for a different reason: `docs/sign-core.js` sets
no metadata at all, and pdf-lib preserves what the source carried.

**Not obvious to find.** It only showed up because a PDF was built specifically with
fake metadata in it to see what came through. A future audit will not stumble on it.

**Proposed fix, with one decision still open:** always report what metadata is riding
along, and offer removal. Whether removal should be the *default* is the owner's call
and is listed below, because stripping alters a document that may need to be handed
over unchanged.

### 2. The CV generator writes the person's name into the PDF metadata

`docs/cv-core.js` calls `setTitle("Curriculum Vitae - <name>")` and
`setAuthor(<name>)`; `tools/make_cv.py` does the same through fpdf2. On a CV the name
is on the page anyway, so on its own this is mild. It stops being mild when someone
later covers the visible name and assumes the file is anonymous, because metadata
survives cropping, conversion and re-export.

Fix: make it optional and off by default, or state plainly on the page that it happens.

## Hardening not done yet

3. **`script-src 'unsafe-inline'`.** The CSP blocks every outbound connection but
   would still execute an injected inline script. Replace with the SHA-256 hashes of
   the JSON-LD blocks and drop `'unsafe-inline'` from `script-src` entirely. Leave it
   on `style-src`: the draggable crop box needs inline positions and the risk there is
   cosmetic.

4. **No `Referrer-Policy`, and the outbound GitHub link has no `rel`.** Add
   `<meta name="referrer" content="no-referrer">` and
   `rel="noopener noreferrer"`. Otherwise clicking "Source on GitHub" tells GitHub
   which tool page the visitor came from, which is to say what they were doing.

5. **The structural residue.** GitHub Pages sees the visitor's IP, which page, when,
   and the User-Agent. Before that, DNS and the TLS SNI tell their ISP they visited
   the site at all. No CSP can touch this: the only fix is not needing the server.
   - a **Service Worker** that caches everything on first load, so later visits make
     zero requests;
   - a **downloadable single-file HTML** per tool that runs from `file://`, so after
     one download there is no server involved ever again, and the tool survives the
     site disappearing.

## Verified sound, do not re-audit

- **EXIF, including GPS, is stripped.** Tested with a JPEG carrying camera make and
  model, a timestamp and coordinates for Turin. The output PDF contains none of it,
  not even the literal string `Exif`. Both paths re-encode the pixels, Pillow on the
  CLI and a canvas in the browser, and neither copies EXIF forward.
- PDFs produced from photographs carry no metadata at all beyond `format: PDF 1.7`.
- No `localStorage`, no `sessionStorage`, no IndexedDB, no cookies anywhere.
- The uploaded file's name is displayed and used to name the download, and never
  leaves the browser.
- CSP live and intact, `connect-src 'none'` included. No subresource loads off-origin.

## Why the site is shaped this way

Decided 8-9 Sep 2026. Recording it because the reasoning is not visible in the result,
and without it the positioning gets re-argued from scratch.

The site used to be one page that led with the redaction checker. Counting the
dedicated competitors somebody thought worth building, as a proxy for demand:

| Need | Dedicated competitors found | Read |
|---|---|---|
| Signature extraction | 7 (Fotor, Picsart, Pixelcut, OnlinePNGTools, Pokecut, AnyEraser, aitextextractors) | Highest demand of the three, and a narrow single-purpose job |
| Scan cleanup / shadow removal | 6 (Scanner Pro, Genius Scan, iScanner, LensUp, and others) | Very high demand, but dominated by mobile apps; the desktop and browser niche is thinner |
| Redaction checking | 5 (PDF X-ray, Redactr, Tamperlens, RedactifyAI, redactpdf.io) | Real demand, specialist audience, lower volume, higher stakes |
| Merge / compress / convert | Smallpdf, iLovePDF, Adobe, PDF24 | Not a field to compete in |

So the page was leading with the *least* demanded of the three and burying the other
two at the bottom. Hence one page per tool: someone arriving from a search wants one
answer, not a catalogue.

**The positioning follows from the same table.** Nearly all of those competitors
upload the file to a server. The two documents a person would least want to hand to a
stranger are their own signature and a file whose redaction may have failed. Running
everything locally is the one thing this toolkit does that the field does not, so it
belongs in every title, every meta description and a badge on every page, not in a
footnote. That is also why the CSP matters: it turns the claim from something to be
believed into something the browser enforces.

## Decisions waiting on the owner

- **The first commit message is still in Italian** (`6bf4793`). Fixing it means
  rewriting published history and force pushing. The repo is new and almost certainly
  uncloned, so the risk is negligible, but it is not a call to make unasked.
- **Metadata on signing: strip by default, or keep and warn?** Stripping protects the
  sender; keeping preserves a document that may have to be delivered unaltered. The
  default should be whichever the owner prefers, with the other available as a flag.
- **Whether to build the hardening package** in items 3 to 5 above.
