#!/usr/bin/env python3
"""
Build the scanfix site: one page per tool, plus a hub, a sitemap and robots.txt.

Why a generator and not seven hand-written HTML files: every page needs the same
head — title, description, canonical link, Open Graph tags, structured data — and
hand-copied heads drift apart the moment one page is edited. Here that block is
written once, in head(), and the pages are data.

The site's one real advantage over the tools it competes with is that nothing is
uploaded: the browser check runs locally, and the command-line tools run on your own
machine. That claim is not a footnote here — it is in every title, every meta
description and a badge at the top of every page, because it is what a person is
looking for when they search for somewhere to put a signature or a badly redacted
document.

    python3 build_site.py            # writes into docs/
"""

import html
import json
from pathlib import Path

ROOT = Path(__file__).parent
DOCS = ROOT / "docs"
SITE = "https://wilwork-de.github.io/scanfix"
REPO = "https://github.com/wilwork-de/scanfix"

PRIVACY_LINE = ("Nothing is uploaded. This page's check runs entirely inside your "
                "browser, and the command-line tools run on your own machine. The "
                "file never reaches a server — not ours, not anyone's.")

OFFLINE_LINE = ("Nothing is uploaded. The tool runs on your own machine, from your "
                "terminal: the document never leaves it and no server is involved.")


def head(page):
    """The shared head: SEO, social cards and structured data in one place."""
    url = f"{SITE}/{page['slug']}/" if page["slug"] else f"{SITE}/"
    depth = "../" if page["slug"] else ""
    schema = {
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        "name": page["h1"],
        "applicationCategory": "UtilitiesApplication",
        "operatingSystem": "Any",
        "url": url,
        "description": page["description"],
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
        "isAccessibleForFree": True,
    }
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(page['title'])}</title>
<meta name="description" content="{html.escape(page['description'])}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="website">
<meta property="og:url" content="{url}">
<meta property="og:title" content="{html.escape(page['title'])}">
<meta property="og:description" content="{html.escape(page['description'])}">
<meta name="twitter:card" content="summary">
<link rel="stylesheet" href="{depth}style.css">
<script type="application/ld+json">{json.dumps(schema)}</script>
</head>
<body>
<div class="sheet">"""


def nav(page):
    if not page["slug"]:
        return ""
    return ('<nav class="top"><a href="../">scanfix</a> / '
            f'{html.escape(page["nav_label"])}</nav>')


def badge(text):
    return (f'<div class="privacy-badge"><span aria-hidden="true">🔒</span>'
            f'<span class="body"><b>Private by construction.</b> {text}</span></div>')


def footer(page):
    # On the hub itself there is nothing to link back to: an empty href would be a
    # dead link that still looks clickable.
    back = '<a href="../">All tools</a> · ' if page["slug"] else ""
    return f"""<footer>
<p>{back}<a href="{REPO}">Source on GitHub</a> · MIT licence</p>
</footer></div></body></html>"""


def render(page):
    parts = [head(page), nav(page),
             f"<h1>{html.escape(page['h1'])}</h1>",
             f'<p class="tagline">{page["tagline"]}</p>',
             badge(page["badge"])]
    parts.append(page.get("body", ""))
    for heading, body in page.get("sections", []):
        parts.append(f"<h2>{html.escape(heading)}</h2>\n{body}")
    parts.append(footer(page))
    parts.append(page.get("script", ""))
    return "\n".join(p for p in parts if p)


def install_block(command, extra=""):
    return f"""<h2>Run it</h2>
<pre><code>git clone {REPO}.git &amp;&amp; cd scanfix
python3 -m venv .venv &amp;&amp; .venv/bin/pip install -r requirements.txt
{html.escape(command)}</code></pre>
<p class="caveat">The virtual environment is not fussiness: on Debian and Ubuntu the
system Python is protected (PEP 668) and a direct <code>pip install</code> is refused,
because the operating system's own tooling depends on those packages.</p>{extra}"""


# --- the pages --------------------------------------------------------------

