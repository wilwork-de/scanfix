/**
 * The browser tools that produce PDFs: sign-core.js, cv-core.js, pdfout.js.
 *
 * Every assertion here builds a real PDF with the vendored pdf-lib the site loads,
 * then reads it back with pdf.js. Producing bytes is easy and producing bytes a
 * reader can parse is not, so nothing is trusted until it has been opened again.
 *
 * The fixtures come from tests/make_fixtures.py and are invented — a delivery note
 * for nobody, a squiggle that is not anyone's signature.
 *
 *   node tests/test_pdf.mjs
 */

import { fileURLToPath } from "node:url";
import path from "node:path";
import fs from "node:fs";

import * as pdfjs from "pdfjs-dist/legacy/build/pdf.mjs";
import * as PDFLib from "../docs/vendor/pdf-lib.esm.min.js";

import { signPdf, spelledDate, blockPlacement, remainingPlaceholders } from "../docs/sign-core.js";
import { buildCv, parseEntries, parsePairs, parseLines, sanitise, LABELS } from "../docs/cv-core.js";
import { fitInside, pixelWidthForDpi, imagesToPdf, A4 } from "../docs/pdfout.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURES = path.join(HERE, "fixtures");

let passed = 0, failed = 0;
const ok = (what, detail = "") => { console.log(`  ok    ${what.padEnd(52)} ${detail}`); passed++; };
const bad = (what, detail = "") => { console.log(`  FAIL  ${what.padEnd(52)} ${detail}`); failed++; };
const is = (what, got, want) => {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  g === w ? ok(what, g) : bad(what, `got ${g}, expected ${w}`);
};
const has = (what, haystack, needle) =>
  haystack.includes(needle) ? ok(what, JSON.stringify(needle.slice(0, 40)))
                            : bad(what, `"${needle.slice(0, 60)}" is not in the extracted text`);

/**
 * Everything a reader can pull back out of the file. The copy matters: pdf.js
 * transfers the array to its worker and detaches the buffer, so a caller that hands
 * over its only copy cannot use those bytes again.
 */
async function readBack(bytes) {
  const pdf = await pdfjs.getDocument({ data: Uint8Array.from(bytes), isEvalSupported: false }).promise;
  let text = "";
  const sizes = [];
  for (let n = 1; n <= pdf.numPages; n++) {
    const page = await pdf.getPage(n);
    sizes.push(page.view.slice(2));
    const content = await page.getTextContent();
    text += content.items.map(i => i.str).join("") + "\n";
    page.cleanup();
  }
  const pages = pdf.numPages;
  await pdf.destroy();
  return { text, pages, sizes };
}

const file = name => new Uint8Array(fs.readFileSync(path.join(FIXTURES, name)));
for (const needed of ["clean.pdf", "signature.png", "page_photo.jpg"]) {
  if (!fs.existsSync(path.join(FIXTURES, needed))) {
    console.log(`  FAIL  fixture ${needed} missing: run tests/make_fixtures.py first`);
    process.exit(1);
  }
}

// --- placing the block ------------------------------------------------------

console.log("Date and signature block, against tools/add_date_signature.py:");
is("the date is spelled out without a leading zero",
   spelledDate(new Date(2026, 8, 8), "en"), "8 September 2026");
is("the Italian month name", spelledDate(new Date(2026, 8, 8), "it"), "8 settembre 2026");

// Text ending 300 points up the page: the block hangs 46 points under it and the
// rule sits 26 points under that, anchored to the document's own left margin.
const roomy = blockPlacement({ left: 60, right: 520, bottom: 300 }, { width: 595, height: 842 });
is("the block hangs under the last line of text",
   [roomy.y, roomy.ruleY, roomy.middle, roomy.spilled], [254, 228, 290, false]);

// Text running down to 100 points: the block would be crushed into the margin, so a
// fresh sheet is used instead and the caller is told.
const tight = blockPlacement({ left: 60, right: 520, bottom: 100 }, { width: 595, height: 842 });
is("a full page spills onto a new sheet", [tight.spilled, tight.y], [true, 772]);

is("an uncompiled template is reported",
   remainingPlaceholders(["Name", "write to firstname.lastname@example.com", "fine"]),
   ["the name at the top", "the email address"]);

// --- signing a real document ------------------------------------------------

const source = file("clean.pdf");
const original = await readBack(source);

const signed = await signPdf(source,
  { place: "Torino", label: "Firma", locale: "it", date: new Date(2026, 8, 8) },
  { PDFLib, pdfjs });
const signedBack = await readBack(signed.bytes);

is("signing reports no problem", signed.problems, []);
has("the date is extractable, not just visible", signedBack.text, "Torino, 8 settembre 2026");
has("the label is on the page", signedBack.text, "Firma");
is("the document keeps its page count", [original.pages, signedBack.pages], [1, 1]);
has("the original text survives untouched", signedBack.text, "Quarterly report");
is("the page keeps its size", signedBack.sizes[0], original.sizes[0]);

const withSignature = await signPdf(source,
  { place: "Turin", date: new Date(2026, 8, 8), signature: { bytes: file("signature.png"), type: "png" } },
  { PDFLib, pdfjs });
