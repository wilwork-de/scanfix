/**
 * The photo-to-PDF page: one photo per A4 page, under a size cap.
 *
 * Straight conversion, in the order tools/photo_to_pdf.py does it: EXIF rotation,
 * greyscale, flatten the paper, resample for the chosen resolution, lay out on A4,
 * and step the resolution down if the file overshoots the cap.
 */

import * as PDFLib from "../vendor/pdf-lib.esm.min.js";
import { toGrey, autocontrastLut } from "../imaging.js";
import { imagesToPdf, pixelWidthForDpi } from "../pdfout.js";
import {
  $, dropZone, status, yieldToPaint, loadImage, pixelsOf, canvasOf,
  resizeCanvas, blobOf, bytesOf, offerDownload, humanSize, escapeHtml,
} from "./ui.js";

const state = $("state");
const listing = $("listing");
const save = $("save");
const notes = $("notes");
let files = [];

dropZone($("drop"), $("picker"), added => {
  files = files.concat(added);
  showList();
  build();
});
for (const id of ["colour", "flatten", "dpi", "cap"]) {
  $(id).addEventListener("change", () => { if (files.length) build(); });
}
$("clear").addEventListener("click", () => {
  files = [];
  showList();
  save.hidden = true;
  notes.innerHTML = "";
  status(state, "");
});

function showList() {
  listing.innerHTML = files.length
    ? "<ol>" + files.map(f => `<li>${escapeHtml(f.name)}</li>`).join("") + "</ol>"
    : "";
  $("clear").hidden = !files.length;
}

/** One image, ready to go on a page: rotated, greyed, flattened, resampled. */
async function prepare(file, dpi) {
  const image = await loadImage(file);
  const px = pixelsOf(image, 4000);
  let canvas;

  if ($("colour").checked) {
    canvas = canvasOf(px.data, px.width, px.height);
  } else {
    const grey = toGrey(px.data, px.width, px.height);
    // Autocontrast with the tails clipped takes the paper to white and the ink to
    // black, which is what a scanner app does. The low cutoff is deliberate: clipping
    // harder eats thin pencil strokes and faint signatures.
    const lut = $("flatten").checked ? autocontrastLut(grey, 1, 6) : null;
    const rgba = new Uint8ClampedArray(px.width * px.height * 4);
    for (let i = 0, p = 0; i < grey.length; i++, p += 4) {
      const v = lut ? lut[Math.round(grey[i])] : grey[i];
      rgba[p] = rgba[p + 1] = rgba[p + 2] = v;
      rgba[p + 3] = 255;
    }
    canvas = canvasOf(rgba, px.width, px.height);
  }

  canvas = resizeCanvas(canvas, pixelWidthForDpi(dpi));
  return bytesOf(await blobOf(canvas, "image/jpeg", 0.82));
}

async function build() {
  save.hidden = true;
  const cap = Number($("cap").value);
  let dpi = Number($("dpi").value);
  const remarks = [];

  try {
    let blob;
    // Overshooting the cap means retrying lower, not handing over a file the upload
    // form will reject. 120 dpi is the floor: below it printed text breaks up.
    for (;;) {
      status(state, `Converting ${files.length} image${files.length > 1 ? "s" : ""} at ${dpi} dpi…`);
      await yieldToPaint();
      const pages = [];
      for (const file of files) pages.push({ bytes: await prepare(file, dpi) });
      blob = new Blob([await imagesToPdf(pages, PDFLib)], { type: "application/pdf" });
      if (blob.size / 1048576 <= cap || dpi <= 120) break;
      remarks.push(`${humanSize(blob.size)} was over the cap, retried lower`);
      dpi = Math.max(120, Math.round(dpi * 0.8));
    }

    offerDownload(save, blob, "document.pdf");
    save.textContent = `Save the PDF (${humanSize(blob.size)})`;
    const mb = blob.size / 1048576;
    if (mb > cap) {
      status(state, `${humanSize(blob.size)}, still over your ${cap} MB cap even at 120 dpi. ` +
                    "Retake the photo closer, with the sheet filling the frame.", "bad");
    } else {
      status(state, `${files.length} page${files.length > 1 ? "s" : ""}, ${humanSize(blob.size)}, ` +
                    `${dpi} dpi. Check at full screen that the signature is legible before ` +
                    "you upload it.", "good");
    }
    notes.innerHTML = remarks.length
      ? "<ul>" + remarks.map(r => `<li>${escapeHtml(r)}</li>`).join("") + "</ul>" : "";
  } catch (err) {
    status(state, `Could not convert that: ${err && err.message || err}`, "bad");
  }
}
