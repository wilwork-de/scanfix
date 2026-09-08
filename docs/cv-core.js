/**
 * Build a one-page CV as a PDF, in English or Italian.
 *
 * A port of tools/make_cv.py, which lays the page out with fpdf2. pdf-lib has no
 * layout engine at all — it draws text where you tell it — so the millimetre
 * bookkeeping fpdf2 does is done here: a cursor running down the page, cells with a
 * height, and word wrapping measured against the real font metrics.
 *
 * pdf-lib is injected so tests/test_cv.mjs can build a CV under Node and read the
 * result back with pdf.js.
 */

export const MM = 72 / 25.4;

// Restrained palette: near-black for headings, grey for the body. No bright colour
// — an institutional CV has to read when it comes out of a black and white printer.
const INK = [26, 32, 44];
const GREY = [74, 85, 104];
const LIGHT_GREY = [160, 174, 192];
const RULE = [203, 213, 224];

export const MONTHS = {
  en: ["January", "February", "March", "April", "May", "June",
       "July", "August", "September", "October", "November", "December"],
  it: ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
       "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"],
};

// Document strings: what the reader sees on the page, so they stay in their own
// language. The Italian block is copied from tools/make_cv.py unchanged.
export const LABELS = {
  en: {
    personal: "Personal details", education: "Education",
    experience: "Experience", skills: "Skills", languages: "Languages",
    other: "Additional information", signature: "Signature",
    born_on: "Date of birth", born_in: "Place of birth",
    citizenship: "Citizenship", licence: "Driving licence", page: "page",
    privacy: "",
  },
  it: {
    personal: "Dati personali", education: "Istruzione e formazione",
    experience: "Esperienza professionale", skills: "Competenze tecniche",
    languages: "Lingue", other: "Altre informazioni", signature: "Firma",
    born_on: "Data di nascita", born_in: "Luogo di nascita",
    citizenship: "Cittadinanza", licence: "Patente", page: "pag.",
    // The GDPR line. It cites the Regulation first, which is the higher and current
    // source; the Italian Code is the national law that was harmonised to it.
    //
    // Do NOT cite "art. 13 del D.Lgs. 196/2003": that article was REPEALED by
    // D.Lgs. 101/2018. Half the templates online still point at it.
    privacy: ("Autorizzo il trattamento dei miei dati personali contenuti nel " +
              "presente curriculum vitae ai sensi del Regolamento UE 2016/679 " +
              "(GDPR) e del D. Lgs. 196/2003 come modificato dal D. Lgs. 101/2018."),
  },
};

export function spelledDate(date, locale = "en") {
  const months = MONTHS[locale] || MONTHS.en;
  return `${date.getDate()} ${months[date.getMonth()]} ${date.getFullYear()}`;
}

/**
 * The core PDF fonts are encoded in WinAnsi, which covers Western European text and
 * nothing else. A smart quote pasted in from a word processor is fine; a Cyrillic or
 * Chinese character is not, and pdf-lib throws rather than dropping it. Map what has
 * an obvious equivalent, and report the rest instead of failing on the whole CV.
 */
const SUBSTITUTES = {
  "‘": "'", "’": "'", "“": '"', "”": '"',
  "–": "-", "—": "-", "…": "...", "•": "-",
  " ": " ", " ": " ", "−": "-", "ʼ": "'",
};

export function sanitise(text, dropped) {
  let out = "";
  for (const ch of String(text)) {
    if (SUBSTITUTES[ch] !== undefined) { out += SUBSTITUTES[ch]; continue; }
    const code = ch.codePointAt(0);
    if (code === 10 || code === 13 || (code >= 32 && code <= 255)) { out += ch; continue; }
    if (dropped && !dropped.includes(ch)) dropped.push(ch);
  }
  return out;
}

