#!/usr/bin/env python3
"""
Costruisce i PDF di prova per il controllo della redazione.

Sono generati, non raccolti: nessun documento reale, nessun dato di nessuno. I nomi
e i numeri dentro sono inventati e servono solo a far vedere che il testo "coperto"
si rilegge.

    python3 tests/genera_campioni.py            # scrive in tests/campioni/
"""

from pathlib import Path

import pymupdf

QUI = Path(__file__).parent
FUORI = QUI / "campioni"

RISERVATO = [
    "Nome: Mario Rossi",
    "Codice fiscale: RSSMRA80A01H501U",
    "IBAN: IT60X0542811101000000123456",
]


def _pagina_con_dati(doc):
    page = doc.new_page()
    page.insert_text((60, 80), "Modulo di esempio", fontname="hebo", fontsize=16)
    page.insert_text((60, 110), "Documento generato per collaudo. Dati inventati.",
                     fontname="helv", fontsize=9, color=(0.4, 0.4, 0.4))
    y = 160
    riquadri = []
    for riga in RISERVATO:
        page.insert_text((60, y), riga, fontname="helv", fontsize=12)
        riquadri.append(pymupdf.Rect(56, y - 12, 56 + 5.9 * len(riga), y + 4))
        y += 34
    return page, riquadri


def finta_redazione():
    """Il caso da riconoscere: rettangoli neri sopra il testo, che resta nel file."""
    doc = pymupdf.open()
    page, riquadri = _pagina_con_dati(doc)
    for r in riquadri:
        page.draw_rect(r, color=(0, 0, 0), fill=(0, 0, 0))
    doc.save(FUORI / "finta_redazione.pdf")
    doc.close()


def redazione_vera():
    """Lo stesso documento oscurato come si deve: il contenuto viene rimosso."""
    doc = pymupdf.open()
    page, riquadri = _pagina_con_dati(doc)
    for r in riquadri:
        page.add_redact_annot(r, fill=(0, 0, 0))
    page.apply_redactions()
    doc.save(FUORI / "redazione_vera.pdf")
    doc.close()


def foto_con_rettangoli():
    """Il caso visto dal vivo: pagina che è una foto, con rettangoli disegnati sopra.

    Qui sotto i rettangoli non c'è testo ma pixel, e l'immagine incorporata non
    viene toccata da niente che le si disegni sopra: si riestrae intatta.
    """
    sorgente = pymupdf.open()
    page, riquadri = _pagina_con_dati(sorgente)
    pix = page.get_pixmap(dpi=110)
    sorgente.close()

    doc = pymupdf.open()
    pagina = doc.new_page(width=595, height=842)
    pagina.insert_image(pymupdf.Rect(0, 0, 595, 842), pixmap=pix, keep_proportion=True)
    fattore = 595 / pix.width * (pix.width / 595)
    for r in riquadri:
        pagina.draw_rect(pymupdf.Rect(r.x0, r.y0, r.x1, r.y1),
                         color=(0.31, 0.51, 0.74), fill=(0.31, 0.51, 0.74))
    doc.save(FUORI / "foto_con_rettangoli.pdf")
    doc.close()


def pulito():
    """Un documento normale, senza niente sopra niente."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((60, 80), "Relazione trimestrale", fontname="hebo", fontsize=16)
    page.insert_text((60, 120), "Testo ordinario, nessuna forma sovrapposta.",
                     fontname="helv", fontsize=11)
    doc.save(FUORI / "pulito.pdf")
    doc.close()


def fascia_grafica():
    """Il falso positivo onesto: una fascia colorata con la scritta bianca sopra.

    Vista dal file è identica a una censura — un rettangolo pieno con del testo
    dentro. Per questo lo strumento non dà un verdetto secco ma mostra il testo che
    trova sotto: qui è il titolo stesso, e chi guarda capisce in un secondo che non
    è una fuga. Distinguerle automaticamente vorrebbe dire indovinare l'intenzione.
    """
    doc = pymupdf.open()
    page = doc.new_page()
    page.draw_rect(pymupdf.Rect(0, 0, 595, 90), color=(0.1, 0.2, 0.5), fill=(0.1, 0.2, 0.5))
    page.insert_text((60, 55), "RELAZIONE ANNUALE", fontname="hebo", fontsize=20,
                     color=(1, 1, 1))
    page.insert_text((60, 140), "Corpo del documento.", fontname="helv", fontsize=11)
    doc.save(FUORI / "fascia_grafica.pdf")
    doc.close()


if __name__ == "__main__":
    FUORI.mkdir(parents=True, exist_ok=True)
    for f in (finta_redazione, redazione_vera, foto_con_rettangoli, pulito, fascia_grafica):
        f()
        print(f"  {f.__name__}.pdf")
    print(f"Campioni in {FUORI}")
