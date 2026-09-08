/**
 * Test suite for the JavaScript checker — the same file the site runs.
 *
 * The point is not just "the JS works": it is that the JS returns the SAME verdicts
 * as the Python version on the same fixtures. Two implementations that drift apart
 * silently are worse than one, because the site would say one thing and the script
 * another about the same document.
 *
 *   node tests/test_js.mjs
 */

import { fileURLToPath } from "node:url";
import path from "node:path";
import fs from "node:fs";

import * as pdfjs from "pdfjs-dist/legacy/build/pdf.mjs";
import { analyseDocument } from "../docs/redaction-check.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURES = path.join(HERE, "fixtures");

const EXPECTED = [
  ["fake_redaction.pdf", "SUSPECT", ["Mario Ross", "RSSMRA80A01H50", "IT60X05428111"]],
  ["real_redaction.pdf", "CLEAN", []],
  ["photo_with_boxes.pdf", "SUSPECT", []],
  ["clean.pdf", "CLEAN", []],
  ["graphic_band.pdf", "SUSPECT", ["ANNUAL REPORT"]],
];

let passed = 0, failed = 0;

const ok = (what, detail = "") => { console.log(`  ok    ${what.padEnd(52)} ${detail}`); passed++; };
const fail = (what, detail = "") => { console.log(`  FAIL  ${what.padEnd(52)} ${detail}`); failed++; };

for (const [name, expected, fragments] of EXPECTED) {
  const file = path.join(FIXTURES, name);
  if (!fs.existsSync(file)) {
    fail(name, "fixture missing: run tests/make_fixtures.py first");
    continue;
  }
  const data = new Uint8Array(fs.readFileSync(file));
  const pdf = await pdfjs.getDocument({ data, isEvalSupported: false }).promise;
  const result = await analyseDocument(pdf, pdfjs.OPS);

  if (result.verdict === expected) ok(name, result.verdict);
  else fail(name, `expected ${expected}, got ${result.verdict}`);

  const allText = result.pages.flatMap(p => p.findings.map(f => f.textUnderneath)).join(" | ");
  for (const f of fragments) {
    if (allText.includes(f)) ok(`  reads back "${f}"`);
    else fail(`  reads back "${f}"`, `not in ${JSON.stringify(allText).slice(0, 90)}`);
  }

  if (name === "photo_with_boxes.pdf") {
    const overImage = result.pages.flatMap(p => p.findings).filter(f => f.overImage);
    if (overImage.length >= 3) ok("  recognises the covers over the image", `${overImage.length}`);
    else fail("  recognises the covers over the image", `found ${overImage.length}, expected >= 3`);
  }

  await pdf.destroy();
}

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
