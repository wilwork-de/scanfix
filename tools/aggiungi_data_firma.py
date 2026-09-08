#!/usr/bin/env python3
"""
Aggiunge data e blocco firma a un CV PDF già esistente, senza rifarlo.

A differenza di genera_cv.py, che costruisce il CV da zero, questo prende il tuo
PDF così com'è e ci stampa sopra solo quello che manca. Layout, font e
impaginazione restano identici: si scrive solo nello spazio vuoto in fondo.

Uso:
    python3 aggiungi_data_firma.py "cv example.pdf"
    python3 aggiungi_data_firma.py "cv example.pdf" --firma firma.png --luogo Torino

DUE COSE CHE HO PROVATO E CHE NON FUNZIONANO — sono qui perché sembrano
ragionevoli e falliscono in silenzio, che è il modo peggiore di fallire.

1. *Riusare il font incorporato nel PDF* per far sembrare l'aggiunta originale.
   I font incorporati sono sottoinsiemi CID: contengono solo i glifi serviti a
   quel documento, con una codifica interna tutta loro. Reinserirli produce testo
   che si vede a schermo ma si estrae come byte nulli. Il PDF sembra giusto e il
   parser del portale non ci legge nessuna data. Si usa Helvetica, che è uno dei
   14 font garantiti da ogni lettore: non pareggia Carlito, ma è corretto.

2. *Sostituire i segnaposto ("name", "email@gmail.com") dentro il PDF.*
   La redazione di PyMuPDF cancella tutto il testo il cui riquadro TOCCA l'area
   scelta, e i riquadri sono gonfiati dall'interlinea: quello dell'intestazione a
   20pt arriva a y=63 e sfiora la riga dei contatti che comincia a y=56. Risultato,
   spariscono anche email e telefono senza un errore. Stringere l'area non basta,
   perché è l'intersezione dei riquadri a decidere.
   I segnaposto si correggono nel file sorgente (.docx / .odt) e si riesporta.
   Lo script qui sotto si limita a segnalarli, e non li tocca.
"""

import argparse
import re
from datetime import date
from pathlib import Path

import pymupdf

MESI = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]

NERO = (0.10, 0.13, 0.17)

# Testi che tradiscono un modello non compilato. Il portale ITS ha respinto il CV
# proprio perché al posto del nome c'era un segnaposto.
SEGNAPOSTO = [
    (re.compile(r"^\s*name\s*$", re.I), "il nome e cognome in cima"),
    (re.compile(r"email@|nome\.cognome@|tuamail@", re.I), "l'indirizzo email"),
    (re.compile(r"\+?\s*3{4,}"), "il numero di telefono"),
    (re.compile(r"\[[^\]]{2,}\]"), "un campo fra parentesi quadre"),
]


def data_italiana(g: date) -> str:
    """8 settembre 2026 — giorno senza zero iniziale, come si scrive a mano."""
    return f"{g.day} {MESI[g.month - 1]} {g.year}"


def geometria(page):
    """Margini reali e fondo del testo, letti dal documento invece che assunti.

    Serve per agganciare il blocco firma allo stesso margine sinistro del CV: se
    lo mettessi a una coordinata fissa, su un PDF con margini diversi risulterebbe
    disallineato di qualche millimetro, che è esattamente il genere di dettaglio
    che fa sembrare un documento rimaneggiato.
    """
    blocchi = [b for b in page.get_text("blocks") if b[4].strip()]
    if not blocchi:
        return page.rect.x0 + 42, page.rect.x1 - 42, page.rect.y0 + 42
    return (min(b[0] for b in blocchi),
            max(b[2] for b in blocchi),
            max(b[3] for b in blocchi))


