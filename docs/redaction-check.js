/**
 * Client-side redaction check for PDFs.
 *
 * Mirrors tools/check_redaction.py. Same idea, same thresholds, same verdict: find
 * the filled shapes that are large and dark enough to hide something, then look at
 * what is still readable UNDERNEATH them.
 *
 * A PDF is a stack of objects drawn one over another, not a flattened image. A
 * rectangle over a name adds an object, it does not remove one: the name stays in
 * the file and comes back by selecting it with the mouse.
 *
 * The module does not import pdf.js: it receives the already-open document and the
 * OPS table. That way the same file runs in the browser (pdf.js from a CDN) and
 * under Node in the tests, so the code that is tested is the code that ships.
 */

export const DARKNESS_THRESHOLD = 0.12;   // below this the tint is too light to cover
export const MIN_AREA = 60;               // square points; below this it is decoration

// --- minimal geometry -------------------------------------------------------

function apply(m, x, y) {
  return [m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]];
}

function multiply(a, b) {
  return [
    a[0] * b[0] + a[2] * b[1], a[1] * b[0] + a[3] * b[1],
    a[0] * b[2] + a[2] * b[3], a[1] * b[2] + a[3] * b[3],
    a[0] * b[4] + a[2] * b[5] + a[4], a[1] * b[4] + a[3] * b[5] + a[5],
  ];
}

function transformedBox(m, x0, y0, x1, y1) {
  const pts = [apply(m, x0, y0), apply(m, x1, y0), apply(m, x0, y1), apply(m, x1, y1)];
  const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

function area(r) { return Math.max(0, r[2] - r[0]) * Math.max(0, r[3] - r[1]); }

function overlap(a, b) {
  return a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3];
}

// --- colour -----------------------------------------------------------------

/** 0 = white, 1 = black. Used to discard near-white fills. */
function darkness(colour) {
  if (!colour) return 0;
  const mean = (colour[0] + colour[1] + colour[2]) / 3;
  return 1 - mean / 255;
}

// --- reading a page ---------------------------------------------------------

/**
 * Walk the operator list and collect filled shapes and images.
 *
 * Drawing in a PDF is a state machine: save/restore push the current matrix,
 * transform multiplies it, constructPath prepares a path and only a fill operation
 * actually paints it. So seeing a rectangle is not enough — you have to see whether
 * anything filled it, and in what colour, because a path with no fill covers nothing.
 */
async function pageElements(page, OPS) {
  const list = await page.getOperatorList();
  const shapes = [];
  const images = [];

  let ctm = [1, 0, 0, 1, 0, 0];
  const stack = [];
  let fill = null;
  let path = null;

  for (let i = 0; i < list.fnArray.length; i++) {
    const op = list.fnArray[i];
    const args = list.argsArray[i];

    if (op === OPS.save) { stack.push(ctm.slice()); continue; }
    if (op === OPS.restore) { ctm = stack.pop() || [1, 0, 0, 1, 0, 0]; continue; }
    if (op === OPS.transform) { ctm = multiply(ctm, args); continue; }

    if (op === OPS.setFillRGBColor) { fill = [args[0], args[1], args[2]]; continue; }
    if (op === OPS.setFillGray) { const v = args[0] * 255; fill = [v, v, v]; continue; }
    if (op === OPS.setFillCMYKColor) {
      const [c, m, y, k] = args;
      fill = [255 * (1 - Math.min(1, c + k)), 255 * (1 - Math.min(1, m + k)),
              255 * (1 - Math.min(1, y + k))];
      continue;
    }

    if (op === OPS.constructPath) {
      // args = [operations, coordinates, minMax]. The third element is already the
      // bounding box of the path, so it need not be rebuilt from the segments.
      const mm = args[2];
      path = (mm && mm.length === 4) ? transformedBox(ctm, mm[0], mm[1], mm[2], mm[3]) : null;
      continue;
    }

    const fills = op === OPS.fill || op === OPS.eoFill || op === OPS.fillStroke ||
                  op === OPS.eoFillStroke || op === OPS.closeFillStroke;
    if (fills && path) {
      shapes.push({ box: path, darkness: darkness(fill), source: "drawing" });
      path = null;
      continue;
    }

    if (op === OPS.paintImageXObject || op === OPS.paintInlineImageXObject) {
      // An image is painted by mapping the unit square through the current matrix:
      // its place on the page is that square, transformed.
      images.push(transformedBox(ctm, 0, 0, 1, 1));
    }
  }

  return { shapes, images };
}

/** Text with its position, in the same space as the shapes. */
async function pageText(page) {
  const content = await page.getTextContent();
  return content.items
    .filter(it => it.str && it.str.trim())
    .map(it => {
      const t = it.transform;
      const x = t[4], y = t[5];
      return { text: it.str, box: [x, y, x + (it.width || 0), y + (it.height || 0)] };
    });
}

/**
 * Square and highlight annotations: they cover like a rectangle, and worse, in many
 * readers they come off with a single click.
 */
async function coveringAnnotations(page) {
  let annots = [];
  try { annots = await page.getAnnotations(); } catch { return []; }
  const out = [];
  for (const a of annots) {
    const kind = a.subtype || "";
    if (!["Square", "Highlight", "Redact"].includes(kind)) continue;
    if (!a.rect || a.rect.length !== 4) continue;
    const r = [Math.min(a.rect[0], a.rect[2]), Math.min(a.rect[1], a.rect[3]),
               Math.max(a.rect[0], a.rect[2]), Math.max(a.rect[1], a.rect[3])];
    const c = a.color || a.interiorColor;
    out.push({
      box: r,
      darkness: c ? darkness([c[0], c[1], c[2]]) : 1,
      source: `${kind} annotation`,
    });
  }
  return out;
}

// --- analysis ---------------------------------------------------------------

/**
 * @param {*} pdf document already opened by pdf.js
 * @param {*} OPS the pdfjsLib.OPS table
 * @returns {Promise<{verdict: string, pages: Array, totalPages: number}>}
 */
export async function analyseDocument(pdf, OPS) {
  const pages = [];

  for (let n = 1; n <= pdf.numPages; n++) {
    const page = await pdf.getPage(n);
    const { shapes, images } = await pageElements(page, OPS);
    const texts = await pageText(page);
    const all = shapes.concat(await coveringAnnotations(page));

    const findings = [];
    for (const shape of all) {
      const r = shape.box;
      if (area(r) < MIN_AREA) continue;
      if (shape.darkness < DARKNESS_THRESHOLD) continue;

      // Shrink by one point so text that merely grazes the edge of the shape is not
      // counted as sitting underneath it.
      const inner = [r[0] + 1, r[1] + 1, r[2] - 1, r[3] - 1];
      const underneath = texts.filter(t => overlap(inner, t.box))
                              .map(t => t.text).join(" ").trim();
      const overImage = images.some(im => overlap(r, im));

      if (!underneath && !overImage) continue;   // covers blank paper: graphics

      findings.push({
        box: r.map(v => Math.round(v * 10) / 10),
        source: shape.source,
        darkness: Math.round(shape.darkness * 1000) / 1000,
        textUnderneath: underneath.slice(0, 300),
        overImage,
      });
    }

    if (findings.length) pages.push({ page: n, findings });
    page.cleanup();
  }

  return {
    totalPages: pdf.numPages,
    pages,
    verdict: pages.length ? "SUSPECT" : "CLEAN",
  };
}