TOOLS = [
    {
        "slug": "redaction-checker",
        "nav_label": "Redaction checker",
        "title": "PDF redaction checker — runs in your browser, no upload",
        "h1": "Is your PDF really redacted?",
        "description": ("Free PDF redaction checker that runs in your browser — nothing "
                        "is uploaded. Finds text still readable under black boxes."),
        "tagline": ("Find out whether the black boxes on a PDF actually removed the text, "
                    "or merely covered it."),
        "badge": PRIVACY_LINE,
        "card": ("Check a PDF's redaction",
                 "Finds text still readable under black boxes.",
                 "Runs in your browser"),
    },
    {
        "slug": "extract-signature",
        "nav_label": "Signature extractor",
        "title": "Extract a signature from a photo — offline, nothing uploaded",
        "h1": "Extract a signature from a photo",
        "description": ("Cut a handwritten signature out of a photograph and save it as a "
                        "transparent PNG, offline on your own machine. Your signature is "
                        "never uploaded to any server."),
        "tagline": ("Turn a photo of your signature into a transparent PNG you can lay on "
                    "any document."),
        "badge": OFFLINE_LINE,
        "card": ("Extract a signature",
                 "Photo of your signature to a transparent PNG.",
                 "Runs on your machine"),
    },
    {
        "slug": "clean-scan",
        "nav_label": "Scan cleanup",
        "title": "Remove shadows from a document photo — offline scan cleanup",
        "h1": "Make a photo of a document look scanned",
        "description": ("Remove shadows and uneven lighting from a photographed document, "
                        "straighten the perspective and fit it to A4. Runs offline on your "
                        "machine — no upload, no account."),
        "tagline": ("Flatten the lighting, straighten the page, and get a PDF that looks "
                    "like it came off a scanner."),
        "badge": OFFLINE_LINE,
        "card": ("Clean up a scan",
                 "Remove shadows, straighten, fit to A4.",
                 "Runs on your machine"),
    },
    {
        "slug": "sign-pdf",
        "nav_label": "Date and signature",
        "title": "Add a date and signature line to a PDF — offline, no upload",
        "h1": "Add a date and signature line to a PDF",
        "description": ("Add a place, a date and a signature rule to the foot of an existing "
                        "PDF without rebuilding it. Runs offline on your own machine; the "
                        "document is never uploaded."),
        "tagline": ("Write only what is missing at the foot of a document you already have."),
        "badge": OFFLINE_LINE,
        "card": ("Add a date and signature",
                 "Place, date and a signature rule at the foot.",
                 "Runs on your machine"),
    },
    {
        "slug": "photo-to-pdf",
        "nav_label": "Photo to PDF",
        "title": "Photo to PDF, offline — no upload, no account",
        "h1": "Turn photos into an A4 PDF",
        "description": ("Turn photos of a document into a light A4 PDF, offline on your own "
                        "machine. Fixes rotation and size. Nothing is uploaded."),
        "tagline": ("For when you printed something, signed it, photographed it, and the "
                    "form wants a PDF."),
        "badge": OFFLINE_LINE,
        "card": ("Photos to a PDF",
                 "Light A4 PDF, right way up, under a size cap.",
                 "Runs on your machine"),
    },
    {
        "slug": "make-cv",
        "nav_label": "CV generator",
        "title": "Generate a CV as a PDF — offline, English or Italian",
        "h1": "Generate a CV as a PDF",
        "description": ("Build a one-page CV as a PDF, English or Italian, with the date and "
                        "signature block in place. Offline — your details stay with you."),
        "tagline": ("A one-page CV that comes out identical every time, with the date and "
                    "signature block already where they belong."),
        "badge": ("Nothing is uploaded. Your name, address and history stay in a file on "
                  "your own machine — no form, no account, no server."),
        "card": ("Generate a CV",
                 "One page, date and signature block in place.",
                 "Runs on your machine"),
    },
]