/**
 * Parse the repeated sections out of a textarea.
 *
 * One entry per paragraph. The first line is "Title | Organisation | Period" and
 * every line under it is a bullet. Blank line, next entry. It is the shortest syntax
 * that survives being typed into a box by hand, and it round-trips: what you see in
 * the field is what comes out on the page.
 */
export function parseEntries(text) {
  const entries = [];
  for (const chunk of String(text).split(/\n\s*\n/)) {
    const lines = chunk.split("\n").map(l => l.trim()).filter(Boolean);
    if (!lines.length) continue;
    const [title, org = "", period = ""] = lines[0].split("|").map(s => s.trim());
    entries.push({ title, org, period, notes: lines.slice(1).map(l => l.replace(/^[-*•]\s*/, "")) });
  }
  return entries;
}

/** "Label: value" per line, for skills and languages. */
export function parsePairs(text) {
  return String(text).split("\n").map(l => l.trim()).filter(Boolean).map(line => {
    const at = line.indexOf(":");
    return at < 0 ? [line, ""] : [line.slice(0, at).trim(), line.slice(at + 1).trim()];
  });
}

export function parseLines(text) {
  return String(text).split("\n").map(l => l.trim()).filter(Boolean);
}

/**
 * A cursor running down an A4 sheet, in millimetres from the top left, which is how
 * fpdf2 works and therefore how the Python original is written. Everything converts
 * to points at the moment it is drawn.
 */
class Sheet {
  constructor(doc, fonts, labels, name, PDFLib) {
    this.doc = doc;
    this.PDFLib = PDFLib;
    this.fonts = fonts;
    this.labels = labels;
    this.name = name;
    this.W = 210;
    this.H = 297;
    this.left = 18;
    this.right = 18;
    this.top = 16;
    this.bottom = 18;
    this.pages = [];
    this.dropped = [];
    this.addPage();
  }

  get epw() { return this.W - this.left - this.right; }
  get remaining() { return this.H - this.bottom - this.y; }

  addPage() {
    this.page = this.doc.addPage([this.W * MM, this.H * MM]);
    this.pages.push(this.page);
    this.y = this.top;
    return this.page;
  }

  font(style) {
    return this.fonts[style] || this.fonts.regular;
  }

  widthOf(text, size, style) {
    return this.font(style).widthOfTextAtSize(text, size) / MM;
  }

  draw(text, xMm, baselineMm, { size = 10, style = "regular", colour = INK } = {}) {
    const clean = sanitise(text, this.dropped);
    if (!clean) return;
    this.page.drawText(clean, {
      x: xMm * MM,
      y: (this.H - baselineMm) * MM,
      size,
      font: this.font(style),
      color: this.rgb(colour),
    });
  }

  rgb(c) {
    return this.PDFLib.rgb(c[0] / 255, c[1] / 255, c[2] / 255);
  }

  /** One line of text in a cell of height h, vertically centred like fpdf2's cell. */
  cell(h, text, opts = {}) {
    const { size = 10, align = "left", width = this.epw, x = this.left } = opts;
    let cx = x;
    if (align === "right") cx = x + width - this.widthOf(sanitise(text, null), size, opts.style);
    else if (align === "center") cx = x + (width - this.widthOf(sanitise(text, null), size, opts.style)) / 2;
    this.draw(text, cx, this.y + h / 2 + (size / MM) * 0.35, opts);
    if (opts.advance !== false) this.y += h;
  }

  /** Word wrapping measured against the real font metrics, not a character count. */
  wrap(text, width, size, style) {
    const words = sanitise(text, this.dropped).split(/\s+/).filter(Boolean);
    const lines = [];
    let line = "";
    for (const word of words) {
      const candidate = line ? `${line} ${word}` : word;
      if (line && this.widthOf(candidate, size, style) > width) { lines.push(line); line = word; }
      else line = candidate;
    }
    if (line) lines.push(line);
    return lines.length ? lines : [""];
  }

