#!/usr/bin/env python3
"""
Ritaglia la firma da una foto del documento firmato e la salva come PNG trasparente.

A cosa serve: è il pezzo che manca per avere un CV *vero* in PDF invece della foto
di un CV. Fotografando tutto il foglio ottieni un'immagine — testo morbido, peso
alto, niente testo selezionabile. Se invece prendi solo la firma e la incolli sul
PDF digitale originale, il documento resta nitido e leggibile da un parser, e la
firma è comunque inchiostro vero scritto a mano.

Come isola i tratti dallo sfondo: si corregge l'illuminazione (stessa tecnica di
pulisci_scansione.py), poi si costruisce il canale ALFA dalla scurezza del pixel.
Carta chiara -> trasparente, inchiostro scuro -> opaco, e i pixel intermedi restano
semitrasparenti, il che tiene i bordi morbidi invece che seghettati. Una soglia
netta produrrebbe una firma scalettata che si vede subito che è ritagliata.

Uso:
    python3 estrai_firma.py "foto_firmata.pdf" -o firma.png
    python3 estrai_firma.py foto.jpg --riquadro 0.5,0.75,1.0,0.95 -o firma.png
    python3 estrai_firma.py foto.jpg --blu -o firma.png     # tiene la penna blu

Poi si incolla sul CV digitale:
    python3 aggiungi_data_firma.py CV.pdf --firma firma.png
"""

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

from pulisci_scansione import campo_luce, carica

# Zona in cui sta la firma su un CV: metà destra, fascia bassa. Espressa in
# frazioni della pagina così vale a qualunque risoluzione della foto.
RIQUADRO = (0.45, 0.70, 1.00, 0.97)


def togli_segmenti_lunghi(alfa: np.ndarray, frazione: float) -> np.ndarray:
    """Cancella il filetto stampato sotto la firma, lasciando i tratti a penna.

    Primo tentativo, sbagliato: azzerare le righe di pixel coperte di inchiostro
    oltre una certa percentuale. Non funziona, perché nella foto il foglio è
    leggermente ruotato e il filetto attraversa una decina di righe diverse senza
    riempirne nessuna.

    Questo invece guarda i *segmenti continui* dentro ogni riga: un filetto resta
    una corsa ininterrotta di pixel scuri anche se inclinato, mentre una firma è
    fatta di tratti che cambiano direzione di continuo e si spezzano. Si azzera
    ogni corsa più lunga di 'frazione' della larghezza.

    MISURATO E NON FUNZIONA su una foto storta, per questo il default è 0 (spento).
    Sul CV di prova il filetto era inclinato quel tanto che bastava: la corsa più
    lunga in una singola riga di pixel arrivava a 75 su 508, cioè il 15%, mentre i
    tratti della firma arrivavano a 66. Le due popolazioni si sovrappongono, quindi
    non esiste una soglia che tolga la riga senza mangiare la firma. Separarle per
    davvero vorrebbe dire raddrizzare l'immagine e cercare le rette (Hough), cioè
    un altro ordine di complessità.

    Serve solo su una scansione dritta, dove il filetto attraversa poche righe e le
    riempie tutte. La strada pulita resta un'altra: firmare su un foglio BIANCO,
    dove non c'è nessuna riga da separare.
    """
    soglia = max(int(alfa.shape[1] * frazione), 8)
    scuro = (alfa > 20).astype(np.int8)
    for y in range(scuro.shape[0]):
        bordi = np.flatnonzero(np.diff(np.concatenate(([0], scuro[y], [0]))))
        for inizio, fine in zip(bordi[::2], bordi[1::2]):
            if fine - inizio >= soglia:
                alfa[y, inizio:fine] = 0
    return alfa


