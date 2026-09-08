#!/usr/bin/env python3
"""
Trasforma la foto di un documento in qualcosa che sembra una scansione.

Il problema che risolve: fotografando un foglio, la luce non è mai uniforme. Una
metà prende luce, l'altra resta in ombra, e il risultato è un PDF in cui la parte
alta sembra un documento e quella bassa sembra una foto. Alzare la luminosità di
tutta l'immagine non serve: schiarisce anche il testo e slava la parte già buona.

La tecnica giusta si chiama *flat-field correction* ed è quella usata dalle app di
scansione. In due passaggi:

  1. Si stima l'illuminazione. Sfocando l'immagine in modo brutale spariscono
     testo e firma, e resta solo l'andamento della luce sul foglio: una mappa
     chiara dove batteva la lampada, scura nell'ombra.
  2. Si DIVIDE l'originale per quella mappa. Dove la carta era scura si divide per
     un valore piccolo e si schiarisce molto; dove era già chiara si divide per un
     valore grande e non cambia quasi nulla. L'ombra sparisce, il contrasto fra
     inchiostro e carta resta intatto ovunque.

È una correzione locale, non globale: ogni zona viene trattata secondo la luce che
ha ricevuto. Per questo funziona dove la semplice luminosità fallisce.

Uso:
    python3 pulisci_scansione.py "fix pdf ai tool.pdf" -o CV_pulito.pdf
    python3 pulisci_scansione.py foto.jpg -o CV_pulito.pdf --colore
"""

import argparse
import io
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image, ImageFilter, ImageOps

A4 = (595.276, 841.890)
MARGINE = 18.0


def carica(percorso: Path) -> Image.Image:
    """Accetta sia un'immagine sia un PDF che contiene una foto a pagina piena."""
    if percorso.suffix.lower() == ".pdf":
        doc = pymupdf.open(percorso)
        page = doc[0]
        immagini = page.get_images(full=True)
        if immagini:
            # Si prende l'immagine incorporata originale invece di ri-renderizzare
            # la pagina: rirenderizzare aggiungerebbe una seconda compressione.
            info = doc.extract_image(immagini[0][0])
            return Image.open(io.BytesIO(info["image"]))
        # Nessuna immagine: è un PDF di testo, qui non c'è niente da pulire.
        raise SystemExit("Questo PDF contiene testo, non una foto: non serve pulirlo.")
    return Image.open(percorso)


