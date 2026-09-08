/**
 * Drive the real pages in a real browser, with the real Content-Security-Policy.
 *
 * The CSP is the part of this site that can break silently: a page whose policy
 * forbids a connection still renders perfectly, right up to the moment a tool needs
 * the thing it blocked. So this suite loads each page in headless Chrome, records
 * every console error and every securitypolicyviolation event, feeds each tool a
 * generated fixture, clicks the download link and checks the file that lands on disk.
 *
 * Puppeteer is deliberately not a dependency in package.json: it drags a whole
 * browser down with it, and nobody cloning this to read six Python scripts should pay
 * for that. Install it when you want to run this.
 *
 *   npm install --no-save puppeteer
 *   node tests/test_browser.mjs
 */

import { fileURLToPath } from "node:url";
import path from "node:path";
import fs from "node:fs";
import http from "node:http";
import * as pdfjs from "pdfjs-dist/legacy/build/pdf.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(HERE, "..");
const DOCS = path.join(ROOT, "docs");
const FIXTURES = path.join(HERE, "fixtures");
const DOWNLOADS = path.join(HERE, "downloads");

let puppeteer;
try {
  puppeteer = (await import("puppeteer")).default;
} catch {
  console.log("  skip  puppeteer is not installed.");
  console.log("        npm install --no-save puppeteer   then run this again.");
  process.exit(0);
}

let passed = 0, failed = 0;
const ok = (what, detail = "") => { console.log(`  ok    ${what.padEnd(52)} ${detail}`); passed++; };
const bad = (what, detail = "") => { console.log(`  FAIL  ${what.padEnd(52)} ${detail}`); failed++; };

// --- a local server, because file:// has no origin and no module loading ----

const TYPES = {
  ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript",
  ".css": "text/css", ".xml": "application/xml", ".txt": "text/plain",
  ".svg": "image/svg+xml",
};
const server = http.createServer((req, res) => {
  let file = path.join(DOCS, decodeURIComponent(req.url.split("?")[0]));
  if (file.endsWith("/")) file = path.join(file, "index.html");
  if (!file.startsWith(DOCS) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
    res.writeHead(404).end("not found");
    return;
  }
  res.writeHead(200, { "content-type": TYPES[path.extname(file)] || "application/octet-stream" });
  res.end(fs.readFileSync(file));
});
await new Promise(r => server.listen(0, "127.0.0.1", r));
const base = `http://127.0.0.1:${server.address().port}`;

fs.rmSync(DOWNLOADS, { recursive: true, force: true });
fs.mkdirSync(DOWNLOADS, { recursive: true });

const browser = await puppeteer.launch({
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
  // Tall enough that the crop box on the signature page is inside the viewport.
  // Puppeteer's mouse works in viewport coordinates while boundingBox() reports page
  // coordinates, so an element below the fold gets clicked at the wrong place.
  defaultViewport: { width: 1100, height: 1500 },
});

/** Open a page, watching for anything the policy refuses or the code throws. */
async function visit(slug) {
  const page = await browser.newPage();
  const errors = [], violations = [];
  page.on("console", m => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", e => errors.push(String(e.message || e)));
  await page.evaluateOnNewDocument(() => {
    window.__violations = [];
    document.addEventListener("securitypolicyviolation",
      e => window.__violations.push(`${e.violatedDirective} blocked ${e.blockedURI}`));
  });
  const client = await page.createCDPSession();
  await client.send("Page.setDownloadBehavior", { behavior: "allow", downloadPath: DOWNLOADS });
  await page.goto(`${base}/${slug}`, { waitUntil: "networkidle0" });
  page.__errors = errors;
  page.__violations = violations;
  return page;
}

async function finish(page, name) {
  const violations = await page.evaluate(() => window.__violations || []);
  if (!violations.length) ok(`${name}: no CSP violation`);
  else bad(`${name}: no CSP violation`, violations.join("; "));
  const errors = page.__errors.filter(e => !/favicon/i.test(e));
  if (!errors.length) ok(`${name}: no console error`);
  else bad(`${name}: no console error`, errors.slice(0, 2).join(" | "));
  await page.close();
}

/** Click the download link and wait for the file Chrome writes. */
async function download(page, selector, timeout = 25000) {
  const before = new Set(fs.readdirSync(DOWNLOADS));
  await page.click(selector);
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const now = fs.readdirSync(DOWNLOADS)
      .filter(f => !before.has(f) && !f.endsWith(".crdownload"));
    if (now.length) {
      await new Promise(r => setTimeout(r, 200));
      return path.join(DOWNLOADS, now[0]);
    }
    await new Promise(r => setTimeout(r, 150));
  }
  throw new Error("nothing was downloaded");
}