def estrai(img: Image.Image, riquadro, chiaro: float, scuro: float, blu: bool,
           lunghezza_riga: float = 0.30):
    w, h = img.size
    x0, y0, x1, y1 = (int(riquadro[0] * w), int(riquadro[1] * h),
                      int(riquadro[2] * w), int(riquadro[3] * h))
    ritaglio = img.crop((x0, y0, x1, y1))

    grigio = np.asarray(ritaglio.convert("L"), dtype=np.float32)
    luce = np.maximum(campo_luce(grigio), 1.0)
    piatto = np.clip(grigio * (255.0 / luce), 0, 255)

    # Alfa a rampa: sopra 'chiaro' è carta (trasparente), sotto 'scuro' è pieno
    # inchiostro (opaco), in mezzo si sfuma. Sono i due numeri da toccare se la
    # firma esce sbiadita (alza 'chiaro') o se resta sporco di fondo (abbassalo).
    alfa = np.clip((chiaro - piatto) / max(chiaro - scuro, 1.0) * 255.0, 0, 255)

    if lunghezza_riga:
        alfa = togli_segmenti_lunghi(alfa, lunghezza_riga)

    if blu:
        rgb = np.asarray(ritaglio.convert("RGB"), dtype=np.float32)
        fattore = (255.0 / luce)[:, :, None]
        colore = np.clip(rgb * fattore * 0.75, 0, 255).astype(np.uint8)
    else:
        colore = np.zeros(piatto.shape + (3,), dtype=np.uint8)   # inchiostro nero

    out = Image.fromarray(np.dstack([colore, alfa.astype(np.uint8)]), mode="RGBA")

    # Si stringe sul contenuto: un PNG con mezza pagina di trasparenza attorno
    # verrebbe scalato male quando lo si appoggia sulla riga della firma.
    bbox = Image.fromarray((alfa > 30).astype(np.uint8) * 255).getbbox()
    if bbox:
        pad = 6
        out = out.crop((max(bbox[0] - pad, 0), max(bbox[1] - pad, 0),
                        min(bbox[2] + pad, out.width), min(bbox[3] + pad, out.height)))
    return out, alfa


def main():
    p = argparse.ArgumentParser(description="Estrae la firma da una foto -> PNG trasparente.")
    p.add_argument("input", help="foto o PDF del documento firmato")
    p.add_argument("-o", "--output", default="firma.png")
    p.add_argument("--riquadro", default=None,
                   help="zona da guardare, in frazioni: x0,y0,x1,y1 (default: basso a destra)")
    p.add_argument("--chiaro", type=float, default=205.0,
                   help="sopra questo valore è carta; alzalo se la firma esce sbiadita")
    p.add_argument("--scuro", type=float, default=95.0,
                   help="sotto questo valore è inchiostro pieno")
    p.add_argument("--blu", action="store_true", help="mantiene il colore della penna")
    p.add_argument("--lunghezza-riga", type=float, default=0.0,
                   help="toglie i segmenti orizzontali oltre questa frazione. Utile solo su\n                        scansioni dritte: su una foto storta non funziona, vedi il codice")
    p.add_argument("--anteprima", default=None,
                   help="salva una griglia con le frazioni per scegliere --riquadro")
    a = p.parse_args()

    src = Path(a.input)
    if not src.is_file():
        p.error(f"file non trovato: {src}")

    riquadro = RIQUADRO
    if a.riquadro:
        riquadro = tuple(float(v) for v in a.riquadro.split(","))
        if len(riquadro) != 4:
            p.error("--riquadro vuole quattro numeri: x0,y0,x1,y1")

    img = carica(src)

    if a.anteprima:
        # Griglia con le frazioni scritte sopra: si legge dove cade la firma e si
        # riportano i quattro numeri in --riquadro. Più rapido che indovinare.
        from PIL import ImageDraw
        g = img.convert("RGB").copy()
        d = ImageDraw.Draw(g)
        for i in range(1, 20):
            f = i / 20
            d.line([(f * g.width, 0), (f * g.width, g.height)], fill=(255, 0, 0), width=1)
            d.line([(0, f * g.height), (g.width, f * g.height)], fill=(0, 120, 255), width=1)
            d.text((f * g.width + 2, 2), f"{f:.2f}", fill=(255, 0, 0))
            d.text((2, f * g.height + 2), f"{f:.2f}", fill=(0, 120, 255))
        g.save(a.anteprima)
        print(f"Griglia salvata in {a.anteprima}: rosso = x, blu = y.")
        print("Leggi gli angoli della firma e rilancia con "
              "--riquadro x0,y0,x1,y1")
        return

    firma, alfa = estrai(img, riquadro, a.chiaro, a.scuro, a.blu, a.lunghezza_riga)
    firma.save(a.output)

    copertura = float((alfa > 30).mean()) * 100
    print(f"Creato: {a.output}  ({firma.width}x{firma.height} px)")
    print(f"Inchiostro trovato nella zona: {copertura:.1f}%")
    if copertura < 0.4:
        print("  Quasi nulla: la firma non è in quella zona. Passa --riquadro "
              "con le frazioni giuste, es. --riquadro 0.4,0.6,1.0,0.95")
    elif copertura > 25:
        print("  Troppo: hai preso dentro anche testo o l'ombra del foglio. "
              "Stringi il riquadro, o abbassa --chiaro.")
    print("Aprilo e controllalo prima di usarlo: deve vedersi solo la firma, "
          "su sfondo a scacchi (trasparente).")


if __name__ == "__main__":
    main()
