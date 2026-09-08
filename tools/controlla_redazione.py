#!/usr/bin/env python3
"""
Verifica se l'oscuramento di un PDF regge davvero, o se è solo un rettangolo sopra.

Il problema. Un PDF non è un'immagine appiattita: è una pila di oggetti disegnati
uno sull'altro. Mettere un rettangolo nero sopra un nome AGGIUNGE un oggetto, non
ne toglie uno. Il nome resta nel file, sotto, e chiunque lo riprende con tre righe
di codice o selezionandolo col mouse. È così che sono usciti atti giudiziari e
documenti governativi che si credevano oscurati.

Vale per i rettangoli di Word e Anteprima, per gli evidenziatori, e per i "tool AI
per PDF" che promettono di censurare un documento.

Cosa fa questo script. Per ogni pagina raccoglie le forme piene (rettangoli e
riempimenti vettoriali) e le annotazioni opache, poi guarda cosa c'è SOTTO ognuna:

  - se sotto c'è testo estraibile, lo stampa. Se quel testo è un nome o un numero,
    l'oscuramento è finto e i dati sono leggibili;
  - se sotto c'è un'immagine, segnala che il contenuto è recuperabile estraendo
    l'immagine incorporata, che non viene toccata da niente che le si disegni sopra.

Perché stampa il testo trovato invece di limitarsi a un verdetto: un rettangolo
pieno sopra del testo non è sempre una censura. Una fascia colorata di intestazione
con la scritta bianca sopra è la stessa cosa vista dal file. Mostrando cosa c'è
sotto, la distinzione la fa una persona in un secondo, senza che il programma debba
indovinare l'intenzione.

Come si oscura davvero:
  1. una vera redazione, che rimuove il contenuto invece di coprirlo. In PyMuPDF
     page.add_redact_annot(rect) seguito da page.apply_redactions();
  2. oppure si appiattisce: si renderizza la pagina in immagine, si copre, si
     riesporta. Grezzo ma efficace, perché ricostruisce i pixel da zero;
  3. in ogni caso si riapre il file finito e si ricontrolla. Con questo script.

Uso:
    python3 controlla_redazione.py documento.pdf
    python3 controlla_redazione.py *.pdf --silenzioso     # solo il verdetto
    python3 controlla_redazione.py doc.pdf --json         # per farci una pipeline

Codici di uscita: 0 nulla di sospetto, 1 possibile fuga, 2 errore di lettura.
"""

import argparse
import json
import sys
from pathlib import Path

import pymupdf

# Un riempimento chiarissimo di solito è uno sfondo pagina o una filigrana, non una
# censura: nessuno oscura un dato con il bianco su bianco. Sotto questa soglia di
# "quanto è scura la tinta" la forma non viene considerata coprente.
SOGLIA_SCUREZZA = 0.12

# Forme minuscole sono decorazioni, punti elenco, bordi di tabella. Una censura ha
# la dimensione di quello che nasconde, quindi almeno qualche punto per lato.
AREA_MINIMA = 60.0     # punti quadrati


def scurezza(colore) -> float:
    """0 = bianco, 1 = nero. Serve a scartare i riempimenti quasi bianchi."""
    if colore is None:
        return 0.0
    if isinstance(colore, (int, float)):
        return 1.0 - float(colore)
    valori = list(colore)[:3]
    if not valori:
        return 0.0
    return 1.0 - sum(float(v) for v in valori) / len(valori)


def forme_coprenti(page):
    """Rettangoli e riempimenti vettoriali abbastanza grandi e scuri da nascondere.

    Si guardano solo i disegni con un riempimento ('f' = fill, 'fs' = fill+stroke).
    Un tratto senza riempimento non copre niente: una riga o un bordo lasciano
    vedere quello che c'è sotto, quindi non sono candidati a censura.
    """
    fuori = []
    for d in page.get_drawings():
        if d.get("type") not in ("f", "fs"):
            continue
        r = pymupdf.Rect(d["rect"])
        if r.get_area() < AREA_MINIMA or not r.is_valid:
            continue
        s = scurezza(d.get("fill"))
        if s < SOGLIA_SCUREZZA:
            continue
        fuori.append({"rect": r, "scurezza": round(s, 3), "origine": "disegno"})

    # Le annotazioni quadrate opache fanno lo stesso lavoro e sono ancora peggio:
    # spesso si cancellano con un clic nel lettore PDF.
    for a in page.annots() or []:
        if a.type[1] not in ("Square", "Highlight", "Redact"):
            continue
        r = pymupdf.Rect(a.rect)
        if r.get_area() < AREA_MINIMA:
            continue
        colori = a.colors or {}
        s = scurezza(colori.get("fill") or colori.get("stroke"))
        if s < SOGLIA_SCUREZZA and a.type[1] != "Redact":
            continue
        fuori.append({"rect": r, "scurezza": round(s, 3),
                      "origine": f"annotazione {a.type[1]}"})
    return fuori


