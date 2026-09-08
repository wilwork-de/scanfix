#!/usr/bin/env bash
# Converte una o piu' foto del CV firmato in un PDF A4 pronto per il portale.
#
#   ./jpg2pdf.sh foto.jpg                  -> CV_firmato.pdf
#   ./jpg2pdf.sh pag1.jpg pag2.jpg         -> CV_firmato.pdf di 2 pagine
#   ./jpg2pdf.sh foto.jpg -o CV_ITS.pdf    -> nome a scelta
#
# set -e ferma lo script al primo errore invece di proseguire su dati incompleti;
# -u tratta una variabile non definita come errore; -o pipefail fa fallire una
# pipeline se fallisce un comando in mezzo e non solo l'ultimo.
set -euo pipefail
QUI="$(dirname "$(readlink -f "$0")")"
exec python3 "$QUI/foto_in_pdf.py" "$@"
