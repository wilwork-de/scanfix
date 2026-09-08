#!/usr/bin/env bash
# Collaudo del controllo redazione. Rigenera i campioni e verifica ogni verdetto.
#
#   bash tests/prova.sh              usa python3
#   PY=.venv/bin/python bash tests/prova.sh
set -uo pipefail
QUI="$(cd "$(dirname "$0")" && pwd)"
RADICE="$(dirname "$QUI")"
PY="${PY:-python3}"
CHECK="$RADICE/tools/controlla_redazione.py"

passati=0; falliti=0

verifica() {   # verifica <descrizione> <file> <verdetto atteso>
    local esito
    esito=$("$PY" "$CHECK" "$QUI/campioni/$2" --silenzioso 2>&1 | awk '{print $1}')
    if [ "$esito" = "$3" ]; then
        printf '  ok    %-52s %s\n' "$1" "$esito"; passati=$((passati+1))
    else
        printf '  FALLITO %-50s atteso %s, ottenuto %s\n' "$1" "$3" "$esito"; falliti=$((falliti+1))
    fi
}

contiene() {   # contiene <descrizione> <file> <stringa attesa nell'output>
    # L'output si cattura PRIMA di filtrarlo: con pipefail attivo la pipeline
    # erediterebbe l'uscita 1 del checker, che qui significa "fuga trovata",
    # cioe' esattamente il caso che il test vuole confermare. Filtrando in
    # pipeline il successo verrebbe letto come fallimento.
    local uscita
    uscita=$("$PY" "$CHECK" "$QUI/campioni/$2" 2>&1 || true)
    if printf '%s' "$uscita" | grep -qF "$3"; then
        printf '  ok    %-52s trova %s\n' "$1" "$3"; passati=$((passati+1))
    else
        printf '  FALLITO %-50s non ha trovato %s\n' "$1" "$3"; falliti=$((falliti+1))
    fi
}

echo "Rigenero i campioni..."
"$PY" "$QUI/genera_campioni.py" >/dev/null || { echo "campioni non generati"; exit 2; }

echo "Verdetti:"
verifica "rettangoli neri sopra il testo"        finta_redazione.pdf     SOSPETTO
verifica "redazione vera (contenuto rimosso)"    redazione_vera.pdf      PULITO
verifica "rettangoli sopra una pagina-immagine"  foto_con_rettangoli.pdf SOSPETTO
verifica "documento senza sovrapposizioni"       pulito.pdf              PULITO
verifica "fascia grafica (falso positivo noto)"  fascia_grafica.pdf      SOSPETTO

echo "Contenuto recuperato da sotto le coperture:"
contiene "rilegge il nome"            finta_redazione.pdf "Mario Ross"
contiene "rilegge il codice fiscale"  finta_redazione.pdf "RSSMRA80A01H50"
contiene "rilegge l'IBAN"             finta_redazione.pdf "IT60X0542811101000000123"
contiene "segnala l'immagine sotto"   foto_con_rettangoli.pdf "copre un'immagine"

echo "Posizione delle immagini (la regressione che dava PULITO sul caso vero):"
if "$PY" - "$RADICE/tools" "$QUI/campioni/foto_con_rettangoli.pdf" <<'PY'
import sys, pymupdf
sys.path.insert(0, sys.argv[1])
from controlla_redazione import rettangoli_delle_immagini
page = pymupdf.open(sys.argv[2])[0]
r = rettangoli_delle_immagini(page)
assert r, "nessun rettangolo immagine trovato"
assert all(x.get_area() > 1 for x in r), f"rettangolo degenere fra {r}"
PY
then printf '  ok    %-52s\n' "una pagina con immagini restituisce sempre un'area"; passati=$((passati+1))
else printf '  FALLITO %-50s\n' "rettangoli immagine"; falliti=$((falliti+1)); fi

echo
echo "$passati superati, $falliti falliti"
[ "$falliti" -eq 0 ]