async function readPdf(file) {
  const data = new Uint8Array(fs.readFileSync(file));
  const pdf = await pdfjs.getDocument({ data, isEvalSupported: false }).promise;
  let text = "";
  const sizes = [];
  for (let n = 1; n <= pdf.numPages; n++) {
    const p = await pdf.getPage(n);
    sizes.push(p.view.slice(2).map(v => Math.round(v)));
    text += (await p.getTextContent()).items.map(i => i.str).join("") + "\n";
    p.cleanup();
  }
  const pages = pdf.numPages;
  await pdf.destroy();
  return { pages, text, sizes };
}

const fixture = name => path.join(FIXTURES, name);

// --- the hub ----------------------------------------------------------------

{
  const page = await visit("");
  const cards = await page.$$eval(".card", n => n.length);
  cards === 6 ? ok("hub: six tools listed") : bad("hub: six tools listed", String(cards));
  await finish(page, "hub");
}

// --- redaction checker ------------------------------------------------------

{
  const page = await visit("redaction-checker/");
  const input = await page.$("#picker");
  await input.uploadFile(fixture("fake_redaction.pdf"));
  await page.waitForSelector(".verdict", { timeout: 20000 });
  const text = await page.$eval("#result", n => n.textContent);
  text.includes("not reliable")
    ? ok("redaction checker: calls the fake redaction out")
    : bad("redaction checker: calls the fake redaction out", text.slice(0, 80));
  text.includes("Mario Rossi")
    ? ok("redaction checker: reads the name back in the browser")
    : bad("redaction checker: reads the name back in the browser");
  await finish(page, "redaction checker");
}

// --- clean scan -------------------------------------------------------------

{
  const page = await visit("clean-scan/");
  await (await page.$("#picker")).uploadFile(fixture("page_photo.jpg"));
  await page.waitForFunction(() => !document.getElementById("save").hidden, { timeout: 60000 });
  const file = await download(page, "#save");
  const pdf = await readPdf(file);
  pdf.pages === 1 && pdf.sizes[0][0] === 595
    ? ok("clean scan: downloads a one-page A4 PDF", `${fs.statSync(file).size} bytes`)
    : bad("clean scan: downloads a one-page A4 PDF", JSON.stringify(pdf.sizes));
  const notes = await page.$eval("#notes", n => n.textContent);
  /fan-out/.test(notes)
    ? ok("clean scan: reports what the straightening did")
    : bad("clean scan: reports what the straightening did", notes.slice(0, 80));
  await finish(page, "clean scan");
}

// --- signature extractor ----------------------------------------------------

