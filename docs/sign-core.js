/**
 * Add a place, a date and a signature rule to the foot of an existing PDF.
 *
 * A port of tools/add_date_signature.py. The document is not rebuilt: pdf-lib opens
 * it and writes into the empty space at the bottom of the last page, so layout,
 * fonts and pagination come out exactly as they went in.
 *
 * pdf.js and pdf-lib are injected rather than imported, so tests/test_sign.mjs can
 * run this file under Node with the vendored copies the pages use.
 *
 * Two coordinate systems meet here and it is worth being explicit about it. PyMuPDF
 * measures y downwards from the top of the page; pdf.js and pdf-lib measure it
 * upwards from the bottom. Everything below is in the upward system, and the
 * comments give the Python line it corresponds to where the two differ.
 */

export const MONTHS = {
  en: ["January", "February", "March", "April", "May", "June",
       "July", "August", "September", "October", "November", "December"],
  it: ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
       "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"],
};

export const INK = [0.10, 0.13, 0.17];

/** 8 September 2026 — no leading zero, the way it is written by hand. */
export function spelledDate(date, locale = "en") {
  const months = MONTHS[locale] || MONTHS.en;
  return `${date.getDate()} ${months[date.getMonth()]} ${date.getFullYear()}`;
}

/** Parse a yyyy-mm-dd string as a local date, avoiding the UTC shift of Date(). */
export function parseDate(value) {
  const [y, m, d] = value.split("-").map(Number);
  return new Date(y, m - 1, d);
}

// Strings that give away an uncompiled template. A real case: an application portal
// rejected a CV because the heading still read "name" instead of a person's name.
export const PLACEHOLDERS = [
  [/^\s*name\s*$/i, "the name at the top"],
  [/email@|firstname\.lastname@|nome\.cognome@|your\.?mail@/i, "the email address"],
  [/\+?\s*3{4,}/, "the phone number"],
  [/\[[^\]]{2,}\]/, "a field in square brackets"],
];

export function remainingPlaceholders(lines) {
  const found = [];
  for (const line of lines) {
    for (const [rx, label] of PLACEHOLDERS) {
      if (rx.test(line.trim()) && !found.includes(label)) found.push(label);
    }
  }
  return found;
}

/**
 * Read the page's real margins and the foot of its text from the text itself.
 *
 * This is what anchors the block to the same left margin as everything above it. At
 * a fixed coordinate it would be a few millimetres out on any document whose margins
 * differ, and that is exactly the sort of detail that makes a file look tampered
 * with.
 */
export function textGeometry(items, page) {
  const boxes = items.filter(it => it.str && it.str.trim());
  if (!boxes.length) {
    return { left: page.width - 42 > 42 ? 42 : 0, right: page.width - 42, bottom: page.height - 42 };
  }
  return {
    left: Math.min(...boxes.map(it => it.x)),
    right: Math.max(...boxes.map(it => it.x + it.width)),
    bottom: Math.min(...boxes.map(it => it.y)),      // lowest baseline on the page
  };
}

/**
 * Where the block goes. `spilled` says a fresh sheet was needed, which the caller
 * reports: quietly turning a one-page document into a two-page one with a nearly
 * empty second sheet is the kind of surprise you notice after uploading it.
 *
 * The threshold is the Python `y + 34 > page.rect.y1 - 40` written the other way up.
 */
export function blockPlacement(geometry, page) {
  let y = geometry.bottom - 46;          // breathing room under the last line
  let { left, right } = geometry;
  const spilled = y < 74;
  if (spilled) {
    y = page.height - 70;
    left = 42.5;
    right = page.width - 42.5;
  }
  return { left, right, y, ruleY: y - 26, middle: left + (right - left) / 2, spilled };
}

/**
 * Read every page's text with pdf.js, as lines, plus the last page's item boxes.
 *
 * The copy is not defensive tidiness: pdf.js transfers the array it is given to its
 * worker, which DETACHES the buffer. Hand it the caller's bytes and the next thing
 * to touch them — pdf-lib opening the same document, the second pass that verifies
 * the result — gets an empty array and an error that names neither cause.
 */
