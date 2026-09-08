/**
 * Putting images on A4 pages, and the arithmetic around it.
 *
 * pdf-lib is passed in rather than imported, for the same reason redaction-check.js
 * takes pdf.js as an argument: the tests can then run this file under Node against
 * the same vendored copy the pages load.
 */

export const A4 = { width: 595.276, height: 841.89 };   // points, 1 pt = 1/72 in
export const MARGIN = 18;
export const MM = 72 / 25.4;

/**
 * Place an image inside a frame without squashing it. A squashed page is visible at
 * a glance and makes a document look tampered with, which is the opposite of the
 * point.
 */
export function fitInside(imgW, imgH, frame) {
  const scale = Math.min(frame.width / imgW, frame.height / imgH);
  const width = imgW * scale, height = imgH * scale;
  return {
    width, height,
    x: frame.x + (frame.width - width) / 2,
    y: frame.y + (frame.height - height) / 2,
  };
}

/** How many pixels wide an image has to be to hit `dpi` across the usable width. */
export function pixelWidthForDpi(dpi, margin = MARGIN) {
  return Math.round(((A4.width - 2 * margin) / 72) * dpi);
}

/** The resolution a photograph of that width actually gives you on the page. */
export function dpiOfWidth(pixels, margin = MARGIN) {
  return pixels / ((A4.width - 2 * margin) / 72);
}

/**
 * One JPEG per page, laid out on A4.
 * `pages` is a list of {bytes, width, height}; `margin` in points.
 */
export async function imagesToPdf(pages, PDFLib, margin = MARGIN) {
  const doc = await PDFLib.PDFDocument.create();
  doc.setProducer("scanfix");
  doc.setCreator("scanfix");
  for (const item of pages) {
    const page = doc.addPage([A4.width, A4.height]);
    const image = await doc.embedJpg(item.bytes);
    const frame = { x: margin, y: margin, width: A4.width - 2 * margin, height: A4.height - 2 * margin };
    const box = fitInside(image.width, image.height, frame);
    page.drawImage(image, box);
  }
  return doc.save();
}
