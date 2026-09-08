/**
 * Collaudo del checker JavaScript, lo stesso file che gira nel sito.
 *
 * Il punto di questo test non e' solo "il JS funziona": e' che il JS dia gli
 * STESSI verdetti della versione Python sugli stessi campioni. Due implementazioni
 * che divergono in silenzio sono peggio di una sola, perche' il sito direbbe una
 * cosa e lo script un'altra sullo stesso documento.
 *
 *   node tests/prova_js.mjs
 */

import { fileURLToPath } from "node:url";
import path from "node:path";
import fs from "node:fs";

import * as pdfjs from "pdfjs-dist/legacy/build/pdf.mjs";
import { analizzaDocumento } from "../docs/redaction-check.js";

const QUI = path.dirname(fileURLToPath(import.meta.url));
const CAMPIONI = path.join(QUI, "campioni");

const ATTESI = [
  ["finta_redazione.pdf", "SOSPETTO", ["Mario Ross", "RSSMRA80A01H50", "IT60X05428111"]],
  ["redazione_vera.pdf", "PULITO", []],
  ["foto_con_rettangoli.pdf", "SOSPETTO", []],
  ["pulito.pdf", "PULITO", []],
  ["fascia_grafica.pdf", "SOSPETTO", ["RELAZIONE ANNUALE"]],
];

let passati = 0, falliti = 0;

function ok(descrizione, dettaglio = "") {
  console.log(`  ok    ${descrizione.padEnd(52)} ${dettaglio}`);
  passati++;
}
function ko(descrizione, dettaglio = "") {
  console.log(`  FALLITO ${descrizione.padEnd(50)} ${dettaglio}`);
  falliti++;
}

for (const [nome, atteso, frammenti] of ATTESI) {
  const percorso = path.join(CAMPIONI, nome);
  if (!fs.existsSync(percorso)) {
    ko(nome, "campione mancante: lancia prima tests/genera_campioni.py");
    continue;
  }
  const dati = new Uint8Array(fs.readFileSync(percorso));
  const pdf = await pdfjs.getDocument({ data: dati, isEvalSupported: false }).promise;
  const esito = await analizzaDocumento(pdf, pdfjs.OPS);

  if (esito.verdetto === atteso) ok(nome, esito.verdetto);
  else ko(nome, `atteso ${atteso}, ottenuto ${esito.verdetto}`);

  const tuttoIlTesto = esito.pagine
    .flatMap(p => p.reperti.map(r => r.testoSotto)).join(" | ");
  for (const f of frammenti) {
    if (tuttoIlTesto.includes(f)) ok(`  rilegge "${f}"`);
    else ko(`  rilegge "${f}"`, `non trovato in ${JSON.stringify(tuttoIlTesto).slice(0, 90)}`);
  }

  if (nome === "foto_con_rettangoli.pdf") {
    const suImmagine = esito.pagine.flatMap(p => p.reperti).filter(r => r.sopraImmagine);
    if (suImmagine.length >= 3) ok("  riconosce le coperture sopra l'immagine", `${suImmagine.length}`);
    else ko("  riconosce le coperture sopra l'immagine", `trovate ${suImmagine.length}, attese >= 3`);
  }

  await pdf.destroy();
}

console.log(`\n${passati} superati, ${falliti} falliti`);
process.exit(falliti ? 1 : 0);