def blocco_data_firma(doc, page, luogo, giorno, firma=None):
    """Stampa 'Luogo, data' a sinistra e 'Firma' + riga a destra, in fondo."""
    sx, dx, fondo = geometria(page)
    y = fondo + 46          # aria fra l'ultima riga del CV e il blocco firma

    if y + 34 > page.rect.y1 - 40:
        # Pagina piena: meglio un foglio nuovo che la firma schiacciata nel margine.
        page = doc.new_page(width=page.rect.width, height=page.rect.height)
        y = page.rect.y0 + 70
        sx, dx = 42.5, page.rect.x1 - 42.5

    meta = sx + (dx - sx) / 2
    page.insert_text((sx, y), f"{luogo}, {giorno}", fontname="helv", fontsize=10, color=NERO)
    page.insert_text((meta, y), "Firma", fontname="helv", fontsize=10, color=NERO)

    y_riga = y + 26
    if firma:
        # L'immagine si appoggia SOPRA la riga, come una firma vera. Le proporzioni
        # si ricavano dal file: schiacciare una firma la fa sembrare finta.
        img = pymupdf.Pixmap(str(firma))
        alt = 20.0
        larg = min(alt * img.width / img.height, dx - meta - 4)
        alt = larg * img.height / img.width
        page.insert_image(
            pymupdf.Rect(meta + 2, y_riga - alt - 1, meta + 2 + larg, y_riga - 1),
            filename=str(firma), keep_proportion=True,
        )

    page.draw_line((meta, y_riga), (dx, y_riga), color=NERO, width=0.7)
    return page


def segnaposto_rimasti(doc):
    trovati = []
    for page in doc:
        for riga in page.get_text().splitlines():
            for rx, etichetta in SEGNAPOSTO:
                if rx.search(riga.strip()) and etichetta not in trovati:
                    trovati.append(etichetta)
    return trovati


def verifica(percorso, atteso, originale):
    """Controlla che la data sia davvero LEGGIBILE e che non si sia perso testo.

    Non è paranoia: la prima versione di questo script scriveva una data che si
    vedeva a schermo ma si estraeva come byte nulli. Senza questo controllo il
    difetto sarebbe arrivato al portale.
    """
    doc = pymupdf.open(percorso)
    testo = "\n".join(p.get_text() for p in doc)
    problemi = []
    if atteso not in testo:
        problemi.append(f"la data {atteso!r} non è estraibile dal PDF")
    if "Firma" not in testo:
        problemi.append("la parola 'Firma' non è estraibile dal PDF")
    perse = [r for r in originale.splitlines() if r.strip() and r not in testo]
    if perse:
        problemi.append(f"{len(perse)} righe dell'originale sono sparite: {perse[:3]}")
    return problemi


def main():
    p = argparse.ArgumentParser(description="Aggiunge data e firma a un CV PDF esistente.")
    p.add_argument("pdf", help="il CV di partenza")
    p.add_argument("--luogo", default="Torino")
    p.add_argument("--data", default=None, help="aaaa-mm-gg (default: oggi)")
    p.add_argument("--firma", default=None, help="PNG/JPG della firma scansionata")
    p.add_argument("--output", default=None)
    a = p.parse_args()

    src = Path(a.pdf)
    if not src.is_file():
        p.error(f"file non trovato: {src}")
    firma = Path(a.firma).expanduser() if a.firma else None
    if firma and not firma.is_file():
        p.error(f"file firma non trovato: {firma}")

    giorno = data_italiana(date.fromisoformat(a.data) if a.data else date.today())
    out = Path(a.output) if a.output else src.with_name(src.stem + "_firmato.pdf")

    doc = pymupdf.open(src)
    originale = "\n".join(pg.get_text() for pg in doc)
    blocco_data_firma(doc, doc[-1], a.luogo, giorno, firma)
    doc.save(str(out), garbage=4, deflate=True)

    problemi = verifica(out, giorno, originale)
    print(f"Creato: {out}")
    for x in problemi:
        print(f"  PROBLEMA: {x}")

    rimasti = segnaposto_rimasti(pymupdf.open(out))
    if rimasti:
        print("DA CORREGGERE nel file sorgente (.docx/.odt) e riesportare: "
              + ", ".join(rimasti))
    if not firma:
        print("Riga della firma vuota: stampa e firma a penna, "
              "oppure rilancia con --firma firma.png")
    return 1 if problemi else 0


if __name__ == "__main__":
    raise SystemExit(main())
