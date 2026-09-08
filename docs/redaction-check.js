/**
 * Controllo della redazione di un PDF, lato client.
 *
 * Rispecchia tools/controlla_redazione.py. Stessa idea, stesse soglie, stesso
 * verdetto: si cercano le forme piene abbastanza grandi e scure da nascondere
 * qualcosa, e si guarda cosa resta leggibile SOTTO di loro.
 *
 * Un PDF e' una pila di oggetti disegnati uno sull'altro, non un'immagine
 * appiattita. Un rettangolo sopra un nome aggiunge un oggetto, non ne toglie uno:
 * il nome resta nel file e si rilegge selezionandolo col mouse.
 *
 * Il modulo non importa pdf.js: riceve il documento gia' aperto e la tabella OPS.
 * Cosi' lo stesso file gira nel browser (pdf.js dal CDN) e sotto Node nei test,
 * ed e' davvero lo stesso codice a essere collaudato e pubblicato.
 */

export const SOGLIA_SCUREZZA = 0.12;   // sotto: tinta troppo chiara per coprire
export const AREA_MINIMA = 60;         // punti quadrati: sotto e' decorazione

// --- geometria minima -------------------------------------------------------

function applica(m, x, y) {
  return [m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]];
}

function moltiplica(a, b) {
  return [
    a[0] * b[0] + a[2] * b[1], a[1] * b[0] + a[3] * b[1],
    a[0] * b[2] + a[2] * b[3], a[1] * b[2] + a[3] * b[3],
    a[0] * b[4] + a[2] * b[5] + a[4], a[1] * b[4] + a[3] * b[5] + a[5],
  ];
}

