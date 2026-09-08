#!/usr/bin/env python3
"""
Trasforma la foto (o la scansione) di un CV firmato in un PDF A4 caricabile.

Serve quando hai stampato, firmato a penna e fotografato: il portale vuole un PDF,
non un JPG, e una foto messa dentro un PDF senza accorgimenti pesa 8 MB, esce
storta e con la carta grigia.

Cosa fa, nell'ordine:
  1. raddrizza secondo l'orientamento EXIF (le foto da telefono sono quasi sempre
     ruotate nei metadati invece che nei pixel: molti visualizzatori le girano da
     soli, altri no, e il tuo CV arriva coricato);
  2. converte in scala di grigi — un CV non ha colori da salvare, e il grigio
     taglia il peso di circa due terzi;
  3. stende il bianco della carta, così lo sfondo non resta beige;
  4. ridimensiona alla risoluzione scelta (200 dpi bastano per il testo stampato);
  5. impagina su A4 con un margine, una foto per pagina;
  6. comprime in JPEG scendendo di qualità finché non sta sotto il limite.

Uso:
    python3 foto_in_pdf.py foto_cv.jpg -o CV_firmato.pdf
    python3 foto_in_pdf.py pag1.jpg pag2.jpg -o CV_firmato.pdf --max-mb 1.5
    python3 foto_in_pdf.py scansione.png --colore        # se ci tieni al colore
"""

import argparse
import io
from pathlib import Path

import pymupdf
from PIL import Image, ImageOps

A4 = (595.276, 841.890)      # punti tipografici, 1 pt = 1/72 di pollice
MARGINE = 18.0


def prepara(percorso: Path, dpi: int, colore: bool, stendi_bianco: bool) -> bytes:
    """Apre l'immagine, la raddrizza e la normalizza. Restituisce un JPEG in memoria."""
    img = Image.open(percorso)
    img = ImageOps.exif_transpose(img)          # rotazione dai metadati -> pixel

    if not colore:
        img = img.convert("L")
        if stendi_bianco:
            # autocontrast con un taglio delle code: porta la carta al bianco pieno
            # e l'inchiostro al nero, che è quello che fa una app di scansione.
            # cutoff basso perché tagliare troppo mangia i tratti sottili a matita
            # o le firme leggere.
            img = ImageOps.autocontrast(img, cutoff=(1, 6))
    else:
        img = img.convert("RGB")

    # Larghezza utile in pollici sulla pagina A4, per dimensionare a quei dpi.
    pollici = (A4[0] - 2 * MARGINE) / 72
    larghezza_px = int(pollici * dpi)
    if img.width > larghezza_px:
        altezza = round(img.height * larghezza_px / img.width)
        img = img.resize((larghezza_px, altezza), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82, optimize=True)
    return buf.getvalue()


def costruisci(immagini, out: Path, dpi: int, colore: bool, stendi_bianco: bool):
    doc = pymupdf.open()
    for percorso in immagini:
        dati = prepara(percorso, dpi, colore, stendi_bianco)
        page = doc.new_page(width=A4[0], height=A4[1])
        cornice = pymupdf.Rect(MARGINE, MARGINE, A4[0] - MARGINE, A4[1] - MARGINE)
        # keep_proportion evita lo schiacciamento: una pagina schiacciata si vede
        # subito e fa sembrare il documento manipolato.
        page.insert_image(cornice, stream=dati, keep_proportion=True)
    doc.save(str(out), garbage=4, deflate=True)
    doc.close()


def main():
    p = argparse.ArgumentParser(description="Foto o scansione del CV firmato -> PDF A4.")
    p.add_argument("immagini", nargs="+", help="una immagine per pagina, in ordine")
    p.add_argument("-o", "--output", default="CV_firmato.pdf")
    p.add_argument("--dpi", type=int, default=200,
                   help="200 basta per il testo stampato; 300 se la firma è sottile")
    p.add_argument("--colore", action="store_true",
                   help="tiene il colore (serve solo se firmi in blu e vuoi che si veda)")
    p.add_argument("--no-bianco", action="store_true",
                   help="non stendere il fondo (usalo se la carta esce slavata)")
    p.add_argument("--max-mb", type=float, default=2.0,
                   help="limite di peso: sotto questo valore i portali non protestano")
    a = p.parse_args()

    percorsi = [Path(x) for x in a.immagini]
    for x in percorsi:
        if not x.is_file():
            p.error(f"file non trovato: {x}")

    out = Path(a.output)
    dpi = a.dpi
    # Se sfora il limite si riprova a risoluzione più bassa invece di consegnare
    # un file che il portale rifiuta. 120 dpi è il pavimento: sotto, il testo
    # stampato comincia a sfaldarsi.
    while True:
        costruisci(percorsi, out, dpi, a.colore, not a.no_bianco)
        mb = out.stat().st_size / 1_048_576
        if mb <= a.max_mb or dpi <= 120:
            break
        dpi = max(120, int(dpi * 0.8))
        print(f"  {mb:.1f} MB oltre il limite, riprovo a {dpi} dpi")

    doc = pymupdf.open(out)
    print(f"Creato: {out}  ({mb:.2f} MB, {len(doc)} pagine, {dpi} dpi)")
    if mb > a.max_mb:
        print(f"  ATTENZIONE: {mb:.2f} MB, sopra il limite di {a.max_mb} MB. "
              "Rifotografa più da vicino, inquadrando solo il foglio.")
    print("Controlla a schermo intero che la firma si veda bene prima di caricare.")


if __name__ == "__main__":
    main()