def rettangoli_delle_immagini(page):
    """Dove stanno le immagini sulla pagina, con due ripieghi.

    Serve un percorso robusto perché la prima versione di questo controllo dava
    PULITO proprio sul caso per cui era stata scritta: una pagina che era una foto
    con quattro rettangoli sopra. Causa: get_image_rects() restituiva [0,0,0,0],
    un rettangolo degenere, quindi nessuna sovrapposizione risultava possibile.
    Capita quando l'immagine è piazzata con una matrice che la funzione non
    ricostruisce, e non solleva nessun errore: risponde una cosa vuota.

    Quindi tre fonti in cascata, dalla più precisa alla più prudente:
      1. get_image_rects(), scartando i rettangoli degeneri;
      2. i blocchi di tipo immagine dell'estrattore di testo, che portano il bbox;
      3. se la pagina contiene immagini ma nessuna delle due ha dato una posizione
         utilizzabile, si considera coperta l'intera pagina. È l'ipotesi prudente
         giusta: su un documento scansionato l'immagine è la pagina, e sbagliare
         per eccesso qui produce un avviso in più, non una fuga taciuta.
    """
    rettangoli = []
    for info in page.get_images(full=True):
        try:
            for r in page.get_image_rects(info[0]):
                r = pymupdf.Rect(r)
                if r.is_valid and not r.is_empty and r.get_area() > 1:
                    rettangoli.append(r)
        except Exception:
            continue

    if not rettangoli:
        try:
            for blocco in page.get_text("dict").get("blocks", []):
                if blocco.get("type") == 1:
                    r = pymupdf.Rect(blocco["bbox"])
                    if r.is_valid and not r.is_empty and r.get_area() > 1:
                        rettangoli.append(r)
        except Exception:
            pass

    if not rettangoli and page.get_images():
        rettangoli.append(pymupdf.Rect(page.rect))
    return rettangoli


def analizza(percorso: Path) -> dict:
    doc = pymupdf.open(percorso)
    pagine = []
    for numero, page in enumerate(doc, start=1):
        rettangoli_immagine = rettangoli_delle_immagini(page)

        reperti = []
        for forma in forme_coprenti(page):
            r = forma["rect"]
            # Si restringe di un punto per non catturare il testo che sfiora il
            # bordo della forma senza esserci sotto davvero.
            dentro = pymupdf.Rect(r.x0 + 1, r.y0 + 1, r.x1 - 1, r.y1 - 1)
            testo = ""
            if dentro.is_valid and not dentro.is_empty:
                testo = page.get_textbox(dentro).strip()

            sopra_immagine = any(r.intersects(ri) for ri in rettangoli_immagine)
            if not testo and not sopra_immagine:
                continue    # copre carta bianca: è grafica, non censura

            reperti.append({
                "riquadro": [round(v, 1) for v in r],
                "origine": forma["origine"],
                "scurezza": forma["scurezza"],
                "testo_sotto": testo[:300],
                "sopra_immagine": sopra_immagine,
            })

        if reperti:
            pagine.append({"pagina": numero, "reperti": reperti})

    esito = {
        "file": str(percorso),
        "pagine_totali": doc.page_count,
        "pagine_sospette": pagine,
        "verdetto": "SOSPETTO" if pagine else "PULITO",
    }
    doc.close()
    return esito


def stampa(esito: dict, silenzioso: bool):
    nome = Path(esito["file"]).name
    if esito["verdetto"] == "PULITO":
        print(f"PULITO    {nome} — nessuna forma opaca sopra contenuto estraibile")
        return
    quanti = sum(len(p["reperti"]) for p in esito["pagine_sospette"])
    print(f"SOSPETTO  {nome} — {quanti} forme opache sopra contenuto ancora estraibile")
    if silenzioso:
        return
    for p in esito["pagine_sospette"]:
        for r in p["reperti"]:
            print(f"  pagina {p['pagina']}  {r['origine']}  riquadro {r['riquadro']}")
            if r["testo_sotto"]:
                print(f"     testo leggibile sotto: {r['testo_sotto']!r}")
            if r["sopra_immagine"]:
                print("     copre un'immagine: il contenuto si recupera estraendo "
                      "l'immagine incorporata, che nessun rettangolo modifica")
    print("\n  Coprire non cancella. Per oscurare davvero: add_redact_annot() +")
    print("  apply_redactions(), oppure appiattire la pagina in immagine. Poi")
    print("  ricontrollare il file finito con questo stesso script.")


def main():
    p = argparse.ArgumentParser(
        description="Verifica se l'oscuramento di un PDF regge o è solo un rettangolo sopra.")
    p.add_argument("pdf", nargs="+", help="uno o più PDF da controllare")
    p.add_argument("--silenzioso", action="store_true", help="solo il verdetto per file")
    p.add_argument("--json", action="store_true", help="risultato in JSON")
    a = p.parse_args()

    esiti, errori = [], 0
    for nome in a.pdf:
        percorso = Path(nome)
        if not percorso.is_file():
            print(f"ERRORE    {nome} — file non trovato", file=sys.stderr)
            errori += 1
            continue
        try:
            esiti.append(analizza(percorso))
        except Exception as e:
            print(f"ERRORE    {nome} — {e}", file=sys.stderr)
            errori += 1

    if a.json:
        print(json.dumps(esiti, indent=2, ensure_ascii=False))
    else:
        for e in esiti:
            stampa(e, a.silenzioso)

    if errori:
        return 2
    return 1 if any(e["verdetto"] == "SOSPETTO" for e in esiti) else 0


if __name__ == "__main__":
    raise SystemExit(main())
