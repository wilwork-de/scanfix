#!/usr/bin/env python3
"""
Build the scanfix site: one page per tool, plus a hub, a sitemap and robots.txt.

Why a generator and not seven hand-written HTML files: every page needs the same
head - title, description, canonical link, Open Graph tags, structured data and the
Content-Security-Policy - and hand-copied heads drift apart the moment one page is
edited. Here that block is written once, in head(), and the pages are data.

The site's one real advantage over the tools it competes with is that nothing is
uploaded. Every tool runs in the browser, the third-party libraries are served from
this origin, and the CSP forbids the page to open a network connection at all. That
claim is in every title, every meta description and a badge at the top of every page,
because it is what a person is looking for when they search for somewhere to put a
signature or a badly redacted document.

    python3 build_site.py            # writes into docs/
"""

import html
import json
from pathlib import Path

ROOT = Path(__file__).parent
DOCS = ROOT / "docs"
SITE = "https://wilwork-de.github.io/scanfix"
REPO = "https://github.com/wilwork-de/scanfix"

# The policy the browser enforces on us.
#
#   connect-src 'none'   no fetch, no XHR, no WebSocket, no beacon. This is the
#                        line that turns "we do not upload your file" from a promise
#                        into something the browser refuses to let the page do.
#   default-src 'self'   scripts, styles and everything else come from this origin.
#                        pdf.js and pdf-lib live in docs/vendor/ for exactly this.
#   worker-src blob:     pdf.js runs its parser in a worker and falls back to a blob
#                        URL when the module worker cannot be created directly.
#   img-src data: blob:  canvas previews and the finished files are blob URLs.
#   'unsafe-inline'      only for the JSON-LD block and the style attributes the crop
#                        box sets while it is dragged. No inline JavaScript is
#                        executed anywhere: every page script is a module file under
#                        docs/app/.
CSP = ("default-src 'self'; connect-src 'none'; img-src 'self' data: blob:; "
       "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
       "worker-src 'self' blob:; object-src 'none'; base-uri 'none'; "
       "form-action 'none'")

BADGE = ("Nothing is uploaded. This tool runs inside your browser, on your own "
         "machine, and the page is served with a policy that forbids it to open a "
         "network connection at all. Your file has nowhere to go.")


def head(page):
    """The shared head: SEO, social cards, structured data and the CSP in one place."""
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
<meta http-equiv="Content-Security-Policy" content="{CSP}">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(page['title'])}</title>
<meta name="description" content="{html.escape(page['description'])}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="website">
<meta property="og:url" content="{url}">
<meta property="og:title" content="{html.escape(page['title'])}">
<meta property="og:description" content="{html.escape(page['description'])}">
<meta name="twitter:card" content="summary">
<link rel="icon" href="{depth}favicon.svg" type="image/svg+xml">
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
    return (f'<div class="privacy-badge"><span aria-hidden="true">&#128274;</span>'
            f'<span class="body"><b>Private by construction.</b> {text}</span></div>')


def footer(page):
    # On the hub itself there is nothing to link back to: an empty href would be a
    # dead link that still looks clickable.
    back = '<a href="../">All tools</a> &middot; ' if page["slug"] else ""
    return f"""<footer>
<p>{back}<a href="{REPO}">Source on GitHub</a> &middot; MIT licence</p>
</footer></div></body></html>"""


def render(page):
    parts = [head(page), nav(page),
             f"<h1>{html.escape(page['h1'])}</h1>",
             f'<p class="tagline">{page["tagline"]}</p>',
             badge(page.get("badge", BADGE)),
             page.get("lead", ""),
             page.get("body", "")]
    for heading, body in page.get("sections", []):
        parts.append(f"<h2>{html.escape(heading)}</h2>\n{body}")
    parts.append(footer(page))
    if page["slug"]:
        parts.append(f'<script type="module" src="../app/{page["slug"]}.js"></script>')
    return "\n".join(p for p in parts if p)


def cli_block(command, extra=""):
    """The command-line alternative, offered after the browser tool, not before."""
    return f"""<p>The browser tool above is the same algorithm. Use the script when you
have forty files to get through, or when you want it inside a pipeline.</p>
<pre><code>git clone {REPO}.git &amp;&amp; cd scanfix
python3 -m venv .venv &amp;&amp; .venv/bin/pip install -r requirements.txt
{html.escape(command)}</code></pre>
<p class="caveat">The virtual environment is not fussiness. On Debian and Ubuntu the
system Python is protected (PEP 668) and a direct <code>pip install</code> is refused,
because the operating system's own tooling depends on those packages.</p>{extra}"""


