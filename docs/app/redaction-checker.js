/**
 * The redaction checker page.
 *
 * The analysis itself is in ../redaction-check.js, which is also what Node runs in
 * tests/test_js.mjs against the same fixtures as the Python tool. This file only
 * moves bytes between the file picker and that module.
 */

import * as pdfjs from "../vendor/pdf.min.mjs";
import { analyseDocument } from "../redaction-check.js";
import { $, dropZone, escapeHtml } from "./ui.js";

pdfjs.GlobalWorkerOptions.workerSrc = "../vendor/pdf.worker.min.mjs";

const result = $("result");

dropZone($("drop"), $("picker"), files => check(files[0]));

async function check(file) {
  result.innerHTML = `<p class="status">Reading <b>${escapeHtml(file.name)}</b>…</p>`;
  try {
    const data = new Uint8Array(await file.arrayBuffer());
    const pdf = await pdfjs.getDocument({ data, isEvalSupported: false }).promise;
    render(file.name, await analyseDocument(pdf, pdfjs.OPS));
    await pdf.destroy();
  } catch (err) {
    result.innerHTML = `<div class="verdict suspect"><h3>Could not read it</h3>
      <p>${escapeHtml(String(err && err.message || err))}</p></div>`;
  }
}

function render(name, r) {
  if (r.verdict === "CLEAN") {
    result.innerHTML = `<div class="verdict clean"><h3>No suspicious covers</h3>
      <p>${escapeHtml(name)}, ${r.totalPages} pages. No opaque shape sits over
      still-extractable content. Read that narrowly: it means the document does not have
      <em>this</em> defect, not that it holds nothing confidential in plain sight.</p></div>`;
    return;
  }
  const count = r.pages.reduce((n, p) => n + p.findings.length, 0);
  let html = `<div class="verdict suspect"><h3>Redaction is not reliable</h3>
    <p>${escapeHtml(name)}: ${count} opaque shapes with something still readable under them.
    Here is what came back.</p></div>`;
  for (const p of r.pages) {
    for (const f of p.findings) {
      html += `<div class="finding"><div class="where">page ${p.page} · ${escapeHtml(f.source)}
        · box [${f.box.join(", ")}]</div>`;
      if (f.textUnderneath) html += `<div class="recovered">${escapeHtml(f.textUnderneath)}</div>`;
      if (f.overImage) {
        html += `<p class="image-note" style="margin:${f.textUnderneath ? "8px" : "0"} 0 0">
          Covers an image. The picture underneath extracts intact, because drawing over an
          embedded image does not modify it.</p>`;
      }
      html += `</div>`;
    }
  }
  result.innerHTML = html;
}
