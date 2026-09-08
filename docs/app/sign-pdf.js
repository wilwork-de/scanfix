/**
 * The date-and-signature page.
 *
 * The work is in ../sign-core.js, which tests/test_pdf.mjs runs under Node against a
 * generated fixture: it opens the result again and checks the date is extractable and
 * that nothing was lost. This file collects the fields and shows what came back.
 */

import * as PDFLib from "../vendor/pdf-lib.esm.min.js";
import * as pdfjs from "../vendor/pdf.min.mjs";
import { signPdf, parseDate } from "../sign-core.js";
import {
  $, dropZone, status, yieldToPaint, bytesOf, offerDownload,
  humanSize, isoToday, escapeHtml,
} from "./ui.js";

pdfjs.GlobalWorkerOptions.workerSrc = "../vendor/pdf.worker.min.mjs";

const state = $("state");
const report = $("report");
const save = $("save");
let document_ = null;
let signature = null;

$("date").value = isoToday();

dropZone($("drop"), $("picker"), files => {
  document_ = files[0];
  $("chosen").textContent = document_.name;
  run();
});
$("signature").addEventListener("change", e => {
  signature = e.target.files[0] || null;
  run();
});
$("locale").addEventListener("change", () => {
  // The label follows the language unless it has been edited by hand.
  const label = $("label");
  if (label.value === "Signature" || label.value === "Firma") {
    label.value = $("locale").value === "it" ? "Firma" : "Signature";
  }
  run();
});
for (const id of ["place", "date", "label"]) $(id).addEventListener("change", run);

async function run() {
  if (!document_) return;
  save.hidden = true;
  report.innerHTML = "";
  try {
    status(state, "Reading the document…");
    await yieldToPaint();

    const options = {
      place: $("place").value.trim().replace(/,\s*$/, ""),
      date: parseDate($("date").value || isoToday()),
      locale: $("locale").value,
      label: $("label").value.trim() || "Signature",
      signature: null,
    };
    if (signature) {
      options.signature = {
        bytes: await bytesOf(signature),
        type: /\.png$/i.test(signature.name) || signature.type === "image/png" ? "png" : "jpg",
      };
    }

    const result = await signPdf(await bytesOf(document_), options, { PDFLib, pdfjs });
    const blob = new Blob([result.bytes], { type: "application/pdf" });
    offerDownload(save, blob, document_.name.replace(/\.pdf$/i, "") + "_signed.pdf");
    save.textContent = `Save the signed PDF (${humanSize(blob.size)})`;

    const lines = [];
    if (result.problems.length) {
      lines.push(...result.problems.map(p => `<li class="bad">${escapeHtml(p)}</li>`));
    } else {
      lines.push(`<li class="good">The date reads back out of the finished file as ` +
                 `<code>${escapeHtml(result.date)}</code>, and every line of the original ` +
                 `is still there.</li>`);
    }
    if (result.spilled) {
      lines.push(`<li>The last page was full, so the block went onto a new sheet: ` +
                 `${result.pagesBefore} pages became ${result.pagesAfter}. To keep it to ` +
                 `${result.pagesBefore}, shorten the document or reduce its bottom margin.</li>`);
    }
    if (result.alreadySigned) {
      lines.push(`<li>That document already carried a signature label. If you are running ` +
                 `this on its own output you will get two blocks.</li>`);
    }
    if (result.placeholders.length) {
      lines.push(`<li>Still to fill in, in the source file (.docx / .odt) and then ` +
                 `re-export: ${escapeHtml(result.placeholders.join(", "))}.</li>`);
    }
    if (!signature) {
      lines.push(`<li>The rule is empty: print it and sign by hand, or drop a cut-out ` +
                 `signature in above. <a href="../extract-signature/">The signature ` +
                 `extractor</a> makes one from a photograph.</li>`);
    }
    report.innerHTML = `<ul class="report">${lines.join("")}</ul>`;
    status(state, result.problems.length ? "Done, with something to check." : "Done.",
           result.problems.length ? "bad" : "good");
  } catch (err) {
    status(state, `Could not sign that file: ${err && err.message || err}`, "bad");
  }
}