# --- the pages --------------------------------------------------------------

TOOLS = [
    {
        "slug": "redaction-checker",
        "nav_label": "Redaction checker",
        "title": "PDF redaction checker - runs in your browser, no upload",
        "h1": "Is your PDF really redacted?",
        "description": ("Free PDF redaction checker that runs in your browser. Nothing "
                        "is uploaded. Finds text still readable under black boxes."),
        "tagline": ("Find out whether those black boxes removed the text or only covered "
                    "it up."),
        "card": ("Check a PDF's redaction",
                 "Reads back whatever is still under the black boxes."),
    },
    {
        "slug": "extract-signature",
        "nav_label": "Signature extractor",
        "title": "Extract a signature from a photo - in your browser, nothing uploaded",
        "h1": "Extract a signature from a photo",
        "description": ("Cut a handwritten signature out of a photograph and save it as a "
                        "transparent PNG, entirely in your browser. Your signature is never "
                        "uploaded to any server."),
        "tagline": ("Turn a photo of your signature into a transparent PNG you can lay on "
                    "any document."),
        "card": ("Extract a signature",
                 "Photo of your signature to a transparent PNG."),
    },
    {
        "slug": "clean-scan",
        "nav_label": "Scan cleanup",
        "title": "Remove shadows from a document photo - offline scan cleanup",
        "h1": "Make a photo of a document look scanned",
        "description": ("Remove shadows and uneven lighting from a photographed document, "
                        "straighten the perspective and fit it to A4. Runs in your browser: "
                        "no upload, no account."),
        "tagline": ("Flatten the light, straighten the page, get a PDF that looks like it "
                    "came off a scanner."),
        "card": ("Clean up a scan",
                 "Shadow gone, page straight, fitted to A4."),
    },
    {
        "slug": "sign-pdf",
        "nav_label": "Date and signature",
        "title": "Add a date and signature line to a PDF - no upload",
        "h1": "Add a date and signature line to a PDF",
        "description": ("Add a place, a date and a signature rule to the foot of an existing "
                        "PDF without rebuilding it. Runs in your browser; the document is "
                        "never uploaded."),
        "tagline": "Write only what is missing at the foot of a document you already have.",
        "card": ("Add a date and signature",
                 "Place, date and a signature rule at the foot."),
    },
    {
        "slug": "photo-to-pdf",
        "nav_label": "Photo to PDF",
        "title": "Photo to PDF in your browser - no upload, no account",
        "h1": "Turn photos into an A4 PDF",
        "description": ("Turn photos of a document into a light A4 PDF, in your browser. "
                        "Fixes the rotation and the size. Nothing is uploaded."),
        "tagline": ("For when you printed something, signed it, photographed it, and the "
                    "form wants a PDF."),
        "card": ("Photos to a PDF",
                 "Light A4 PDF, right way up, under a size cap."),
    },
    {
        "slug": "make-cv",
        "nav_label": "CV generator",
        "title": "Generate a CV as a PDF - in your browser, English or Italian",
        "h1": "Generate a CV as a PDF",
        "description": ("Build a one-page CV as a PDF, English or Italian, with the date and "
                        "signature block in place. Runs in your browser: your details stay "
                        "in the tab."),
        "tagline": ("One page, English or Italian, with the date and signature block already "
                    "where they belong."),
        "card": ("Generate a CV",
                 "One page, date and signature block in place."),
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
        f'<span class="runs">Runs in your browser</span></a>'
        for t in TOOLS)

    hub = {
        "slug": "",
        "nav_label": "",
        "title": "scanfix - PDF tools that never upload your file",
        "h1": "PDF tools that never upload your file",
        "description": ("Free PDF tools that run entirely in your browser: redaction "
                        "checker, signature extractor, scan cleanup, photo to PDF, CV "
                        "generator. Your document never reaches a server."),
        "tagline": ("Six small tools for the paperwork nobody enjoys. Not one of them sends "
                    "your document anywhere."),
        "badge": ("Every tool here runs inside your browser. There is no upload step, no "
                  "account, and no server holding your file for the afternoon. That matters "
                  "most for the two documents you would least want to hand to a stranger: "
                  "your signature, and a file whose redaction might have failed."),
        "body": f'<div class="cards">{hub_cards}</div>',
        "sections": [
            ("Why it works this way",
             "<p>Most tools that do these jobs ask you to upload first. Think about what "
             "that means for a signature, or for a document you are checking precisely "
             "because its censorship may have failed. You would be handing over the exact "
             "thing you are trying to protect, to a company whose retention policy you have "
             "not read.</p>"
             "<p>So the work happens here, in the tab. Each page carries its own copy of "
             "pdf.js and pdf-lib and loads nothing from anywhere else, and each one is "
             "served with a Content-Security-Policy that sets "
             "<code>connect-src&nbsp;'none'</code>. A privacy policy is a promise. This is "
             "the browser refusing, on your behalf, to let the page open a connection at "
             "all.</p>"),
            ("Try breaking it",
             "<p>Open any tool, turn off your wi-fi, then use it. It keeps working. Or leave "
             "the network tab of the developer console open while you convert a file and "
             "watch it stay empty.</p>"),
            ("The same tools from a terminal",
             "<p>Every one of these started as a Python script, and the scripts are still "
             "here. Reach for them when you have a folder of files rather than one.</p>"
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
    print("  (docs/app/, docs/vendor/ and the core modules in docs/ are checked in, "
          "not generated)")


# --- per-tool content -------------------------------------------------------
# Kept apart from the metadata above so the head, the navigation and the privacy
# badge stay identical across pages while the body of each page is its own.

DROP = """<div id="drop" role="button" tabindex="0" aria-label="{aria}">
  <strong>{strong}</strong>
  <span>{sub}</span>
  <input type="file" id="picker" accept="{accept}"{multiple}>
</div>"""

CONTENT = {
    "redaction-checker": {
        "lead": "<p class=\"lead\">You blacked out a name in a document before sending it "
                "on. Or one landed in your inbox with rectangles over the sensitive parts, "
                "and you want to know whether they hold. Drop it below.</p>",
        "body": DROP.format(aria="Choose a PDF to check", strong="Drop a PDF here",
                            sub="or click to choose one", accept="application/pdf,.pdf",
                            multiple="") + """
<div id="result" aria-live="polite"></div>""",
        "sections": [
            ("Why a black box is often not a redaction",
             "<p>A PDF is a stack of objects drawn one over another, not a flat picture. "
             "Drawing a black rectangle over a name adds an object. It does not delete one. "
             "The name is still in the file, underneath, and it comes back by selecting it "
             "with a mouse or with three lines of code.</p>"
             "<p>Court filings and government documents have leaked this way while the "
             "people who published them believed the text was gone. The same trap catches "
             "rectangles drawn in Word, highlighter annotations, and the online tools that "
             "offer to censor a PDF for you.</p>"),
            ("How to redact so that it holds",
             "<ol><li><strong>Remove the content instead of covering it.</strong> In "
             "PyMuPDF: <code>page.add_redact_annot(rect)</code>, then "
             "<code>page.apply_redactions()</code>.</li>"
             "<li><strong>Or flatten the page.</strong> Render it to an image, cover, "
             "re-export. Crude, and it works, because the pixels get rebuilt from "
             "scratch.</li>"
             "<li><strong>Then check the finished file.</strong> This is the step everyone "
             "who has ever published a badly censored document skipped.</li></ol>"
             '<p class="caveat">One thing the checker cannot decide for you. A filled '
             "rectangle over text is not always a censorship: a coloured header band with "
             "white type on it looks identical from inside the file. That is why you get the "
             "text it found rather than a bare verdict. An account number is a leak. The "
             "document's own title is graphics. Telling those apart automatically would mean "
             "guessing at what the person laying out the page meant.</p>"),
            ("The same check from a terminal",
             "<p>It exits with code <code>1</code> when it finds a possible leak, so it drops "
             "into a pipeline or a pre-commit hook.</p>"
             + cli_block(".venv/bin/python tools/check_redaction.py document.pdf")),
        ],
    },

    "clean-scan": {
        "lead": "<p class=\"lead\">You printed a form, signed it, and photographed it on the "
                "kitchen table because you do not own a scanner. Half the page is in shadow "
                "and the paper looks grey. Drop the photo in and you get back a PDF that "
                "looks like it came out of an office machine.</p>",
        "body": DROP.format(aria="Choose a photo of a document",
                            strong="Drop a photo of the page here",
                            sub="or click to choose one. A PDF holding a photograph works too.",
                            accept="image/*,application/pdf,.pdf", multiple="") + """
<div class="controls">
  <label><input type="checkbox" id="straighten" checked> Straighten the perspective</label>
  <label><input type="checkbox" id="fit" checked> Rebuild the margins at A4</label>
  <label><input type="checkbox" id="colour"> Keep the colour, for blue ink</label>
  <label class="slider">Whiter paper
    <input type="range" id="strength" min="1" max="1.15" step="0.01" value="1.06"></label>
  <label>Resolution
    <select id="dpi">
      <option value="150">150 dpi</option>
      <option value="200" selected>200 dpi</option>
      <option value="300">300 dpi</option>
    </select></label>
</div>
<p id="state" class="status" aria-live="polite"></p>
<div id="preview" class="preview"></div>
<a id="save" class="button" hidden>Save the PDF</a>
<div id="notes" class="notes"></div>""",
        "sections": [
            ("What it does to the photograph",
             "<p>Three things, in this order. It evens out the light, so the shadow of your "
             "hand or the lamp on one side stops showing. It straightens the page if you "
             "shot it at an angle. Then it rebuilds the sheet at A4 proportions with proper "
             "margins, so the document fills the page instead of floating in the middle of "
             "it.</p>"
             "<p>Each step has a switch. If the photo is already square on, turn the "
             "straightening off and save yourself the resampling.</p>"),
            ("The detail, if you want it: uneven light comes out by dividing",
             "<p>Turning the brightness up makes a shadowed photo worse. It lightens the ink "
             "along with the paper and blows out the half that was already fine.</p>"
             "<p>The technique that works is called flat-field correction. Blur the image "
             "hard enough that the text disappears, and what is left is a map of how the "
             "light fell across the sheet. Then divide the original by that map. Where the "
             "paper was dark you are dividing by a small number and you brighten a lot; "
             "where it was already bright, almost nothing changes. The correction is local. "
             "Every part of the page gets treated according to the light it actually "
             "received, which is why it works where a brightness slider fails.</p>"),
            ("A sheet photographed at an angle is a trapezoid",
             "<p>It is not a rotated rectangle, which is why no single rotation angle fixes "
             "it. On the photo this was built for, the slant of the text lines ran from "
             "0.00&deg; at the top of the page to 1.00&deg; at the bottom.</p>"
             "<p>So the tool measures two angles, one high on the page and one low, "
             "reconstructs the trapezoid they imply, and maps it back to a rectangle with a "
             "projective transform. It repeats until the residual falls under 0.15&deg;. "
             "Measured on that photo: 1.05&deg;, then 0.25&deg;, then 0.00&deg;. It never "
             "looks for the edge of the sheet, which is usually out of frame or sitting "
             "against a background brighter than the paper. All the geometry comes from the "
             "text.</p>"
             '<p class="caveat">Straightening crops to the block of text and takes the '
             "sheet's margins with it, so they get rebuilt afterwards at the proportions of "
             "an ordinary document. The browser works on the photo scaled to 2400 pixels "
             "wide, which is more than 300 dpi across A4; the command-line version keeps "
             "the full resolution.</p>"),
            ("The same cleanup from a terminal",
             cli_block(".venv/bin/python tools/clean_scan.py photo.jpg -o clean.pdf",
                       "<p>It reports the real resolution your photo gives on the page. "
                       "Under about 150 dpi the text stays soft. Cleaning takes the shadow "
                       "away, it cannot invent detail the camera never caught, so a closer "
                       "photo beats any amount of processing.</p>")),
        ],
    },

    "extract-signature": {
        "lead": "<p class=\"lead\">A form wants a handwritten signature, and you would rather "
                "not print it, sign it, photograph the whole page and upload a grey picture "
                "of A4. Sign a blank sheet instead, photograph that, and cut the signature "
                "out here. You get a PNG with a transparent background that sits on the real "
                "document, which stays sharp text.</p>",
        "body": DROP.format(aria="Choose a photo of your signature",
                            strong="Drop a photo of your signature here",
                            sub="or click to choose one. A scan already saved as a PDF works too.",
                            accept="image/*,application/pdf,.pdf", multiple="") + """
<div id="stage" class="stage" hidden>
  <canvas id="shot"></canvas>
  <div id="box" class="croparea"><span id="handle" class="handle"></span></div>
</div>
<p class="hint">Drag a box around the signature. Drag inside it to move it, or the corner
to resize.</p>
<div class="controls">
  <label class="slider">Anything lighter than this is paper
    <input type="range" id="light" min="150" max="245" step="1" value="205"></label>
  <label class="slider">Anything darker than this is solid ink
    <input type="range" id="dark" min="20" max="160" step="1" value="95"></label>
  <label><input type="checkbox" id="colour"> Keep the pen colour</label>
</div>
<p id="state" class="status" aria-live="polite"></p>
<div id="result" class="preview chequered"></div>
<a id="save" class="button" hidden>Save the PNG</a>
<p class="hint">The same crop on the command line:
<code id="fractions">--box 0.45,0.70,1.00,0.97</code></p>""",
        "sections": [
            ("Sign on a blank sheet",
             "<p>This is the one piece of advice that changes the result.</p>"
             "<p>Photograph a signature written on plain paper, rather than one already "
             "sitting on a form. On a form the printed signature rule runs straight through "
             "your handwriting, and separating the two is genuinely hard. Measured on a real "
             "photo: the rule was tilted just enough that its longest unbroken run inside any "
             "pixel row reached 15% of the width, while the signature's own strokes reached "
             "13%. The two populations overlap. No threshold takes the rule out without "
             "eating part of the signature.</p>"
             "<p>On a blank sheet there is nothing to separate.</p>"),
            ("The detail, if you want it: the edges are a ramp",
             "<p>The lighting gets corrected first, the same way "
             '<a href="../clean-scan/">the scan cleanup</a> does it. Then the alpha channel '
             "is built from how dark each pixel is. Light paper goes fully transparent, dark "
             "ink fully opaque, and everything between them lands partly transparent.</p>"
             "<p>That middle band is the whole point. A hard threshold gives you a signature "
             "with staircase edges that reads as pasted on the moment anyone looks at it.</p>"
             '<p class="caveat">The two sliders are the numbers to move if the result is '
             "wrong. Raise the paper threshold when the signature comes out faint. Lower it "
             "when grime from the background survives.</p>"),
            ("The same extraction from a terminal",
             cli_block(".venv/bin/python tools/extract_signature.py photo.jpg -o signature.png",
                       "<p><code>--preview grid.png</code> writes a copy with a labelled grid "
                       "so you can read the four numbers off it, which is the command line's "
                       "version of the box you drag above. <code>--blue</code> keeps the pen "
                       "colour.</p>")),
        ],
    },

    "photo-to-pdf": {
        "lead": "<p class=\"lead\">The portal only accepts PDF and you have three photos on "
                "your phone. Drop them below, in the order you want the pages. You get one "
                "A4 PDF, right way up, small enough to upload.</p>",
        "body": DROP.format(aria="Choose photos", strong="Drop your photos here",
                            sub="or click to choose them. One photo per page, in order.",
                            accept="image/*", multiple=" multiple") + """
<div id="listing" class="listing"></div>
<div class="controls">
  <label><input type="checkbox" id="flatten" checked> Flatten the paper to white</label>
  <label><input type="checkbox" id="colour"> Keep the colour</label>
  <label>Resolution
    <select id="dpi">
      <option value="150">150 dpi</option>
      <option value="200" selected>200 dpi</option>
      <option value="300">300 dpi</option>
    </select></label>
  <label>Size cap
    <select id="cap">
      <option value="1">1 MB</option>
      <option value="2" selected>2 MB</option>
      <option value="5">5 MB</option>
    </select></label>
  <button type="button" id="clear" class="link" hidden>Start again</button>
</div>
<p id="state" class="status" aria-live="polite"></p>
<a id="save" class="button" hidden>Save the PDF</a>
<div id="notes" class="notes"></div>""",
        "sections": [
            ("What it does to your photos",
             "<p>It rotates them properly first. Phone photos are almost always rotated in "
             "the metadata rather than in the pixels, which is why the same picture looks "
             "upright in your gallery and lies on its side once it reaches somebody else's "
             "screen.</p>"
             "<p>Then greyscale, which costs nothing on a document and cuts about two thirds "
             "of the weight, a flattened white background so the paper does not stay beige, "
             "and A4 layout with a margin. If the result comes out over your size cap it "
             "steps the resolution down and tries again, rather than handing you a file the "
             "upload form will reject.</p>"
             "<p>This is the straight conversion. For shadows and perspective use "
             '<a href="../clean-scan/">the scan cleanup</a> instead.</p>'),
            ("One thing not to do",
             "<p>Do not rename <code>photo.jpg</code> to <code>photo.pdf</code>. The name "
             "does not change the contents. It is still a JPEG, and the portal rejects it by "
             "reading the first few bytes, which say <code>JFIF</code> where they should say "
             "<code>%PDF</code>. Obvious written down. Extremely common in practice.</p>"),
            ("The same conversion from a terminal",
             cli_block(".venv/bin/python tools/photo_to_pdf.py photo.jpg -o document.pdf",
                       "<p>Pass several images to get several pages, in the order you list "
                       "them. <code>--max-mb 1.5</code> tightens the size cap.</p>")),
        ],
    },

    "sign-pdf": {
        "lead": "<p class=\"lead\">The document is finished. It just needs a place, a date "
                "and somewhere to sign, and you do not want to reopen the word processor and "
                "re-export the whole thing. Drop the PDF in, fill in two fields, save it back "
                "out. Everything above the block is untouched.</p>",
        "body": DROP.format(aria="Choose a PDF to sign", strong="Drop the PDF here",
                            sub="or click to choose one", accept="application/pdf,.pdf",
                            multiple="") + """
<p class="chosen" id="chosen"></p>
<div class="fields">
  <label>Place<input type="text" id="place" placeholder="Turin"></label>
  <label>Date<input type="date" id="date"></label>
  <label>Language of the date
    <select id="locale"><option value="en">English</option><option value="it">Italiano</option></select>
  </label>
  <label>Word above the rule<input type="text" id="label" value="Signature"></label>
  <label class="wide">A cut-out signature, if you have one
    <input type="file" id="signature" accept="image/png,image/jpeg"></label>
</div>
<p id="state" class="status" aria-live="polite"></p>
<a id="save" class="button" hidden>Save the signed PDF</a>
<div id="report"></div>""",
        "sections": [
            ("What it adds, and what it leaves alone",
             "<p>Place and date on the left, a label and a rule on the right, at the foot of "
             "the last page. Layout, fonts and pagination stay exactly as they were. The "
             "block lines up with the document's own margins, which are read out of the file "
             "rather than assumed, because a signature block a few millimetres off the text "
             "above it is one of the things that makes a document look tampered with.</p>"
             "<p>Afterwards the finished file gets opened again and two things are checked: "
             "that the date is readable by a parser, and that no line of the original went "
             "missing. Both are reported under the download button.</p>"
             '<p>A cut-out signature goes on the rule at the proportions of the image. '
             '<a href="../extract-signature/">The signature extractor</a> makes one from a '
             "photograph.</p>"),
            ("Two things that look reasonable and do not work",
             "<p><strong>Reusing the font already embedded in the PDF</strong>, so the "
             "addition blends in. Embedded fonts are subsets: they carry only the glyphs "
             "that document happened to need, with their own internal encoding. Re-inserting "
             "one gives you text that displays perfectly on screen and extracts as null "
             "bytes. The PDF looks right and a parser reads no date at all. Helvetica is used "
             "instead.</p>"
             "<p><strong>Replacing placeholders inside the PDF.</strong> Redaction deletes "
             "every piece of text whose box touches the chosen area, and those boxes are "
             "inflated by line spacing: removing a heading took the contact line below it as "
             "well, with no error and no warning. Placeholders belong in the source document. "
             "This tool only tells you they are still there.</p>"),
            ("The same block from a terminal",
             cli_block(".venv/bin/python tools/add_date_signature.py document.pdf --place Turin",
                       "<p><code>--signature signature.png</code> lays a real signature on the "
                       "rule. <code>--locale it --label Firma</code> switches the date and the "
                       "label to Italian.</p>")),
        ],
    },

    "make-cv": {
        "lead": "<p class=\"lead\">You are applying for a job in Italy, the portal wants a CV "
                "with a date on it and a signature at the bottom, and the template you "
                "downloaded fights you every time you add a line. Fill this in instead. You "
                "get a one-page PDF whose text an applicant tracking system can still "
                "read.</p>",
        "body": """<p class="hint">Nothing you type here is stored or sent. It lives in this
tab until you close it.</p>
<div class="fields">
  <label>First name<input type="text" id="first_name" placeholder="Giulia"></label>
  <label>Surname<input type="text" id="last_name" placeholder="Marchetti"></label>
  <label class="wide">One line under your name: the role you are applying for
    <input type="text" id="headline" placeholder="Junior systems administrator"></label>
  <label>Date of birth<input type="text" id="born_on" placeholder="14/03/1996"></label>
  <label>Place of birth<input type="text" id="born_in" placeholder="Novara"></label>
  <label class="wide">Address
    <input type="text" id="address" placeholder="Via delle Rose 12, 10125 Torino (TO)"></label>
  <label>Phone<input type="text" id="phone" placeholder="+39 011 555 0142"></label>
  <label>Email<input type="text" id="email" placeholder="giulia.marchetti@example.org"></label>
  <label>LinkedIn, if you use it<input type="text" id="linkedin" placeholder="linkedin.com/in/..."></label>
  <label>Driving licence<input type="text" id="licence" placeholder="Driving licence B"></label>
  <label>Citizenship<input type="text" id="citizenship" placeholder="Italian"></label>
</div>
<label class="block">Education
  <textarea id="education" rows="4" placeholder="Diploma in computer science | ITIS Avogadro - Torino | 2015
Final mark 92/100"></textarea></label>
<label class="block">Experience
  <textarea id="experience" rows="8" placeholder="Help desk operator | Nordcom SpA - Torino | 03/2021 - present
Handled about 40 tickets a week across Windows 10 and 11
Wrote the runbook the rest of the desk now follows

Shop assistant | Libreria Bodoni - Novara | 2018 - 2021
Ran the stock system and the weekly order"></textarea></label>
<label class="block">Skills
  <textarea id="skills" rows="4" placeholder="Operating systems: Windows 10/11, Debian, Ubuntu
Networking: TCP/IP, DNS, DHCP, VPN
Tools: PowerShell, Bash, Git"></textarea></label>
<label class="block">Languages
  <textarea id="languages" rows="3" placeholder="Italian: native
English: B2"></textarea></label>
<label class="block">Anything else, one line each
  <textarea id="other" rows="2" placeholder="Volunteer IT support at a local association"></textarea></label>
<div class="fields">
  <label>Language of the CV
    <select id="locale"><option value="en">English</option><option value="it">Italiano</option></select>
  </label>
  <label>Place next to the date<input type="text" id="place" placeholder="Torino"></label>
  <label>Date<input type="date" id="date"></label>
  <label class="wide">A cut-out signature, if you have one
    <input type="file" id="signature" accept="image/png,image/jpeg"></label>
</div>
<button type="button" id="build" class="button primary">Build the PDF</button>
<p id="state" class="status" aria-live="polite"></p>
<a id="save" class="button" hidden>Save the CV</a>
<div id="notes" class="notes"></div>""",
        "sections": [
            ("Writing the entries",
             "<p>One entry per block, with a blank line between blocks. The first line is the "
             "title, then the organisation, then the dates, separated by a vertical bar. "
             "Every line after that becomes a bullet.</p>"
             "<p>Put a verb at the front of each bullet. \"Responsible for\" says nothing. "
             "\"Handled 40 tickets a week\" says what you did, and a number is worth more "
             "than an adjective.</p>"),
            ("English or Italian",
             "<p>The switch changes the headings and spells the date out in the right "
             "language. The Italian version also carries the GDPR authorisation line, which "
             "Italian employers and public bodies expect to see on a CV.</p>"
             '<p class="caveat">One detail if you ever write that line yourself: do not cite '
             "<em>art. 13 del D.Lgs. 196/2003</em>. That article was repealed by D.Lgs. "
             "101/2018, which harmonised the Italian Code with the GDPR, and disclosure is "
             "now governed by articles 13 and 14 of the Regulation. Half the templates online "
             "still point at the repealed one.</p>"),
            ("About the signature",
             "<p>Institutional portals usually want a handwritten signature rather than a "
             "typed name. Sign a blank sheet, cut it out with "
             '<a href="../extract-signature/">the signature extractor</a>, and add the PNG '
             "here. It lands on the rule at the foot of the page.</p>"
             '<p class="caveat">The built-in PDF fonts cover Western European text and '
             "nothing else. If you type a character outside that range the page tells you "
             "which one it had to leave out rather than losing it in silence.</p>"),
            ("The same CV from a terminal",
             cli_block(".venv/bin/python tools/make_cv.py --locale en -o cv.pdf",
                       "<p>The script keeps your details in a dictionary at the top of the "
                       "file, which is the better shape when you are tailoring the same CV "
                       "to twenty applications.</p>")),
        ],
    },
}

if __name__ == "__main__":
    build()
