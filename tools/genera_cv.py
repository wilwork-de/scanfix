#!/usr/bin/env python3
"""
Genera un CV italiano in PDF, pronto per l'upload sul portale ITS.

Perché uno script e non Word: il PDF esce identico ogni volta, il testo resta
selezionabile (i portali a volte lo leggono in automatico) e la data in fondo si
aggiorna da sola. Modifichi il dizionario DATI qui sotto e rilanci.

Uso:
    python3 genera_cv.py                          # data = oggi, firma = riga vuota
    python3 genera_cv.py --firma firma.png        # incolla la firma scansionata
    python3 genera_cv.py --luogo Torino --output CV.pdf

Il flag --firma serve per il metodo B spiegato in LEGGIMI.md: firmi su carta
bianca, fotografi, ritagli, e l'immagine viene appoggiata sulla riga della firma.
Il resto del CV resta testo nitido invece che una scansione sfocata.
"""

import argparse
from datetime import date
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

# ---------------------------------------------------------------------------
# 1. I TUOI DATI - è l'unica parte che devi toccare.
#    Tutto cio' che sta fra [parentesi quadre] è un segnaposto da sostituire.
#    Se una voce non ti serve, mettila a "" oppure svuota la lista: le sezioni
#    vuote non vengono stampate.
# ---------------------------------------------------------------------------

DATI = {
    "nome": "[Nome]",
    "cognome": "[Cognome]",
    # Il ruolo è una riga sola sotto il nome. Per un ITS scrivi il profilo che
    # stai cercando, non quello che hai fatto finora.
    "ruolo": "Candidato - [nome del corso ITS]",

    "nato_il": "[gg/mm/aaaa]",
    "nato_a": "[Città]",
    "residenza": "[Via e numero], [CAP] [Città] ([Provincia])",
    "telefono": "[+39 ...]",
    "email": "[nome.cognome@example.com]",
    "linkedin": "",                 # es. "linkedin.com/in/tuonome" - lascia "" se non lo vuoi
    "patente": "B - automunito",
    "cittadinanza": "Italiana",

    # Istruzione: la più recente per prima. Il diploma DEVE esserci, perché è
    # il documento che l'ITS ti sta chiedendo anche come allegato separato.
    "istruzione": [
        {
            "titolo": "Diploma di [indirizzo di studio]",
            "ente": "[Nome dell'istituto] - [Città]",
            "periodo": "[aaaa]",
            "note": [
                "Votazione: [xx/100]",
            ],
        },
        {
            "titolo": "[Altro corso o certificazione]",
            "ente": "[Ente erogatore]",
            "periodo": "[aaaa]",
            "note": [],
        },
    ],

    # Esperienza: la più recente per prima. Ogni riga dice cosa FACEVI, con un
    # verbo all'inizio. "Responsabile di" non dice niente, "gestito X" si'.
    "esperienza": [
        {
            "titolo": "[Ruolo]",
            "ente": "[Azienda] - [Città]",
            "periodo": "[mm/aaaa] - [mm/aaaa o 'in corso']",
            "note": [
                "[Cosa facevi, con un numero dentro se ce l'hai]",
                "[Strumenti o tecnologie che usavi]",
            ],
        },
    ],

    # Competenze raggruppate. Le etichette le decidi tu.
    "competenze": [
        ("Sistemi operativi", "[Windows, Linux, ...]"),
        ("Reti", "[TCP/IP, DNS, ...]"),
        ("Linguaggi e strumenti", "[Python, Git, ...]"),
    ],

    "lingue": [
        ("Italiano", "madrelingua"),
        ("Inglese", "[A2 / B1 / B2 - livello QCER]"),
    ],

    # Testo libero finale. Lascia lista vuota per saltare la sezione.
    "altro": [
        "Disponibilità immediata e a trasferte sul territorio [regione].",
    ],
}

# Formula privacy. Il GDPR va citato per primo: è la fonte superiore e quella
# vigente, il Codice italiano è la norma nazionale che gli si è adeguata.
#
# NON citare "art. 13 del D.Lgs. 196/2003": quell'articolo è stato ABROGATO dal
# D.Lgs. 101/2018, che ha armonizzato il Codice col GDPR. L'informativa oggi la
# governano gli artt. 13-14 del Regolamento. Il template che gira su mezza
# internet cita ancora il vecchio art. 13 e nessuno viene scartato per questo,
# ma è un riferimento a una norma che non esiste più.
PRIVACY = (
    "Autorizzo il trattamento dei miei dati personali contenuti nel presente "
    "curriculum vitae ai sensi del Regolamento UE 2016/679 (GDPR) e del "
    "D. Lgs. 196/2003 come modificato dal D. Lgs. 101/2018."
)

MESI = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]

# Palette sobria: nero-blu per i titoli, grigio per il corpo. Niente colori
# accesi, un CV istituzionale si legge anche stampato in bianco e nero.
INCHIOSTRO = (26, 32, 44)
GRIGIO = (74, 85, 104)
GRIGIO_CHIARO = (160, 174, 192)
FILETTO = (203, 213, 224)


