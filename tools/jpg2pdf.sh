#!/usr/bin/env bash
# Convert one or more photos of a signed document into an A4 PDF.
#
#   ./jpg2pdf.sh photo.jpg                  -> document.pdf
#   ./jpg2pdf.sh page1.jpg page2.jpg        -> a two-page document.pdf
#   ./jpg2pdf.sh photo.jpg -o signed.pdf    -> name of your choice
#
# set -e stops at the first error instead of carrying on with partial data; -u
# treats an unset variable as an error; -o pipefail makes a pipeline fail when a
# command in the middle fails, not only the last one.
set -euo pipefail
HERE="$(dirname "$(readlink -f "$0")")"
exec "${PYTHON:-python3}" "$HERE/photo_to_pdf.py" "$@"
