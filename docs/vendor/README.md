# Vendored libraries

These are unmodified copies of two third-party libraries, downloaded from cdnjs and
committed so the pages load them from this origin. Nothing here is patched: the point
of vendoring is that you can check these bytes against the ones cdnjs serves.

That is what makes the privacy claim enforceable. With every script coming from this
origin, the pages can be served with `default-src 'self'` and `connect-src 'none'`, and
the browser then refuses to let them open a network connection at all. Loading pdf.js
from a CDN would mean the CDN sees who is reading a document and when, even though the
document itself never left the tab.

| File | Library | Version | Licence |
|---|---|---|---|
| `pdf.min.mjs`, `pdf.worker.min.mjs` | [pdf.js](https://mozilla.github.io/pdf.js/) | 4.10.38 | Apache-2.0 |
| `pdf-lib.esm.min.js` | [pdf-lib](https://pdf-lib.js.org/) | 1.17.1 | MIT |

pdf.js reads PDFs (the redaction check, and the text geometry the signature block is
anchored to). pdf-lib writes them.

## How they got here

```bash
curl -O https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.min.mjs
curl -O https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.worker.min.mjs
curl -O https://cdnjs.cloudflare.com/ajax/libs/pdf-lib/1.17.1/pdf-lib.esm.min.js
sha256sum *.mjs *.js > checksums.txt
```

`checksums.txt` sits next to this file. Run `sha256sum -c checksums.txt` in this
directory, or re-download from the URLs above and compare, before you trust these
bytes.

## One known cosmetic wart

`pdf-lib.esm.min.js` ends with a `sourceMappingURL` comment pointing at a `.map` file
that is not vendored. With developer tools open the browser asks this origin for that
map and gets a 404. The file is left byte for byte as cdnjs serves it, because a
checksum you can verify is worth more than a tidy console.