{
  const page = await visit("extract-signature/");
  await (await page.$("#picker")).uploadFile(fixture("page_photo.jpg"));
  await page.waitForSelector("#stage:not([hidden])", { timeout: 20000 });

  // Drag a box over most of the sheet, the way a visitor would.
  await page.$eval("#stage", n => n.scrollIntoView({ block: "center" }));
  const stage = await (await page.$("#stage")).boundingBox();
  await page.mouse.move(stage.x + stage.width * 0.08, stage.y + stage.height * 0.12);
  await page.mouse.down();
  await page.mouse.move(stage.x + stage.width * 0.9, stage.y + stage.height * 0.8, { steps: 8 });
  await page.mouse.up();
  await page.waitForFunction(() => !document.getElementById("save").hidden, { timeout: 30000 });

  const fractions = await page.$eval("#fractions", n => n.textContent);
  /^--box 0\.0[5-9]/.test(fractions)
    ? ok("signature extractor: the dragged box sets the crop", fractions)
    : bad("signature extractor: the dragged box sets the crop", fractions);

  const file = await download(page, "#save");
  const bytes = fs.readFileSync(file);
  const isPng = bytes.slice(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]));
  // Byte 25 of the IHDR chunk is the colour type; 6 is truecolour with alpha.
  isPng && bytes[25] === 6
    ? ok("signature extractor: downloads a PNG with an alpha channel", `${bytes.length} bytes`)
    : bad("signature extractor: downloads a PNG with an alpha channel",
          `png=${isPng} colourType=${bytes[25]}`);
  await finish(page, "signature extractor");
}

// --- photo to PDF -----------------------------------------------------------

{
  const page = await visit("photo-to-pdf/");
  await (await page.$("#picker")).uploadFile(fixture("page_photo.jpg"), fixture("page_photo.jpg"));
  await page.waitForFunction(() => !document.getElementById("save").hidden, { timeout: 40000 });
  const file = await download(page, "#save");
  const pdf = await readPdf(file);
  pdf.pages === 2 && pdf.sizes[0][0] === 595 && pdf.sizes[0][1] === 842
    ? ok("photo to PDF: two photos become two A4 pages", `${fs.statSync(file).size} bytes`)
    : bad("photo to PDF: two photos become two A4 pages", JSON.stringify(pdf));
  await finish(page, "photo to PDF");
}

// --- date and signature -----------------------------------------------------

{
  const page = await visit("sign-pdf/");
  await page.$eval("#place", n => { n.value = "Torino"; });
  await page.$eval("#date", n => { n.value = "2026-09-08"; });
  await page.select("#locale", "it");
  await (await page.$("#picker")).uploadFile(fixture("clean.pdf"));
  await page.waitForFunction(() => !document.getElementById("save").hidden, { timeout: 30000 });
  const file = await download(page, "#save");
  const pdf = await readPdf(file);
  pdf.text.includes("Torino, 8 settembre 2026")
    ? ok("date and signature: the date is extractable from the download")
    : bad("date and signature: the date is extractable from the download", pdf.text.slice(0, 90));
  pdf.text.includes("Quarterly report") && pdf.pages === 1
    ? ok("date and signature: the original survives, still one page")
    : bad("date and signature: the original survives, still one page", String(pdf.pages));
  await finish(page, "date and signature");
}

// --- CV ---------------------------------------------------------------------

{
  const page = await visit("make-cv/");
  await page.evaluate(() => {
    const set = (id, v) => { document.getElementById(id).value = v; };
    set("first_name", "Giulia");
    set("last_name", "Marchetti");
    set("headline", "Junior systems administrator");
    set("born_in", "Novara");
    set("email", "giulia.marchetti@example.org");
    set("experience", "Help desk operator | Nordcom SpA - Torino | 03/2021 - present\n" +
                      "Handled about 40 tickets a week across Windows 10 and 11");
    set("skills", "Networking: TCP/IP, DNS, DHCP");
    set("place", "Torino");
    set("date", "2026-09-08");
    document.getElementById("locale").value = "it";
  });
  await page.click("#build");
  await page.waitForFunction(() => !document.getElementById("save").hidden, { timeout: 30000 });
  const file = await download(page, "#save");
  const pdf = await readPdf(file);
  pdf.pages === 1 && pdf.text.includes("GIULIA MARCHETTI")
    ? ok("CV: one page with the name as selectable text")
    : bad("CV: one page with the name as selectable text", pdf.text.slice(0, 90));
  pdf.text.includes("Regolamento UE 2016/679")
    ? ok("CV: the Italian version carries the GDPR clause")
    : bad("CV: the Italian version carries the GDPR clause");
  await finish(page, "CV");
}

await browser.close();
server.close();
fs.rmSync(DOWNLOADS, { recursive: true, force: true });

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