def build():
    DOCS.mkdir(exist_ok=True)
    written = []

    for page in TOOLS:
        page.update(CONTENT.get(page["slug"], {}))
        page.setdefault("sections", [])
        target = DOCS / page["slug"] / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render(page), encoding="utf-8")
        written.append(target)

    hub_cards = "\n".join(
        f'<a class="card" href="{t["slug"]}/"><b>{html.escape(t["card"][0])}</b>'
        f'<span>{html.escape(t["card"][1])}</span>'
        f'<span class="runs">{html.escape(t["card"][2])}</span></a>'
        for t in TOOLS)

    hub = {
        "slug": "",
        "nav_label": "",
        "title": "scanfix — private PDF tools that never upload your file",
        "h1": "PDF tools that never upload your file",
        "description": ("Free PDF tools that run offline or in your browser: redaction "
                        "checker, signature extractor, scan cleanup, photo to PDF. Your "
                        "document never reaches a server."),
        "tagline": ("Six small tools for documents. Every one of them works without sending "
                    "your file anywhere."),
        "badge": ("Every tool here runs either inside your browser or on your own machine "
                  "from a terminal. There is no upload step, no account and no server to "
                  "trust — which matters most for the two documents you would least want to "
                  "hand over: your signature, and a file whose redaction might have failed."),
        "body": f'<div class="cards">{hub_cards}</div>',
        "sections": [
            ("Why it is built this way",
             "<p>Most tools that do these jobs ask you to upload the file first. For a "
             "signature, or for a document you are checking precisely because its "
             "censorship may have failed, that is the wrong shape: you would be handing a "
             "stranger the exact thing you are trying to protect.</p>"
             "<p>So the redaction check runs in the browser through pdf.js, and the rest "
             "are Python scripts you run yourself. You can disconnect from the network "
             "after this page loads and the checker still works.</p>"),
            ("Install the command-line tools",
             f"<pre><code>git clone {REPO}.git &amp;&amp; cd scanfix\n"
             "python3 -m venv .venv &amp;&amp; .venv/bin/pip install -r requirements.txt"
             "</code></pre>"),
        ],
    }
    (DOCS / "index.html").write_text(render(hub), encoding="utf-8")
    written.append(DOCS / "index.html")

    urls = [f"{SITE}/"] + [f"{SITE}/{t['slug']}/" for t in TOOLS]
    sitemap = ('<?xml version="1.0" encoding="UTF-8"?>\n'
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
               + "".join(f"  <url><loc>{u}</loc></url>\n" for u in urls)
               + "</urlset>\n")
    (DOCS / "sitemap.xml").write_text(sitemap, encoding="utf-8")
    (DOCS / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n", encoding="utf-8")
    written += [DOCS / "sitemap.xml", DOCS / "robots.txt"]

    for w in written:
        print(f"  {w.relative_to(ROOT)}")
    print(f"{len(written)} files written")



# --- per-tool content -------------------------------------------------------
# Kept apart from the metadata above so the head, the navigation and the privacy
# badge stay identical across pages while the body of each page is its own.

CONTENT = {
    "redaction-checker": {
        "body": """<div id="drop" role="button" tabindex="0" aria-label="Choose a PDF to check">
  <strong>Drop a PDF here</strong>
  <span>or click to choose one</span>
  <input type="file" id="picker" accept="application/pdf,.pdf">
</div>
<div id="result" aria-live="polite"></div>""",
        "sections": [
            ("Why a black box is not a redaction",
             "<p>A PDF is not a flattened image: it is a stack of objects drawn one over "
             "another. Putting a black rectangle over a name <strong>adds</strong> an "
             "object, it does not remove one. The name stays in the file, underneath, and "
             "comes back by selecting it with the mouse or with three lines of code. This "
             "is how court filings and government documents have leaked while their "
             "authors believed them censored, and it holds just the same for rectangles "
             "drawn in Word, for highlighter annotations, and for online tools that "
             "promise to censor a PDF for you.</p>"),
            ("How to redact for real",
             "<ol><li><strong>Remove, do not cover.</strong> A true redaction deletes the "
             "content. In PyMuPDF: <code>page.add_redact_annot(rect)</code> then "
             "<code>page.apply_redactions()</code>.</li>"
             "<li><strong>Or flatten it.</strong> Render the page to an image, cover, "
             "re-export. Crude, but it rebuilds the pixels from scratch.</li>"
             "<li><strong>Check the finished file.</strong> Not optional — it is the step "
             "everyone who has published a badly censored document skipped.</li></ol>"
             '<p class="caveat">One stated limit: a filled rectangle over text is not '
             "always a censorship. A coloured header band with white type on it, seen from "
             "the file, is exactly the same thing. That is why this tool does not return a "
             "bare verdict but shows <em>what</em> it found underneath: an account number "
             "is a leak, the document's own title is graphics. Telling them apart "
             "automatically would mean guessing at intent.</p>"),
            ("The same check from a terminal",
             "<p>Exits with code <code>1</code> when it finds a possible leak, so it drops "
             "into a pipeline or a pre-commit hook.</p>"
             + install_block(".venv/bin/python tools/check_redaction.py document.pdf")),
        ],
        "script": """<script type="module">
import * as pdfjs from "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.min.mjs";
import { analyseDocument } from "../redaction-check.js";

pdfjs.GlobalWorkerOptions.workerSrc =
  "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.worker.min.mjs";

const drop = document.getElementById("drop");
const picker = document.getElementById("picker");
const result = document.getElementById("result");
const esc = s => s.replace(/[&<>"']/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

drop.addEventListener("click", () => picker.click());
drop.addEventListener("keydown", e => {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); picker.click(); }
});
picker.addEventListener("change", e => { if (e.target.files[0]) check(e.target.files[0]); });
for (const t of ["dragenter", "dragover"])
  drop.addEventListener(t, e => { e.preventDefault(); drop.classList.add("over"); });
for (const t of ["dragleave", "drop"])
  drop.addEventListener(t, e => { e.preventDefault(); drop.classList.remove("over"); });
drop.addEventListener("drop", e => { const f = e.dataTransfer.files[0]; if (f) check(f); });

async function check(file) {
  result.innerHTML = `<p style="color:var(--muted)">Analysing <b>${esc(file.name)}</b>…</p>`;
  try {
    const data = new Uint8Array(await file.arrayBuffer());
    const pdf = await pdfjs.getDocument({ data, isEvalSupported: false }).promise;
    render(file.name, await analyseDocument(pdf, pdfjs.OPS));
    await pdf.destroy();
  } catch (err) {
    result.innerHTML = `<div class="verdict suspect"><h3>Could not read it</h3>
      <p>${esc(String(err && err.message || err))}</p></div>`;
  }
}

function render(name, r) {
  if (r.verdict === "CLEAN") {
    result.innerHTML = `<div class="verdict clean"><h3>No suspicious covers</h3>
      <p>${esc(name)} — ${r.totalPages} pages. No opaque shape sits over still-extractable
      content. Note this says the document does not have <em>this</em> defect, not that it
      holds no confidential data in plain sight.</p></div>`;
    return;
  }
  const count = r.pages.reduce((n, p) => n + p.findings.length, 0);
  let html = `<div class="verdict suspect"><h3>Redaction is not reliable</h3>
    <p>${esc(name)} — ${count} opaque shapes over still-extractable content.
    Below is what reads back from under the covers.</p></div>`;
  for (const p of r.pages) for (const f of p.findings) {
    html += `<div class="finding"><div class="where">page ${p.page} · ${esc(f.source)}
      · box [${f.box.join(", ")}]</div>`;
    if (f.textUnderneath) html += `<div class="recovered">${esc(f.textUnderneath)}</div>`;
    if (f.overImage) html += `<p class="image-note" style="margin:${f.textUnderneath ? "8px" : "0"} 0 0">
      Covers an image: the content is recovered by extracting the embedded image,
      which nothing drawn on top of it modifies.</p>`;
    html += `</div>`;
  }
  result.innerHTML = html;
}
</script>""",
    },

    "extract-signature": {
        "sections": [
            ("What it does",
             "<p>You photograph your signature, and it comes back as a PNG with a "
             "transparent background, trimmed to the strokes. Lay it on a contract, a form "
             "or a CV and the document stays sharp text instead of becoming a blurry scan "
             "of a printed page.</p>"
             "<p>The separation is not a hard threshold. The illumination is corrected "
             "first, then the alpha channel is built from how dark each pixel is: light "
             "paper becomes transparent, dark ink opaque, and the values between stay "
             "semi-transparent. That keeps the edges smooth — a hard cut-off produces a "
             "jagged signature that looks obviously pasted.</p>"),
            ("Sign on a blank sheet",
             "<p>This is the one tip that matters. Sign a plain white sheet and photograph "
             "that, rather than photographing a form you have already signed. On a form the "
             "printed signature rule runs through your signature, and separating the two is "
             "genuinely hard: on a real case the rule was tilted just enough that its "
             "longest unbroken run in any pixel row reached 15% of the width while the "
             "signature's own strokes reached 13% — the two overlap, so no threshold "
             "removes one without eating the other.</p>"
             "<p>On a blank sheet there is nothing to separate.</p>"),
            ("Run it", install_block(
                ".venv/bin/python tools/extract_signature.py photo.jpg -o signature.png",
                "<p>Not sure which part of the photo to use? "
                "<code>--preview grid.png</code> writes a copy with a labelled grid, so you "
                "can read the four numbers off it and pass <code>--box x0,y0,x1,y1</code>. "
                "<code>--blue</code> keeps the pen colour instead of forcing black.</p>")),
        ],
    },

    "clean-scan": {
        "sections": [
            ("Uneven light is removed by dividing, not by brightening",
             "<p>When you photograph a sheet, one half catches the lamp and the other stays "
             "in shadow — the top looks like a document and the bottom looks like a "
             "snapshot. Raising the brightness makes it worse, because it lightens the text "
             "too and washes out the half that was already fine.</p>"
             "<p><em>Flat-field correction</em> blurs the content away hard, which leaves "
             "only the map of how light fell across the sheet, then divides the original by "
             "that map. Where the paper was dark you divide by a small number and brighten "
             "a lot; where it was already bright almost nothing changes. It is a local "
             "correction, so every area is treated according to the light it actually "
             "received. That is why it works where plain brightness fails.</p>"),
            ("A sheet photographed at an angle is a trapezoid",
             "<p>Not a rotated rectangle — which means no single rotation angle can "
             "straighten it. On a real case the slant of the text lines ran from 0.00° at "
             "the top to 1.00° at the bottom.</p>"
             "<p>The tool measures two angles, one high on the page and one low, "
             "reconstructs the actual trapezoid and maps it back to a rectangle with a "
             "projective transform, iterating until the residual falls below 0.15° "
             "(measured: 1.05° → 0.25° → 0.00°). It does not need the edge of the sheet, "
             "which often is not detectable — on that case the background was brighter than "
             "the paper. It derives the geometry from the text itself.</p>"
             '<p class="caveat">Straightening crops to the block of text, so it takes the '
             "sheet's margins with it. They are rebuilt afterwards, at the proportions of a "
             "normal document. If you prefer the page exactly as shot, "
             "<code>--no-straighten</code> and <code>--no-fit</code> turn both steps off.</p>"),
            ("Run it", install_block(
                ".venv/bin/python tools/clean_scan.py photo.jpg -o clean.pdf",
                "<p>It reports the real resolution of your photo on the page. Below about "
                "150 dpi the text stays soft: cleaning removes the shadow but cannot invent "
                "detail the camera never captured, so a closer photo beats any amount of "
                "processing.</p>")),
        ],
    },

    "sign-pdf": {
        "sections": [
            ("What it adds, and what it leaves alone",
             "<p>Place and date on the left, a label and a signature rule on the right, at "
             "the foot of the last page. Nothing else is touched: layout, fonts and "
             "pagination stay exactly as they were, and the block is anchored to the "
             "document's own margins, read from the file rather than assumed.</p>"
             "<p>Afterwards it re-extracts the text and checks two things: that the date is "
             "actually readable by a parser, and that no line of the original disappeared. "
             "It says so if either fails.</p>"),
            ("Two things that look reasonable and do not work",
             "<p><strong>Reusing the font embedded in the PDF</strong> so the addition "
             "blends in. Embedded fonts are subsets: they carry only the glyphs that "
             "document needed, with their own internal encoding. Re-inserting one produces "
             "text that displays on screen but extracts as null bytes — the PDF looks right "
             "and a parser reads no date at all. Helvetica is used instead.</p>"
             "<p><strong>Replacing placeholders inside the PDF.</strong> Redaction deletes "
             "every piece of text whose box touches the chosen area, and those boxes are "
             "inflated by line spacing: removing a heading also removed the contact line "
             "below it, with no error. Placeholders belong in the source document; this "
             "tool only reports them.</p>"),
            ("Run it", install_block(
                '.venv/bin/python tools/add_date_signature.py document.pdf --place Turin',
                "<p><code>--signature signature.png</code> lays a real signature on the "
                "rule. <code>--locale it --label Firma</code> switches the date and the "
                "label to Italian. If the last page is full the block goes onto a new "
                "sheet, and it tells you, rather than quietly making a one-page document "
                "into two.</p>")),
        ],
    },

    "photo-to-pdf": {
        "sections": [
            ("What it does",
             "<p>Straight conversion, one photo per page. It fixes the rotation from the "
             "EXIF data — phone photos are almost always rotated in the metadata rather "
             "than in the pixels, so some viewers turn them and others do not, and your "
             "document arrives lying on its side. Then greyscale, which costs nothing on a "
             "document and cuts about two thirds of the weight, a flattened white "
             "background, and A4 layout.</p>"
             "<p>If the result overshoots the size cap it steps the resolution down and "
             "tries again, rather than handing you a file the upload form will reject. "
             "For heavier correction — shadows, perspective — use "
             '<a href="../clean-scan/">the scan cleanup</a> instead.</p>'),
            ("One thing not to do",
             "<p>Do not rename <code>photo.jpg</code> to <code>photo.pdf</code>. The name "
             "does not change the contents: it is still a JPEG, and a portal rejects it by "
             "reading the first bytes, which say <code>JFIF</code> rather than "
             "<code>%PDF</code>. Obvious written down, extremely common in practice.</p>"),
            ("Run it", install_block(
                ".venv/bin/python tools/photo_to_pdf.py photo.jpg -o document.pdf",
                "<p>Pass several images to get several pages, in the order you list them. "
                "<code>--max-mb 1.5</code> tightens the size cap.</p>")),
        ],
    },

    "make-cv": {
        "sections": [
            ("What it does",
             "<p>You fill in a dictionary at the top of the file and it builds a one-page "
             "PDF: the same output every time, text that stays selectable so an applicant "
             "tracking system can read it, and a date at the foot that updates itself.</p>"
             "<p>Empty sections disappear rather than printing an empty heading, and the "
             "signature block goes where an institution expects it: the data-protection "
             "line first, then place and date on the left with the signature on the "
             "right.</p>"),
            ("English or Italian",
             "<p><code>--locale en</code> or <code>--locale it</code> switches the headings "
             "and the spelled-out date. The Italian version also carries the GDPR "
             "authorisation clause, which Italian employers and public bodies expect.</p>"
             '<p class="caveat">A detail worth knowing if you write that clause yourself: '
             "do not cite <em>art. 13 del D.Lgs. 196/2003</em>. That article was repealed "
             "by D.Lgs. 101/2018, which harmonised the Italian Code with the GDPR — "
             "disclosure is now governed by articles 13 and 14 of the Regulation. Half the "
             "templates online still cite the repealed one.</p>"),
            ("Run it", install_block(
                ".venv/bin/python tools/make_cv.py --locale en -o cv.pdf",
                "<p>Institutional portals often want a <em>handwritten</em> signature, not a "
                "typed name. Sign a blank sheet, cut it out with "
                '<a href="../extract-signature/">the signature extractor</a>, and pass '
                "<code>--signature signature.png</code>.</p>")),
        ],
    },
}

if __name__ == "__main__":
    build()