export async function readText(bytes, pdfjs) {
  const pdf = await pdfjs.getDocument({ data: Uint8Array.from(bytes), isEvalSupported: false }).promise;
  const lines = [];
  let lastItems = [];
  for (let n = 1; n <= pdf.numPages; n++) {
    const page = await pdf.getPage(n);
    const content = await page.getTextContent();
    let current = "";
    const items = [];
    for (const it of content.items) {
      if (typeof it.str === "string") current += it.str;
      if (it.transform) {
        items.push({ str: it.str, x: it.transform[4], y: it.transform[5], width: it.width || 0 });
      }
      if (it.hasEOL) { lines.push(current); current = ""; }
    }
    if (current) lines.push(current);
    if (n === pdf.numPages) lastItems = items;
    page.cleanup();
  }
  const pageCount = pdf.numPages;
  await pdf.destroy();
  return { lines, lastItems, pageCount };
}

/**
 * @param {Uint8Array} bytes        the PDF to sign
 * @param {object} options          {place, date (Date), locale, label, signature}
 *                                  signature is {bytes, type: "png"|"jpg"}
 * @param {object} deps             {PDFLib, pdfjs}
 */
export async function signPdf(bytes, options, deps) {
  const { PDFLib, pdfjs } = deps;
  const { place = "", label = "Signature", locale = "en", signature = null } = options;
  const day = spelledDate(options.date || new Date(), locale);

  const before = await readText(bytes, pdfjs);
  const doc = await PDFLib.PDFDocument.load(bytes, { ignoreEncryption: true });
  const font = await doc.embedFont(PDFLib.StandardFonts.Helvetica);

  let page = doc.getPage(doc.getPageCount() - 1);
  const size = { width: page.getWidth(), height: page.getHeight() };
  const geometry = textGeometry(before.lastItems, size);
  const spot = blockPlacement(geometry, size);

  if (spot.spilled) page = doc.addPage([size.width, size.height]);

  const colour = PDFLib.rgb(...INK);
  // Without a place the line is just the date: ", 8 September 2026" would be a
  // visible artefact of an unset field.
  const stamp = place ? `${place}, ${day}` : day;
  page.drawText(stamp, { x: spot.left, y: spot.y, size: 10, font, color: colour });
  page.drawText(label, { x: spot.middle, y: spot.y, size: 10, font, color: colour });

  if (signature) {
    const image = signature.type === "png"
      ? await doc.embedPng(signature.bytes)
      : await doc.embedJpg(signature.bytes);
    // Proportions come from the file. A squashed signature looks forged.
    let height = 20;
    const width = Math.min(height * image.width / image.height, spot.right - spot.middle - 4);
    height = width * image.height / image.width;
    page.drawImage(image, { x: spot.middle + 2, y: spot.ruleY + 1, width, height });
  }

  page.drawLine({
    start: { x: spot.middle, y: spot.ruleY },
    end: { x: spot.right, y: spot.ruleY },
    thickness: 0.7,
    color: colour,
  });

  const out = await doc.save();

  // Check the date is actually READABLE and that no text was lost. Not paranoia:
  // the first version of the Python script wrote a date that displayed on screen
  // and extracted as null bytes, and without this check the defect would have
  // reached the portal it was uploaded to.
  const after = await readText(out, pdfjs);
  const joined = after.lines.join("\n");
  const problems = [];
  if (!joined.includes(day)) problems.push(`the date "${day}" is not extractable from the PDF`);
  const lost = before.lines.filter(l => l.trim() && !joined.includes(l));
  if (lost.length) {
    problems.push(`${lost.length} lines of the original are gone: ${JSON.stringify(lost.slice(0, 3))}`);
  }

  return {
    bytes: out,
    date: day,
    spilled: spot.spilled,
    pagesBefore: before.pageCount,
    pagesAfter: after.pageCount,
    problems,
    placeholders: remainingPlaceholders(after.lines),
    alreadySigned: before.lines.slice(-12).join(" ").includes(label),
  };
}