function riquadroTrasformato(m, x0, y0, x1, y1) {
  const punti = [applica(m, x0, y0), applica(m, x1, y0), applica(m, x0, y1), applica(m, x1, y1)];
  const xs = punti.map(p => p[0]), ys = punti.map(p => p[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

function area(r) { return Math.max(0, r[2] - r[0]) * Math.max(0, r[3] - r[1]); }

function siSovrappongono(a, b) {
  return a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3];
}

// --- colore -----------------------------------------------------------------

/** 0 = bianco, 1 = nero. Serve a scartare i riempimenti quasi bianchi. */
function scurezza(colore) {
  if (!colore) return 0;
  const media = (colore[0] + colore[1] + colore[2]) / 3;
  return 1 - media / 255;
}

// --- lettura della pagina ---------------------------------------------------

/**
 * Cammina la lista degli operatori e raccoglie forme piene e immagini.
 *
 * Il disegno in un PDF e' una macchina a stati: save/restore impilano la matrice
 * corrente, transform la moltiplica, constructPath prepara un tracciato e solo
 * un'operazione di riempimento lo materializza. Quindi non basta vedere un
 * rettangolo: bisogna vedere se qualcuno lo ha effettivamente riempito, e con
 * quale colore, perche' un tracciato senza riempimento non copre niente.
 */
async function elementiDellaPagina(page, OPS) {
  const lista = await page.getOperatorList();
  const forme = [];
  const immagini = [];

  let ctm = [1, 0, 0, 1, 0, 0];
  const pila = [];
  let riempimento = null;
  let tracciato = null;

  for (let i = 0; i < lista.fnArray.length; i++) {
    const op = lista.fnArray[i];
    const args = lista.argsArray[i];

    if (op === OPS.save) { pila.push(ctm.slice()); continue; }
    if (op === OPS.restore) { ctm = pila.pop() || [1, 0, 0, 1, 0, 0]; continue; }
    if (op === OPS.transform) { ctm = moltiplica(ctm, args); continue; }

    if (op === OPS.setFillRGBColor) { riempimento = [args[0], args[1], args[2]]; continue; }
    if (op === OPS.setFillGray) { const v = args[0] * 255; riempimento = [v, v, v]; continue; }
    if (op === OPS.setFillCMYKColor) {
      const [c, m2, y2, k] = args;
      riempimento = [255 * (1 - Math.min(1, c + k)), 255 * (1 - Math.min(1, m2 + k)),
                     255 * (1 - Math.min(1, y2 + k))];
      continue;
    }

    if (op === OPS.constructPath) {
      // args = [operazioni, coordinate, minMax]. Il terzo elemento e' gia' il
      // riquadro del tracciato, quindi non serve ricostruirlo dai segmenti.
      const mm = args[2];
      tracciato = (mm && mm.length === 4) ? riquadroTrasformato(ctm, mm[0], mm[1], mm[2], mm[3]) : null;
      continue;
    }

    const riempie = op === OPS.fill || op === OPS.eoFill || op === OPS.fillStroke ||
                    op === OPS.eoFillStroke || op === OPS.closeFillStroke;
    if (riempie && tracciato) {
      forme.push({ riquadro: tracciato, scurezza: scurezza(riempimento), origine: "disegno" });
      tracciato = null;
      continue;
    }

    if (op === OPS.paintImageXObject || op === OPS.paintInlineImageXObject) {
      // Un'immagine si disegna mappando il quadrato unitario con la matrice
      // corrente: il suo posto sulla pagina e' quel quadrato trasformato.
      immagini.push(riquadroTrasformato(ctm, 0, 0, 1, 1));
    }
  }

  return { forme, immagini };
}

/** Testo con la sua posizione, nello stesso spazio delle forme. */
async function testoDellaPagina(page) {
  const contenuto = await page.getTextContent();
  return contenuto.items
    .filter(it => it.str && it.str.trim())
    .map(it => {
      const t = it.transform;
      const x = t[4], y = t[5];
      return { testo: it.str, riquadro: [x, y, x + (it.width || 0), y + (it.height || 0)] };
    });
}

/** Annotazioni quadrate o evidenziatori: coprono come un rettangolo, e in piu' */
/** spesso si tolgono con un clic nel lettore. */
async function annotazioniCoprenti(page) {
  let annots = [];
  try { annots = await page.getAnnotations(); } catch { return []; }
  const fuori = [];
  for (const a of annots) {
    const tipo = a.subtype || "";
    if (!["Square", "Highlight", "Redact"].includes(tipo)) continue;
    if (!a.rect || a.rect.length !== 4) continue;
    const r = [Math.min(a.rect[0], a.rect[2]), Math.min(a.rect[1], a.rect[3]),
               Math.max(a.rect[0], a.rect[2]), Math.max(a.rect[1], a.rect[3])];
    const c = a.color || a.interiorColor;
    fuori.push({
      riquadro: r,
      scurezza: c ? scurezza([c[0], c[1], c[2]]) : 1,
      origine: `annotazione ${tipo}`,
    });
  }
  return fuori;
}

// --- analisi ----------------------------------------------------------------

/**
 * @param {*} pdf documento gia' aperto da pdf.js
 * @param {*} OPS tabella pdfjsLib.OPS
 * @returns {Promise<{verdetto: string, pagine: Array, totalePagine: number}>}
 */
export async function analizzaDocumento(pdf, OPS) {
  const pagine = [];

  for (let n = 1; n <= pdf.numPages; n++) {
    const page = await pdf.getPage(n);
    const { forme, immagini } = await elementiDellaPagina(page, OPS);
    const testi = await testoDellaPagina(page);
    const tutte = forme.concat(await annotazioniCoprenti(page));

    const reperti = [];
    for (const forma of tutte) {
      const r = forma.riquadro;
      if (area(r) < AREA_MINIMA) continue;
      if (forma.scurezza < SOGLIA_SCUREZZA) continue;

      // Si stringe di un punto per non catturare il testo che sfiora il bordo
      // della forma senza esserci sotto davvero.
      const dentro = [r[0] + 1, r[1] + 1, r[2] - 1, r[3] - 1];
      const sotto = testi.filter(t => siSovrappongono(dentro, t.riquadro))
                         .map(t => t.testo).join(" ").trim();
      const sopraImmagine = immagini.some(im => siSovrappongono(r, im));

      if (!sotto && !sopraImmagine) continue;   // copre carta bianca: e' grafica

      reperti.push({
        riquadro: r.map(v => Math.round(v * 10) / 10),
        origine: forma.origine,
        scurezza: Math.round(forma.scurezza * 1000) / 1000,
        testoSotto: sotto.slice(0, 300),
        sopraImmagine,
      });
    }

    if (reperti.length) pagine.push({ pagina: n, reperti });
    page.cleanup();
  }

  return {
    totalePagine: pdf.numPages,
    pagine,
    verdetto: pagine.length ? "SOSPETTO" : "PULITO",
  };
}