if (withSignature.bytes.length > signed.bytes.length) {
  ok("a signature image is embedded", `${withSignature.bytes.length - signed.bytes.length} bytes more`);
} else {
  bad("a signature image is embedded", "the file did not grow");
}
is("signing with an image still verifies", withSignature.problems, []);

// --- the CV -----------------------------------------------------------------

console.log("CV, against tools/make_cv.py:");
is("an entry parses into title, organisation, period and bullets",
   parseEntries("Help desk operator | Nordcom - Torino | 03/2021 - present\nHandled 40 tickets a week"),
   [{ title: "Help desk operator", org: "Nordcom - Torino", period: "03/2021 - present",
      notes: ["Handled 40 tickets a week"] }]);
is("a skills line parses into label and value",
   parsePairs("Networking: TCP/IP, DNS"), [["Networking", "TCP/IP, DNS"]]);

// The core PDF fonts are WinAnsi. A smart quote has an equivalent; a Devanagari
// character has none, and the CV must still build and say what it dropped.
const dropped = [];
is("typographic characters are folded into WinAnsi",
   sanitise("don’t — do", dropped), "don't - do");
sanitise("क", dropped);
is("anything unencodable is reported rather than silently lost", dropped, ["क"]);

// The GDPR clause is document content and it is quoted law: if the two copies ever
// diverge, one of them is wrong. This compares the JavaScript copy with the literal
// in the Python source.
const pythonSource = fs.readFileSync(path.join(HERE, "..", "tools", "make_cv.py"), "utf8");
const block = pythonSource.match(/"privacy":\s*\(([\s\S]*?)\),/);
const fromPython = [...block[1].matchAll(/"([^"]*)"/g)].map(m => m[1]).join("");
is("the GDPR clause matches tools/make_cv.py word for word",
   LABELS.it.privacy === fromPython, true);

const data = {
  first_name: "Giulia", last_name: "Marchetti",
  headline: "Junior systems administrator",
  born_on: "14/03/1996", born_in: "Novara",
  address: "Via delle Rose 12, 10125 Torino (TO)",
  phone: "+39 011 555 0142", email: "giulia.marchetti@example.org",
  licence: "Driving licence B", citizenship: "Italian",
  education: parseEntries("Diploma in computer science | ITIS Avogadro - Torino | 2015\nFinal mark 92/100"),
  experience: parseEntries("Help desk operator | Nordcom SpA - Torino | 03/2021 - present\n" +
                           "Handled about 40 tickets a week across Windows 10 and 11"),
  skills: parsePairs("Operating systems: Windows 10/11, Debian\nNetworking: TCP/IP, DNS, DHCP"),
  languages: parsePairs("Italian: native\nEnglish: B2"),
  other: parseLines("Volunteer IT support at a local association"),
};

const english = await buildCv(data, { locale: "en", place: "Turin", date: new Date(2026, 8, 8) }, PDFLib);
const englishBack = await readBack(english.bytes);
is("the English CV fits on one page", englishBack.pages, 1);
is("the sheet is A4", englishBack.sizes[0].map(v => Math.round(v)), [595, 842]);
has("the name is selectable text, not a picture", englishBack.text, "GIULIA MARCHETTI");
has("the date is at the foot", englishBack.text, "Turin, 8 September 2026");
has("English headings", englishBack.text, "EXPERIENCE");

const italian = await buildCv(
  { ...data, other: [] },
  { locale: "it", place: "Torino", date: new Date(2026, 8, 8),
    signature: { bytes: file("signature.png"), type: "png" } },
  PDFLib);
const italianBack = await readBack(italian.bytes);
is("the Italian CV fits on one page", italianBack.pages, 1);
has("Italian headings", italianBack.text, "ESPERIENZA PROFESSIONALE");
has("the GDPR clause is on the page", italianBack.text, "Regolamento UE 2016/679");
if (italian.bytes.length > english.bytes.length) ok("the signature image is embedded in the CV");
else bad("the signature image is embedded in the CV", "the file did not grow");

// --- photos to a PDF --------------------------------------------------------

console.log("Photos to A4, against tools/photo_to_pdf.py:");
const frame = { x: 18, y: 18, width: A4.width - 36, height: A4.height - 36 };
const placed = fitInside(1000, 500, frame);
is("an image is scaled to the frame without squashing",
   [Math.round(placed.width), Math.round(placed.height)], [559, 280]);
if (Math.abs((placed.x - frame.x) - (frame.x + frame.width - placed.x - placed.width)) < 0.01) {
  ok("and centred in it");
} else {
  bad("and centred in it", `x ${placed.x}`);
}
is("200 dpi across the usable width", pixelWidthForDpi(200), 1554);

const photo = file("page_photo.jpg");
const album = await imagesToPdf(
  [{ bytes: photo }, { bytes: photo }].map(p => ({ ...p, })), PDFLib);
const albumBack = await readBack(album);
is("one photo per page, on A4", [albumBack.pages, albumBack.sizes[0].map(v => Math.round(v))],
   [2, [595, 842]]);

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
