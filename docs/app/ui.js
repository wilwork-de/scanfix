/**
 * The small amount of browser plumbing every tool page needs: pick a file, get its
 * pixels, hand back a result the visitor can save.
 *
 * Kept apart from the algorithms on purpose. docs/imaging.js, docs/sign-core.js and
 * docs/cv-core.js touch no DOM and are tested under Node; this file is the part that
 * only makes sense inside a browser.
 */

export const $ = (id) => document.getElementById(id);

export function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/** Give the browser a moment to repaint before a slow step blocks the thread. */
export const yieldToPaint = () => new Promise(r => setTimeout(r, 16));

export function status(node, message, kind = "") {
  node.className = kind ? `status ${kind}` : "status";
  node.textContent = message;
}

/**
 * A drop zone that also works by clicking, by keyboard, and with several files.
 * `onFiles` gets an array, so a page that wants one file just takes the first.
 */
export function dropZone(zone, input, onFiles) {
  zone.addEventListener("click", () => input.click());
  zone.addEventListener("keydown", e => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); }
  });
  input.addEventListener("change", e => {
    if (e.target.files.length) onFiles([...e.target.files]);
  });
  for (const t of ["dragenter", "dragover"]) {
    zone.addEventListener(t, e => { e.preventDefault(); zone.classList.add("over"); });
  }
  for (const t of ["dragleave", "drop"]) {
    zone.addEventListener(t, e => { e.preventDefault(); zone.classList.remove("over"); });
  }
  zone.addEventListener("drop", e => {
    const files = [...(e.dataTransfer.files || [])];
    if (files.length) onFiles(files);
  });
}

/**
 * Decode an image with its EXIF rotation applied.
 *
 * Phone photos are almost always rotated in the metadata rather than in the pixels,
 * which is why the same picture arrives upright in one viewer and on its side in
 * another. createImageBitmap can be told to honour it; where that option is missing,
 * an <img> element does it anyway, because browsers have defaulted to
 * image-orientation: from-image for years.
 */
export async function loadImage(file) {
  try {
    return await createImageBitmap(file, { imageOrientation: "from-image" });
  } catch {
    const url = URL.createObjectURL(file);
    try {
      const img = new Image();
      img.src = url;
      await img.decode();
      return img;
    } finally {
      URL.revokeObjectURL(url);
    }
  }
}

/** Pixels from a decoded image, capped so a 48-megapixel photo does not stall. */
export function pixelsOf(image, maxWidth = 2400) {
  const sw = image.width || image.naturalWidth;
  const sh = image.height || image.naturalHeight;
  const scale = Math.min(1, maxWidth / sw);
  const w = Math.max(1, Math.round(sw * scale));
  const h = Math.max(1, Math.round(sh * scale));
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(image, 0, 0, w, h);
  return { data: ctx.getImageData(0, 0, w, h).data, width: w, height: h, sourceWidth: sw, sourceHeight: sh };
}

export function canvasOf(rgba, w, h) {
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  canvas.getContext("2d").putImageData(new ImageData(new Uint8ClampedArray(rgba), w, h), 0, 0);
  return canvas;
}

/** Scale a canvas to a target width, in one step. */
export function resizeCanvas(canvas, width) {
  if (canvas.width <= width) return canvas;
  const out = document.createElement("canvas");
  out.width = width;
  out.height = Math.round(canvas.height * width / canvas.width);
  const ctx = out.getContext("2d");
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(canvas, 0, 0, out.width, out.height);
  return out;
}

export function blobOf(canvas, type = "image/jpeg", quality = 0.85) {
  return new Promise(resolve => canvas.toBlob(resolve, type, quality));
}

export async function bytesOf(blobOrFile) {
  return new Uint8Array(await blobOrFile.arrayBuffer());
}

/**
 * Offer a result as a download.
 *
 * A blob URL is a pointer into this tab's own memory. Nothing is uploaded to produce
 * it and nothing is fetched to save it, which is why the page can promise no network
 * traffic and have the browser hold it to that: the Content-Security-Policy on every
 * page here sets connect-src to 'none', so a fetch would be refused even if some
 * future edit tried one.
 */
export function offerDownload(anchor, blob, filename) {
  if (anchor.dataset.url) URL.revokeObjectURL(anchor.dataset.url);
  const url = URL.createObjectURL(blob);
  anchor.dataset.url = url;
  anchor.href = url;
  anchor.download = filename;
  anchor.hidden = false;
  return url;
}

export function humanSize(bytes) {
  return bytes < 1024 * 1024
    ? `${Math.round(bytes / 1024)} KB`
    : `${(bytes / 1048576).toFixed(2)} MB`;
}

/** yyyy-mm-dd for a date input, in the visitor's own timezone. */
export function isoToday() {
  const d = new Date();
  const pad = n => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