def campo_luce(grigio: np.ndarray, raggio_rel: float = 0.045) -> np.ndarray:
    """Stima l'illuminazione del foglio sfocando via tutto il contenuto.

    Il raggio è proporzionale alla larghezza: deve essere molto più grande di una
    lettera (altrimenti sfoca il testo e lo si cancella insieme all'ombra) e molto
    più piccolo del foglio (altrimenti non segue più il gradiente della luce).
    Il 4-5% della larghezza è il compromesso che regge su fogli A4 fotografati.
    """
    h, w = grigio.shape
    # astype(uint8): da un array float Pillow costruisce un'immagine in modo "F",
    # che GaussianBlur non accetta. Serve un 8 bit per canale, cioè il modo "L".
    piccola = Image.fromarray(grigio.astype(np.uint8)).resize(
        (max(w // 8, 1), max(h // 8, 1)), Image.BILINEAR)
    piccola = piccola.filter(ImageFilter.GaussianBlur(radius=max(raggio_rel * w / 8, 2)))
    return np.asarray(piccola.resize((w, h), Image.BILINEAR), dtype=np.float32)


def _appiattita(img: Image.Image) -> Image.Image:
    """Grigio con l'illuminazione già corretta: la base per misurare le righe."""
    g = np.asarray(img.convert("L"), dtype=np.float32)
    return Image.fromarray(
        np.clip(g * (255.0 / np.maximum(campo_luce(g), 1.0)), 0, 255).astype(np.uint8))


def angolo_righe(im: Image.Image, massimo=6.0) -> float:
    """Inclinazione delle righe di testo, col metodo del profilo di proiezione.

    Si ruota l'immagine di prova a vari angoli e per ognuno si sommano i pixel
    scuri riga per riga. Quando le righe di testo sono orizzontali quella somma è
    a picchi (righe piene alternate a interlinea vuota); quando sono inclinate il
    testo si spalma e il profilo si appiattisce. Massimizzare le differenze fra
    valori vicini trova l'angolo giusto senza dover riconoscere una sola lettera.

    Prima passata a mezzo grado per trovare la zona, seconda a un ventesimo di
    grado per rifinire: cercare subito fine su tutto l'intervallo costerebbe venti
    volte tanto per lo stesso risultato.
    """
    im = im.resize((700, max(int(700 * im.height / im.width), 40)), Image.BILINEAR)

    def punteggio(a):
        r = np.asarray(im.rotate(a, resample=Image.BILINEAR, fillcolor=255), dtype=np.float32)
        return float((np.diff((255.0 - r).sum(axis=1)) ** 2).sum())

    grezzo = max((punteggio(a), a) for a in np.arange(-massimo, massimo + 0.01, 0.5))[1]
    return max((punteggio(a), a) for a in np.arange(grezzo - 0.6, grezzo + 0.61, 0.05))[1]


def _una_correzione(img: Image.Image):
    """Un passaggio di raddrizzamento prospettico ricavato dal testo.

    Il foglio fotografato di sbieco è un trapezio, non un rettangolo ruotato: qui
    l'inclinazione delle righe passava da 0.00 gradi in cima a 1.00 in fondo. Una
    rotazione sola non può sistemarlo, perché non esiste un angolo giusto per
    tutta la pagina.

    Il bordo del foglio non serve — e spesso non c'è, perché la foto è già
    ritagliata o lo sfondo è chiaro quanto la carta. Bastano il rettangolo che
    racchiude il testo e due angoli misurati, uno in alto e uno in basso: con
    quelli si costruisce il trapezio effettivo e lo si rimanda a rettangolo. Una
    trasformazione proiettiva è determinata da quattro punti, e ridistribuisce da
    sola l'inclinazione intermedia.
    """
    P = _appiattita(img)
    W, H = P.size
    inchiostro = np.asarray(P) < 170
    righe = np.flatnonzero(inchiostro.sum(axis=1) > 3)
    colonne = np.flatnonzero(inchiostro.sum(axis=0) > 3)
    if len(righe) < 20 or len(colonne) < 20:
        return img, 0.0
    y0, y1, x0, x1 = righe[0], righe[-1], colonne[0], colonne[-1]

    alto = np.radians(angolo_righe(P.crop((0, int(H * 0.08), W, int(H * 0.35)))))
    basso = np.radians(angolo_righe(P.crop((0, int(H * 0.65), W, int(H * 0.95)))))
    larghezza = x1 - x0

    sorgente = [(x0, y0), (x1, y0 + larghezza * np.tan(alto)),
                (x1, y1 + larghezza * np.tan(basso)), (x0, y1)]
    destinazione = [(0, 0), (larghezza, 0), (larghezza, y1 - y0), (0, y1 - y0)]

    # PIL vuole i coefficienti della mappa destinazione -> sorgente: per ogni
    # pixel di uscita dice da dove prendere il colore in ingresso.
    A, B = [], []
    for (xd, yd), (xs, ys) in zip(destinazione, sorgente):
        A += [[xd, yd, 1, 0, 0, 0, -xs * xd, -xs * yd],
              [0, 0, 0, xd, yd, 1, -ys * xd, -ys * yd]]
        B += [xs, ys]
    coeff = np.linalg.solve(np.array(A, dtype=float), np.array(B, dtype=float))

    riempi = (255, 255, 255) if img.mode == "RGB" else 255
    fuori = img.transform((larghezza, y1 - y0), Image.PERSPECTIVE, coeff,
                          Image.BICUBIC, fillcolor=riempi)
    return fuori, abs(np.degrees(basso - alto))


def raddrizza(img: Image.Image, giri=3, soglia=0.15, verboso=True) -> Image.Image:
    """Applica la correzione finché il ventaglio residuo non è trascurabile.

    Si itera perché una singola passata lascia un residuo: la stima degli angoli
    è fatta su un'immagine ancora distorta, quindi è approssimata. Rimisurando
    sull'immagine già corretta si scende sotto il decimo di grado. Sotto 'soglia'
    ci si ferma, perché continuare significherebbe reinterpolare i pixel per un
    guadagno che nessuno vede.
    """
    for giro in range(giri):
        img, ventaglio = _una_correzione(img)
        if verboso:
            print(f"  raddrizzamento, passata {giro + 1}: ventaglio {ventaglio:.2f} gradi")
        if ventaglio < soglia:
            break

    # Il raddrizzamento ritaglia sul rettangolo del TESTO, quindi si porta via i
    # margini del foglio e il documento esce con le righe attaccate al bordo. Si
    # restituisce un margine proporzionale alla larghezza: proporzionale e non
    # fisso, così vale a qualunque risoluzione della foto.
    bordo = int(img.width * 0.06)
    riempi = (255, 255, 255) if img.mode == "RGB" else 255
    tela = Image.new(img.mode, (img.width + 2 * bordo, img.height + 2 * bordo), riempi)
    tela.paste(img, (bordo, bordo))
    if verboso:
        print(f"  margine restituito: {bordo} px per lato")
    return tela


def pulisci(img: Image.Image, colore: bool, forza: float) -> Image.Image:
    img = ImageOps.exif_transpose(img)
    grigio = np.asarray(img.convert("L"), dtype=np.float32)

    luce = campo_luce(grigio)
    luce = np.maximum(luce, 1.0)              # mai dividere per zero

    if colore:
        rgb = np.asarray(img.convert("RGB"), dtype=np.float32)
        # Stesso fattore di correzione sui tre canali: normalizza la luce senza
        # spostare le tinte, così una firma in blu resta blu.
        fattore = (255.0 / luce)[:, :, None]
        fuori = np.clip(rgb * fattore, 0, 255)
    else:
        fuori = np.clip(grigio * (255.0 / luce), 0, 255)

    # Ora la carta è uniforme ma grigina. Si fissano punto di bianco e di nero:
    # il bianco sul valore tipico della carta (percentile alto), il nero un po'
    # sopra lo zero per non impastare i tratti sottili della firma.
    riferimento = fuori if fuori.ndim == 2 else fuori.mean(axis=2)
    bianco = np.percentile(riferimento, 92)
    nero = np.percentile(riferimento, 2)
    bianco = max(bianco, nero + 20)
    # 'forza' avvicina il punto di bianco: più alto = carta più bianca, ma sopra
    # ~1.15 comincia a mangiare l'inchiostro chiaro.
    bianco = nero + (bianco - nero) / forza

    fuori = np.clip((fuori - nero) * (255.0 / (bianco - nero)), 0, 255)
    out = Image.fromarray(fuori.astype(np.uint8), mode="RGB" if colore else "L")
    # Maschera di contrasto leggera: la divisione ammorbidisce un po' i bordi.
    return out.filter(ImageFilter.UnsharpMask(radius=1.2, percent=55, threshold=3))


def adatta_ad_A4(img: Image.Image, lato=0.07, alto=0.035, verboso=True) -> Image.Image:
    """Ricostruisce attorno al testo la carta che l'inquadratura ha tagliato via.

    Il problema: la foto ha proporzioni 0.81, un A4 ne ha 0.707. Appoggiandola
    sulla pagina si riempie la larghezza e restano due bande bianche sopra e sotto
    — 76 pt ciascuna contro 18 pt ai lati — e il documento sembra ballare in mezzo
    al foglio invece di essere il foglio.

    Ritagliare per pareggiare le proporzioni non è possibile: servirebbero 132 px
    di larghezza e ai lati ce ne sono 18 e 43, quindi si taglierebbe il testo. Si
    aggiunge carta, allora, invece di toglierne.

    Dove metterla non è arbitrario: si riproducono i margini del CV digitale di
    partenza, 7% ai lati e 3.5% in alto, e l'avanzo finisce in fondo. Non è uno
    sbilanciamento, è com'era il documento originale — un CV che finisce a due
    terzi di pagina ha molto bianco sotto, e ricentrare il testo lo farebbe
    sembrare una lettera, non un curriculum.
    """
    grigio = np.asarray(img.convert("L"), dtype=np.float32)
    inchiostro = grigio < 170
    righe = np.flatnonzero(inchiostro.sum(axis=1) > 2)
    colonne = np.flatnonzero(inchiostro.sum(axis=0) > 2)
    if len(righe) < 10 or len(colonne) < 10:
        return img

    x0, x1, y0, y1 = int(colonne[0]), int(colonne[-1]), int(righe[0]), int(righe[-1])
    larghezza_testo, altezza_testo = x1 - x0, y1 - y0

    tela_w = round(larghezza_testo / (1 - 2 * lato))
    tela_h = round(tela_w / 0.70711)
    # Se il testo è troppo alto per starci con un margine sotto decente, comanda
    # l'altezza e la larghezza segue: meglio margini laterali larghi che testo
    # tagliato in fondo.
    minimo = round(altezza_testo / (1 - alto - 0.04))
    if tela_h < minimo:
        tela_h, tela_w = minimo, round(minimo * 0.70711)

    mx, my = round(tela_w * lato), round(tela_h * alto)
    riempi = (255, 255, 255) if img.mode == "RGB" else 255
    tela = Image.new(img.mode, (tela_w, tela_h), riempi)
    tela.paste(img, (mx - x0, my - y0))

    if verboso:
        sotto = tela_h - my - altezza_testo
        print(f"  adattata ad A4: tela {tela_w}x{tela_h} px "
              f"(rapporto {tela_w / tela_h:.4f}), margini lato {mx} alto {my} basso {sotto} px")
    return tela


def in_pdf(img: Image.Image, out: Path, dpi: int, margine: float = MARGINE):
    pollici = (A4[0] - 2 * margine) / 72
    larghezza_px = int(pollici * dpi)
    if img.width > larghezza_px:
        img = img.resize((larghezza_px, round(img.height * larghezza_px / img.width)),
                         Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85, optimize=True)

    doc = pymupdf.open()
    page = doc.new_page(width=A4[0], height=A4[1])
    page.insert_image(pymupdf.Rect(margine, margine, A4[0] - margine, A4[1] - margine),
                      stream=buf.getvalue(), keep_proportion=True)
    doc.save(str(out), garbage=4, deflate=True)
    doc.close()


def main():
    p = argparse.ArgumentParser(description="Foto di un documento -> PDF che sembra scansionato.")
    p.add_argument("input", help="immagine, o PDF che contiene la foto")
    p.add_argument("-o", "--output", default="documento_pulito.pdf")
    p.add_argument("--colore", action="store_true",
                   help="mantiene il colore (per una firma in penna blu)")
    p.add_argument("--forza", type=float, default=1.06,
                   help="quanto sbiancare la carta: 1.0 delicato, 1.15 aggressivo")
    p.add_argument("--dpi", type=int, default=200)
    p.add_argument("--no-adatta", action="store_true",
                   help="non ricostruire i margini: lascia le bande bianche sopra e sotto")
    p.add_argument("--no-raddrizza", action="store_true",
                   help="salta il raddrizzamento prospettico (tiene la pagina com'è)")
    a = p.parse_args()

    src = Path(a.input)
    if not src.is_file():
        p.error(f"file non trovato: {src}")

    originale = carica(src)
    dpi_reali = originale.width / ((A4[0] - 2 * MARGINE) / 72)
    lavoro = originale if a.no_raddrizza else raddrizza(ImageOps.exif_transpose(originale))
    pulita = pulisci(lavoro, a.colore, a.forza)
    if a.no_adatta:
        in_pdf(pulita, Path(a.output), a.dpi)
    else:
        # Adattata ad A4 la carta E la pagina hanno le stesse proporzioni, quindi
        # si appoggia a filo pagina: i margini sono già dentro l'immagine.
        in_pdf(adatta_ad_A4(pulita), Path(a.output), a.dpi, margine=0.0)

    mb = Path(a.output).stat().st_size / 1_048_576
    print(f"Creato: {a.output}  ({mb:.2f} MB)")
    print(f"Foto di partenza: {originale.width}x{originale.height} px "
          f"= circa {dpi_reali:.0f} dpi sulla pagina")
    if dpi_reali < 150:
        print("  NOTA: sotto i 150 dpi il testo resta un po' morbido. La pulizia "
              "toglie l'ombra ma non inventa dettaglio: se puoi, rifai la foto "
              "inquadrando solo il foglio, senza tavolo attorno.")


if __name__ == "__main__":
    main()
