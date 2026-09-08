/**
 * The scan cleanup page: photograph in, PDF that looks scanned out.
 *
 * The maths is in ../imaging.js, ported from tools/clean_scan.py and checked against
 * it in tests/test_imaging.mjs. This file is the wiring: read the file, run the
 * stages with a word about each one on screen, hand back a PDF.
 */

import * as PDFLib from "../vendor/pdf-lib.esm.min.js";
import { toGrey, cleanScan, straightenPass, inkBox, a4Canvas } from "../imaging.js";
import { A4, MARGIN, pixelWidthForDpi, dpiOfWidth, fitInside } from "../pdfout.js";
import {
  $, dropZone, status, yieldToPaint, loadImage, pixelsOf, canvasOf,
  resizeCanvas, blobOf, bytesOf, offerDownload, humanSize, escapeHtml,
} from "./ui.js";

const state = $("state");
const preview = $("preview");
const notes = $("notes");
const save = $("save");
let busy = false;
let lastFile = null;

dropZone($("drop"), $("picker"), files => run(files[0]));
// Changing a setting re-runs on the photo already loaded, so the effect of the
// switch is visible without picking the file again.
for (const id of ["colour", "straighten", "fit", "strength", "dpi"]) {
  $(id).addEventListener("change", () => { if (lastFile) run(lastFile); });
}

async function run(file) {
  if (busy) return;
  busy = true;
  lastFile = file;
  save.hidden = true;
  notes.innerHTML = "";
  try {
    await process(file);
  } catch (err) {
    status(state, `Could not read that image: ${err && err.message || err}`, "bad");
  } finally {
    busy = false;
  }
}

async function process(file) {
  const dpi = Number($("dpi").value);
  status(state, `Reading ${file.name}…`);
  await yieldToPaint();

  const image = await loadImage(file);
  let px = pixelsOf(image, 2400);
  const sourceW = px.sourceWidth, sourceH = px.sourceHeight;
  const realDpi = dpiOfWidth(sourceW);
  const remarks = [];

  if ($("straighten").checked) {
    // Repeat until the fan-out is negligible. One pass leaves a residual, because
    // the angles were measured on an image that was still distorted; measuring again
    // on the corrected one brings it under a tenth of a degree. Below the threshold
    // it stops, since resampling again costs sharpness for a change nobody can see.
    for (let pass = 1; pass <= 3; pass++) {
      status(state, `Straightening, pass ${pass}…`);
      await yieldToPaint();
      const done = straightenPass(px.data, px.width, px.height);
      px = { data: done.rgba, width: done.width, height: done.height };
      remarks.push(`straighten, pass ${pass}: fan-out ${done.fan.toFixed(2)}°`);
      if (done.fan < 0.15) break;
    }
    // Straightening crops to the block of text and takes the sheet's margins with
    // it, so the document would come out with its lines against the edge. Give a
    // margin back, proportional to the width so it holds at any resolution.
    const border = Math.round(px.width * 0.06);
    px = pad(px, border, border, border, border);
    remarks.push(`margin restored: ${border} px per side`);
  }

  status(state, "Removing the shadow…");
  await yieldToPaint();
  const cleaned = cleanScan(px.data, px.width, px.height, {
    colour: $("colour").checked,
    strength: Number($("strength").value),
  });
  let out = { data: cleaned.rgba, width: cleaned.width, height: cleaned.height };

  let margin = MARGIN;
  if ($("fit").checked) {
    status(state, "Rebuilding the margins…");
    await yieldToPaint();
    const fitted = fitA4(out);
    if (fitted) {
      out = fitted.px;
      remarks.push(`fitted to A4: ${out.width}×${out.height} px ` +
                   `(ratio ${(out.width / out.height).toFixed(4)}), margins ` +
                   `${fitted.marginX} px at the sides, ${fitted.marginY} at the top`);
      // Once fitted, the paper and the page share a ratio, so it goes edge to edge:
      // the margins are inside the image already.
      margin = 0;
    }
  }

  status(state, "Building the PDF…");
  await yieldToPaint();
  let canvas = canvasOf(out.data, out.width, out.height);
  canvas = resizeCanvas(canvas, pixelWidthForDpi(dpi, margin));
  const jpeg = await blobOf(canvas, "image/jpeg", 0.85);

  const doc = await PDFLib.PDFDocument.create();
  doc.setProducer("scanfix");
  const page = doc.addPage([A4.width, A4.height]);
  const embedded = await doc.embedJpg(await bytesOf(jpeg));
  page.drawImage(embedded, fitInside(embedded.width, embedded.height, {
    x: margin, y: margin, width: A4.width - 2 * margin, height: A4.height - 2 * margin,
  }));
  const bytes = await doc.save();
  const blob = new Blob([bytes], { type: "application/pdf" });

  preview.innerHTML = "";
  preview.appendChild(resizeCanvas(canvas, Math.min(canvas.width, 520)));
  offerDownload(save, blob, file.name.replace(/\.[^.]+$/, "") + "_clean.pdf");
  save.textContent = `Save the PDF (${humanSize(blob.size)})`;
  status(state, "Done. Look at it before you send it.", "good");

  remarks.push(`source photo ${sourceW}×${sourceH} px, ` +
               `about ${Math.round(realDpi)} dpi on the page`);
  if (realDpi < 150) {
    remarks.push("Under 150 dpi the text stays soft. Cleaning takes the shadow away, " +
                 "it cannot invent detail the camera never caught: a closer photo beats " +
                 "any amount of processing.");
  }
  notes.innerHTML = "<ul>" + remarks.map(r => `<li>${escapeHtml(r)}</li>`).join("") + "</ul>";
}

/** Put white paper back around the image. */
function pad(px, left, top, right, bottom) {
  const w = px.width + left + right, h = px.height + top + bottom;
  const data = new Uint8ClampedArray(w * h * 4).fill(255);
  for (let y = 0; y < px.height; y++) {
    const from = y * px.width * 4;
    data.set(px.data.subarray(from, from + px.width * 4), ((y + top) * w + left) * 4);
  }
  return { data, width: w, height: h };
}

/** Rebuild an A4 sheet around the text, the way clean_scan.py's fit_to_a4 does. */
function fitA4(px) {
  const grey = toGrey(px.data, px.width, px.height);
  const box = inkBox(grey, px.width, px.height, 170, 2);
  if (!box || box.rows < 10 || box.cols < 10) return null;
  const textW = box.x1 - box.x0, textH = box.y1 - box.y0;
  const { canvasW, canvasH, marginX, marginY } = a4Canvas(textW, textH);

  const data = new Uint8ClampedArray(canvasW * canvasH * 4).fill(255);
  const dx = marginX - box.x0, dy = marginY - box.y0;
  for (let y = 0; y < px.height; y++) {
    const ty = y + dy;
    if (ty < 0 || ty >= canvasH) continue;
    for (let x = 0; x < px.width; x++) {
      const tx = x + dx;
      if (tx < 0 || tx >= canvasW) continue;
      const from = (y * px.width + x) * 4, to = (ty * canvasW + tx) * 4;
      data[to] = px.data[from];
      data[to + 1] = px.data[from + 1];
      data[to + 2] = px.data[from + 2];
      data[to + 3] = 255;
    }
  }
  return { px: { data, width: canvasW, height: canvasH }, marginX, marginY };
}