  multiCell(width, h, text, opts = {}) {
    const { size = 10, style = "regular", x = this.left } = opts;
    for (const line of this.wrap(text, width, size, style)) {
      this.cell(h, line, { ...opts, x, width, advance: true });
    }
  }

  rule(y, colour = RULE, thickness = 0.25) {
    this.page.drawLine({
      start: { x: this.left * MM, y: (this.H - y) * MM },
      end: { x: (this.W - this.right) * MM, y: (this.H - y) * MM },
      thickness: thickness * MM,
      color: this.rgb(colour),
    });
  }
}

function rgbOf(PDFLib, c) {
  return PDFLib.rgb(c[0] / 255, c[1] / 255, c[2] / 255);
}

/**
 * @param {object} data     the CV fields
 * @param {object} options  {locale, place, date, signature: {bytes, type}}
 * @param {object} PDFLib   the pdf-lib module
 */
export async function buildCv(data, options, PDFLib) {
  const locale = options.locale === "it" ? "it" : "en";
  const labels = LABELS[locale];
  const doc = await PDFLib.PDFDocument.create();
  const fonts = {
    regular: await doc.embedFont(PDFLib.StandardFonts.Helvetica),
    bold: await doc.embedFont(PDFLib.StandardFonts.HelveticaBold),
    italic: await doc.embedFont(PDFLib.StandardFonts.HelveticaOblique),
  };

  const name = `${data.first_name || ""} ${data.last_name || ""}`.trim();
  doc.setTitle(`Curriculum Vitae - ${name}`);
  doc.setAuthor(name);
  doc.setProducer("scanfix");
  doc.setCreator("scanfix");

  const sheet = new Sheet(doc, fonts, labels, name, PDFLib);

  // --- heading ---
  sheet.cell(9, name.toUpperCase(), { size: 21, style: "bold", colour: INK });
  if (data.headline) sheet.cell(5.5, data.headline, { size: 10.5, colour: GREY });
  sheet.y += 2.5;

  const contacts = [data.phone, data.email, data.linkedin].filter(Boolean);
  // · is a middle dot: it exists in WinAnsi, unlike the bullet character.
  if (contacts.length) sheet.cell(4.6, contacts.join("  ·  "), { size: 9, colour: GREY });
  if (data.address) sheet.cell(4.6, data.address, { size: 9, colour: GREY });

  sheet.y += 3;
  sheet.rule(sheet.y, INK, 0.5);
  sheet.y += 5;

  const section = (title) => {
    // Under 22 mm there is no point opening a section: the heading would be orphaned
    // at the foot of the page.
    if (sheet.remaining < 22) sheet.addPage();
    sheet.cell(5.5, title.toUpperCase(), { size: 10, style: "bold", colour: INK });
    sheet.rule(sheet.y + 0.4);
    sheet.y += 3;
  };

  const bullet = (text, indent = 3.5) => {
    const x = sheet.left + indent;
    sheet.page.drawRectangle({
      x: x * MM, y: (sheet.H - sheet.y - 3.2) * MM,
      width: 1.3 * MM, height: 1.3 * MM,
      color: rgbOf(PDFLib, LIGHT_GREY),
    });
    sheet.multiCell(sheet.epw - indent - 3.6, 4.7, text,
                    { size: 9.5, colour: GREY, x: x + 3.6 });
  };

  const pair = (label, value, width = 42) => {
    const y = sheet.y;
    sheet.cell(5, label, { size: 9.5, style: "bold", colour: INK, width, advance: false });
    sheet.multiCell(sheet.epw - width, 5, value, { size: 9.5, colour: GREY, x: sheet.left + width });
    sheet.y = Math.max(sheet.y, y + 5);
  };

  const entry = (e) => {
    const dateWidth = 38;
    const y = sheet.y;
    sheet.multiCell(sheet.epw - dateWidth, 5, e.title, { size: 10, style: "bold", colour: INK });
    if (e.period) {
      const after = sheet.y;
      sheet.y = y;
      sheet.cell(5, e.period, {
        size: 9, colour: GREY, align: "right",
        x: sheet.W - sheet.right - dateWidth, width: dateWidth, advance: false,
      });
      sheet.y = after;
    }
    if (e.org) sheet.multiCell(sheet.epw, 4.8, e.org, { size: 9.5, style: "italic", colour: GREY });
    for (const note of e.notes || []) bullet(note);
    sheet.y += 2.6;
  };

  // --- personal details ---
  const personal = [
    [labels.born_on, data.born_on], [labels.born_in, data.born_in],
    [labels.citizenship, data.citizenship], [labels.licence, data.licence],
  ].filter(([, v]) => v);
  if (personal.length) {
    section(labels.personal);
    for (const [k, v] of personal) pair(k, v);
    sheet.y += 3;
  }

  for (const key of ["education", "experience"]) {
    if (data[key] && data[key].length) {
      section(labels[key]);
      for (const e of data[key]) entry(e);
    }
  }

  for (const key of ["skills", "languages"]) {
    if (data[key] && data[key].length) {
      section(labels[key]);
      for (const [k, v] of data[key]) pair(k, v, 46);
      sheet.y += 3;
    }
  }

  if (data.other && data.other.length) {
    section(labels.other);
    for (const line of data.other) bullet(line);
    sheet.y += 3;
  }

  // --- the signature block ---
  // This is the part institutional portals reject a CV over. Always in this order:
  // the data-protection authorisation first, then place and date on the same line as
  // the signature.
  if (sheet.remaining < 48) sheet.addPage(); else sheet.y += 4;

  if (labels.privacy) {
    sheet.multiCell(sheet.epw, 3.9, labels.privacy, { size: 8, colour: GREY });
    sheet.y += 8;
  }

  const y = sheet.y;
  const half = sheet.epw / 2;
  const day = spelledDate(options.date || new Date(), locale);
  sheet.cell(5, options.place ? `${options.place}, ${day}` : day,
             { size: 10, colour: INK, width: half, advance: false });
  sheet.cell(5, labels.signature, { size: 10, colour: INK, x: sheet.left + half, width: half, advance: false });

  const ruleY = y + 18;
  if (options.signature) {
    const image = options.signature.type === "png"
      ? await doc.embedPng(options.signature.bytes)
      : await doc.embedJpg(options.signature.bytes);
    const width = Math.min(14 * image.width / image.height, half - 2);
    const height = width * image.height / image.width;
    // The image sits ON the rule, half a millimetre clear of it, like a real
    // signature written across the line.
    sheet.page.drawImage(image, {
      x: (sheet.left + half + 1) * MM,
      y: (sheet.H - ruleY + 0.5) * MM,
      width: width * MM,
      height: height * MM,
    });
  }

  sheet.page.drawLine({
    start: { x: (sheet.left + half) * MM, y: (sheet.H - ruleY) * MM },
    end: { x: (sheet.W - sheet.right) * MM, y: (sheet.H - ruleY) * MM },
    thickness: 0.3 * MM,
    color: rgbOf(PDFLib, INK),
  });
  sheet.y = ruleY;

  // --- page numbers ---
  // Harmless on a one-page CV, useful on two if the sheets get separated after
  // printing.
  const total = sheet.pages.length;
  sheet.pages.forEach((page, i) => {
    const text = sanitise(`${name} - ${labels.page} ${i + 1}/${total}`, sheet.dropped);
    const width = fonts.regular.widthOfTextAtSize(text, 7.5);
    page.drawText(text, {
      x: (sheet.W * MM - width) / 2,
      y: 10 * MM,
      size: 7.5,
      font: fonts.regular,
      color: rgbOf(PDFLib, LIGHT_GREY),
    });
  });

  return { bytes: await doc.save(), pages: total, dropped: sheet.dropped, date: day };
}
