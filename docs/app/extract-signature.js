/**
 * The signature extractor page.
 *
 * The command-line version takes the crop as four fractions you read off a grid
 * image. On a page you can just drag a box over the photograph, so that is what this
 * does; the numbers underneath are the same ones extract_signature.py takes.
 */

import { extractSignature } from "../imaging.js";
import {
  $, dropZone, status, yieldToPaint, loadImage, pixelsOf, pixelsFromPdf, isPdf,
  canvasOf, blobOf, offerDownload, humanSize,
} from "./ui.js";

const state = $("state");
const stage = $("stage");
const shot = $("shot");
const box = $("box");
const result = $("result");
const save = $("save");

// Where a signature sits on a signed document: right half, lower band. Same default
// as the CLI, expressed as fractions so it holds at any resolution.
let region = { x0: 0.45, y0: 0.70, x1: 1.00, y1: 0.97 };
let source = null;
let name = "signature";

dropZone($("drop"), $("picker"), files => open(files[0]));
for (const id of ["light", "dark", "colour"]) {
  $(id).addEventListener("input", () => { if (source) extract(); });
}

async function open(file) {
  try {
    status(state, "Reading the photograph…");
    await yieldToPaint();
    name = file.name.replace(/\.[^.]+$/, "");
    source = isPdf(file) ? await pixelsFromPdf(file, 2400)
                         : pixelsOf(await loadImage(file), 2400);
    const canvas = canvasOf(source.data, source.width, source.height);
    shot.width = source.width;
    shot.height = source.height;
    shot.getContext("2d").drawImage(canvas, 0, 0);
    stage.hidden = false;
    save.hidden = true;
    result.innerHTML = "";
    drawBox();
    // No extraction yet. The default box is a guess about where a signature usually
    // sits, and guessing wrong greets you with a red warning before you have done
    // anything. Ask for the box first.
    status(state, "Now drag a box around the signature.");
  } catch (err) {
    status(state, `Could not read that image: ${err && err.message || err}`, "bad");
  }
}

// --- the draggable box ------------------------------------------------------

function drawBox() {
  box.style.left = `${region.x0 * 100}%`;
  box.style.top = `${region.y0 * 100}%`;
  box.style.width = `${(region.x1 - region.x0) * 100}%`;
  box.style.height = `${(region.y1 - region.y0) * 100}%`;
  $("fractions").textContent =
    `--box ${region.x0.toFixed(2)},${region.y0.toFixed(2)},${region.x1.toFixed(2)},${region.y1.toFixed(2)}`;
}

const clamp = v => Math.min(1, Math.max(0, v));

function pointIn(event) {
  const r = stage.getBoundingClientRect();
  return { x: clamp((event.clientX - r.left) / r.width), y: clamp((event.clientY - r.top) / r.height) };
}

let drag = null;

stage.addEventListener("pointerdown", e => {
  if (!source) return;
  const p = pointIn(e);
  const onHandle = e.target === $("handle");
  const inside = !onHandle && e.target === box;
  drag = { mode: onHandle ? "resize" : inside ? "move" : "draw", from: p, start: { ...region } };
  if (drag.mode === "draw") region = { x0: p.x, y0: p.y, x1: p.x, y1: p.y };
  stage.setPointerCapture(e.pointerId);
  e.preventDefault();
});

stage.addEventListener("pointermove", e => {
  if (!drag) return;
  const p = pointIn(e);
  if (drag.mode === "draw") {
    region = { x0: Math.min(drag.from.x, p.x), y0: Math.min(drag.from.y, p.y),
               x1: Math.max(drag.from.x, p.x), y1: Math.max(drag.from.y, p.y) };
  } else if (drag.mode === "move") {
    const dx = p.x - drag.from.x, dy = p.y - drag.from.y;
    const w = drag.start.x1 - drag.start.x0, h = drag.start.y1 - drag.start.y0;
    const x0 = Math.min(Math.max(drag.start.x0 + dx, 0), 1 - w);
    const y0 = Math.min(Math.max(drag.start.y0 + dy, 0), 1 - h);
    region = { x0, y0, x1: x0 + w, y1: y0 + h };
  } else {
    region = { ...region, x1: Math.max(p.x, region.x0 + 0.02), y1: Math.max(p.y, region.y0 + 0.02) };
  }
  drawBox();
});

stage.addEventListener("pointerup", async () => {
  if (!drag) return;
  drag = null;
  if (region.x1 - region.x0 > 0.02 && region.y1 - region.y0 > 0.02) await extract();
});

// --- the extraction ---------------------------------------------------------

async function extract() {
  status(state, "Cutting it out…");
  await yieldToPaint();

  const x0 = Math.floor(region.x0 * source.width), y0 = Math.floor(region.y0 * source.height);
  const x1 = Math.max(x0 + 2, Math.floor(region.x1 * source.width));
  const y1 = Math.max(y0 + 2, Math.floor(region.y1 * source.height));
  const w = x1 - x0, h = y1 - y0;

  const crop = new Uint8ClampedArray(w * h * 4);
  for (let y = 0; y < h; y++) {
    const from = ((y0 + y) * source.width + x0) * 4;
    crop.set(source.data.subarray(from, from + w * 4), y * w * 4);
  }

  const cut = extractSignature(crop, w, h, {
    light: Number($("light").value),
    dark: Number($("dark").value),
    keepColour: $("colour").checked,
  });

  const full = canvasOf(cut.rgba, w, h);
  const b = cut.box || { x0: 0, y0: 0, x1: w, y1: h };
  const trimmed = document.createElement("canvas");
  trimmed.width = b.x1 - b.x0;
  trimmed.height = b.y1 - b.y0;
  trimmed.getContext("2d").drawImage(full, -b.x0, -b.y0);

  const blob = await blobOf(trimmed, "image/png");
  result.innerHTML = "";
  result.appendChild(trimmed);
  offerDownload(save, blob, `${name}_signature.png`);
  save.textContent = `Save the PNG (${humanSize(blob.size)})`;
  save.hidden = false;

  const coverage = cut.coverage;
  if (coverage < 0.4) {
    status(state, `Almost no ink in that box (${coverage.toFixed(1)}%). The signature is ` +
                  "somewhere else on the photo. Drag the box over it.", "bad");
  } else if (coverage > 25) {
    status(state, `That is a lot of ink (${coverage.toFixed(1)}%): you have caught body ` +
                  "text or the shadow of the sheet. Tighten the box, or lower the paper " +
                  "threshold.", "bad");
  } else {
    status(state, `Ink in the box: ${coverage.toFixed(1)}%. Check the preview against the ` +
                  "chequerboard: only the signature should be showing.", "good");
  }
  drawBox();
}