class CV(FPDF):
    """FPDF con qualche scorciatoia per non ripetere set_font ovunque."""

    def __init__(self, dati):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.dati = dati
        # Margine inferiore alto: lascia respiro e tiene il blocco firma staccato.
        self.set_auto_page_break(auto=True, margin=18)
        self.set_margins(18, 16, 18)
        self.set_title(f"Curriculum Vitae - {dati['nome']} {dati['cognome']}")
        self.set_author(f"{dati['nome']} {dati['cognome']}")

    def footer(self):
        """Numero di pagina in fondo. Su un CV di una pagina sola è innocuo,
        su due diventa utile se il selezionatore stampa e i fogli si separano."""
        self.set_y(-13)
        self.set_font("Helvetica", "", 7.5)
        self.set_text_color(*GRIGIO_CHIARO)
        etichetta = f"{self.dati['nome']} {self.dati['cognome']} - pag. {self.page_no()}/{{nb}}"
        self.cell(0, 4, etichetta, align="C")

    # -- intestazione --------------------------------------------------------

    def intestazione(self):
        d = self.dati
        self.set_font("Helvetica", "B", 21)
        self.set_text_color(*INCHIOSTRO)
        self.cell(0, 9, f"{d['nome']} {d['cognome']}".upper(),
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        if d.get("ruolo"):
            self.set_font("Helvetica", "", 10.5)
            self.set_text_color(*GRIGIO)
            self.cell(0, 5.5, d["ruolo"], new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.ln(2.5)

        # Contatti su una o due righe, separati da un punto medio.
        contatti = [v for v in (d.get("telefono"), d.get("email"), d.get("linkedin")) if v]
        indirizzo = [v for v in (d.get("residenza"),) if v]
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*GRIGIO)
        for riga in (contatti, indirizzo):
            if riga:
                self.cell(0, 4.6, "  \xb7  ".join(riga),
                          new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.ln(3)
        self.set_draw_color(*INCHIOSTRO)
        self.set_line_width(0.5)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(5)

    # -- blocchi riutilizzabili ---------------------------------------------

    def sezione(self, titolo):
        """Titolo di sezione maiuscolo con filetto sottile sotto."""
        # Se restano meno di 22 mm non ha senso aprire una sezione qui:
        # il titolo finirebbe orfano in fondo alla pagina.
        if self.h - self.b_margin - self.get_y() < 22:
            self.add_page()
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*INCHIOSTRO)
        self.cell(0, 5.5, titolo.upper(), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*FILETTO)
        self.set_line_width(0.25)
        self.line(self.l_margin, self.get_y() + 0.4, self.w - self.r_margin, self.get_y() + 0.4)
        self.ln(3)

    def voce(self, titolo, ente="", periodo="", note=()):
        """Una riga di esperienza o istruzione: titolo a sinistra, date a destra."""
        larghezza_data = 38
        y = self.get_y()

        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*INCHIOSTRO)
        self.multi_cell(self.epw - larghezza_data, 5, titolo,
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        if periodo:
            # La data la scrivo dopo, riportando la Y a quella del titolo, così
            # resta allineata in alto anche se il titolo va a capo.
            y_dopo = self.get_y()
            self.set_xy(self.w - self.r_margin - larghezza_data, y)
            self.set_font("Helvetica", "", 9)
            self.set_text_color(*GRIGIO)
            self.cell(larghezza_data, 5, periodo, align="R")
            self.set_y(y_dopo)

        if ente:
            self.set_font("Helvetica", "I", 9.5)
            self.set_text_color(*GRIGIO)
            self.multi_cell(self.epw, 4.8, ente, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        for riga in note:
            self.punto(riga)
        self.ln(2.6)

    def punto(self, testo, rientro=3.5):
        """Elenco puntato. Il pallino è disegnato, non un carattere: i font
        base del PDF non hanno il bullet e andrebbe in errore di codifica."""
        self.set_font("Helvetica", "", 9.5)
        self.set_text_color(*GRIGIO)
        x0 = self.l_margin + rientro
        y0 = self.get_y()
        self.set_fill_color(*GRIGIO_CHIARO)
        self.rect(x0, y0 + 1.9, 1.3, 1.3, style="F")
        self.set_xy(x0 + 3.6, y0)
        self.multi_cell(self.epw - rientro - 3.6, 4.7, testo,
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def coppia(self, etichetta, valore, larghezza=42):
        """Riga a due colonne: etichetta in grassetto, valore accanto."""
        y = self.get_y()
        self.set_font("Helvetica", "B", 9.5)
        self.set_text_color(*INCHIOSTRO)
        self.cell(larghezza, 5, etichetta)
        self.set_font("Helvetica", "", 9.5)
        self.set_text_color(*GRIGIO)
        self.set_xy(self.l_margin + larghezza, y)
        self.multi_cell(self.epw - larghezza, 5, valore,
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # -- il blocco che il portale ITS sta chiedendo -------------------------

    def blocco_firma(self, luogo, giorno, firma_img=None):
        """Privacy + luogo/data a sinistra + firma a mano a destra.

        È la parte per cui il CV è stato respinto. Va in fondo all'ultima
        pagina, sempre in quest'ordine: prima l'autorizzazione privacy, poi
        data e firma sulla stessa riga.
        """
        # Serve spazio per privacy (~14mm) + firma (~30mm). Se non c'e', pagina nuova.
        if self.h - self.b_margin - self.get_y() < 48:
            self.add_page()
        else:
            self.ln(4)

        self.set_font("Helvetica", "", 8)
        self.set_text_color(*GRIGIO)
        self.multi_cell(self.epw, 3.9, PRIVACY, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(8)

        y = self.get_y()
        meta = self.epw / 2

        # Sinistra: luogo e data, in chiaro. "Torino, 8 settembre 2026".
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*INCHIOSTRO)
        self.cell(meta, 5, f"{luogo}, {giorno}")

        # Destra: etichetta, spazio per l'inchiostro, riga.
        self.set_xy(self.l_margin + meta, y)
        self.set_font("Helvetica", "", 10)
        self.cell(meta, 5, "Firma", align="L")

        y_riga = y + 18
        if firma_img:
            # L'immagine si appoggia SOPRA la riga, come una firma vera.
            altezza = 14
            self.image(str(firma_img),
                       x=self.l_margin + meta + 1,
                       y=y_riga - altezza - 0.5,
                       h=altezza)

        self.set_draw_color(*INCHIOSTRO)
        self.set_line_width(0.3)
        self.line(self.l_margin + meta, y_riga, self.w - self.r_margin, y_riga)
        self.set_y(y_riga)


def data_italiana(g: date) -> str:
    """8 settembre 2026 - senza zero davanti al giorno, come si scrive a mano."""
    return f"{g.day} {MESI[g.month - 1]} {g.year}"


def costruisci(dati, luogo, giorno, firma_img, output):
    pdf = CV(dati)
    pdf.add_page()
    pdf.intestazione()

    # -- dati anagrafici: per un ente pubblico servono, per un'azienda no.
    anagrafica = [
        ("Data di nascita", dati.get("nato_il")),
        ("Luogo di nascita", dati.get("nato_a")),
        ("Cittadinanza", dati.get("cittadinanza")),
        ("Patente", dati.get("patente")),
    ]
    anagrafica = [(k, v) for k, v in anagrafica if v]
    if anagrafica:
        pdf.sezione("Dati personali")
        for k, v in anagrafica:
            pdf.coppia(k, v)
        pdf.ln(3)

    if dati.get("istruzione"):
        pdf.sezione("Istruzione e formazione")
        for v in dati["istruzione"]:
            pdf.voce(v["titolo"], v.get("ente", ""), v.get("periodo", ""), v.get("note", ()))

    if dati.get("esperienza"):
        pdf.sezione("Esperienza professionale")
        for v in dati["esperienza"]:
            pdf.voce(v["titolo"], v.get("ente", ""), v.get("periodo", ""), v.get("note", ()))

    if dati.get("competenze"):
        pdf.sezione("Competenze tecniche")
        for k, v in dati["competenze"]:
            pdf.coppia(k, v, larghezza=46)
        pdf.ln(3)

    if dati.get("lingue"):
        pdf.sezione("Lingue")
        for k, v in dati["lingue"]:
            pdf.coppia(k, v, larghezza=46)
        pdf.ln(3)

    if dati.get("altro"):
        pdf.sezione("Altre informazioni")
        for riga in dati["altro"]:
            pdf.punto(riga)
        pdf.ln(3)

    pdf.blocco_firma(luogo, giorno, firma_img)
    pdf.output(str(output))
    return output


def main():
    p = argparse.ArgumentParser(description="Genera il CV in PDF per il portale ITS.")
    p.add_argument("--luogo", default="Torino",
                   help="città che compare accanto alla data (default: Torino)")
    p.add_argument("--data", default=None,
                   help="data in formato aaaa-mm-gg; default: oggi")
    p.add_argument("--firma", default=None,
                   help="PNG/JPG della firma scansionata, con sfondo bianco o trasparente")
    p.add_argument("--output", default=None, help="percorso del PDF in uscita")
    a = p.parse_args()

    giorno = date.fromisoformat(a.data) if a.data else date.today()

    firma = Path(a.firma).expanduser() if a.firma else None
    if firma and not firma.is_file():
        p.error(f"file firma non trovato: {firma}")

    nome_file = f"CV_{DATI['nome']}_{DATI['cognome']}.pdf".replace(" ", "_")
    nome_file = nome_file.replace("[", "").replace("]", "")
    out = Path(a.output) if a.output else Path(__file__).parent / nome_file

    costruisci(DATI, a.luogo, data_italiana(giorno), firma, out)
    print(f"Creato: {out}")
    if not firma:
        print("ATTENZIONE: la riga della firma è vuota. Il portale ITS vuole la "
              "firma a mano - stampa e firma, oppure rilancia con --firma firma.png")


if __name__ == "__main__":
    main()
