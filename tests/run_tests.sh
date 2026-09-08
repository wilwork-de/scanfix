#!/usr/bin/env bash
# Test suite for the redaction check. Regenerates the fixtures and asserts every verdict.
#
#   bash tests/run_tests.sh                     uses python3
#   PY=.venv/bin/python bash tests/run_tests.sh
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"
PY="${PY:-python3}"
CHECK="$ROOT/tools/check_redaction.py"

passed=0; failed=0

expect() {   # expect <description> <file> <expected verdict>
    local got
    got=$("$PY" "$CHECK" "$HERE/fixtures/$2" --quiet 2>&1 | awk '{print $1}')
    if [ "$got" = "$3" ]; then
        printf '  ok    %-52s %s\n' "$1" "$got"; passed=$((passed+1))
    else
        printf '  FAIL  %-52s expected %s, got %s\n' "$1" "$3" "$got"; failed=$((failed+1))
    fi
}

recovers() {   # recovers <description> <file> <string expected in the output>
    # The output is captured BEFORE being filtered: with pipefail on, the pipeline
    # would inherit the checker's exit code 1, which here means "leak found" — that
    # is, exactly the case the test is confirming. Filtering in a pipeline would
    # read success as failure.
    local out
    out=$("$PY" "$CHECK" "$HERE/fixtures/$2" 2>&1 || true)
    if printf '%s' "$out" | grep -qF "$3"; then
        printf '  ok    %-52s finds %s\n' "$1" "$3"; passed=$((passed+1))
    else
        printf '  FAIL  %-52s did not find %s\n' "$1" "$3"; failed=$((failed+1))
    fi
}

echo "Regenerating fixtures..."
"$PY" "$HERE/make_fixtures.py" >/dev/null || { echo "fixtures not generated"; exit 2; }

echo "Verdicts:"
expect "black rectangles over text"          fake_redaction.pdf   SUSPECT
expect "real redaction (content removed)"    real_redaction.pdf   CLEAN
expect "rectangles over a photo page"        photo_with_boxes.pdf SUSPECT
expect "document with no overlays"           clean.pdf            CLEAN
expect "graphic band (known false positive)" graphic_band.pdf     SUSPECT

echo "Content recovered from under the covers:"
recovers "reads back the name"      fake_redaction.pdf   "Mario Ross"
recovers "reads back the tax code"  fake_redaction.pdf   "RSSMRA80A01H50"
recovers "reads back the IBAN"      fake_redaction.pdf   "IT60X0542811101000000123"
recovers "reports the image below"  photo_with_boxes.pdf "covers an image"

echo "Image placement (the regression that returned CLEAN on the real case):"
if "$PY" - "$ROOT/tools" "$HERE/fixtures/photo_with_boxes.pdf" <<'PY'
import sys, pymupdf
sys.path.insert(0, sys.argv[1])
from check_redaction import image_rects
page = pymupdf.open(sys.argv[2])[0]
r = image_rects(page)
assert r, "no image rectangle found"
assert all(x.get_area() > 1 for x in r), f"degenerate rectangle among {r}"
PY
then printf '  ok    %-52s\n' "a page with images always yields an area"; passed=$((passed+1))
else printf '  FAIL  %-52s\n' "image rectangles"; failed=$((failed+1)); fi

echo "Deskew on a page whose text does not fill it:"
if "$PY" - "$ROOT/tools" "$HERE/fixtures/short_note.png" <<'DESKEW'
import sys
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from clean_scan import _one_pass, load
_, fan = _one_pass(load(Path(sys.argv[2])))
# The page is rendered dead straight, so any fan-out reported here is invented.
# Before the fix this measured 6.60 degrees: the lower measurement band was taken
# at a fixed fraction of the frame and landed on blank paper, where every angle
# scores the same and the tie broke at the top of the search range.
assert fan < 0.15, f"straight page reported {fan:.2f} degrees of fan-out"
DESKEW
then printf '  ok    %-52s\n' "a straight short page reports no fan-out"; passed=$((passed+1))
else printf '  FAIL  %-52s\n' "straight short page still warped"; failed=$((failed+1)); fi

echo
echo "$passed passed, $failed failed"
[ "$failed" -eq 0 ]
