/**
 * The image maths the browser tools run, checked against the Python tools.
 *
 * Same argument as tests/test_js.mjs: two implementations of the same algorithm are
 * worse than one unless something holds them together, because they drift apart in
 * silence and the site then says one thing about a photograph while the command line
 * says another.
 *
 * The reference numbers below come from tests/imaging_reference.py, which runs the
 * Python functions on the same synthetic page this file builds. Re-derive them with:
 *
 *     .venv/bin/python tests/imaging_reference.py
 *
 * The tolerances are not slack: the ports differ in one deliberate way. Pillow
 * quantises the illumination estimate to 8 bits before blurring it, and the port
 * keeps floats, which moves a mean by a tenth of a grey level and moves no decision
 * at all.
 *
 *   node tests/test_imaging.mjs
 */

import * as im from "../docs/imaging.js";

const W = 320, H = 240;

let passed = 0, failed = 0;
const ok = (what, detail = "") => { console.log(`  ok    ${what.padEnd(52)} ${detail}`); passed++; };
const bad = (what, detail = "") => { console.log(`  FAIL  ${what.padEnd(52)} ${detail}`); failed++; };

function near(what, got, want, tol) {
  if (Math.abs(got - want) <= tol) ok(what, `${got.toFixed(4)} (python ${want})`);
  else bad(what, `got ${got.toFixed(4)}, python ${want}, tolerance ${tol}`);
}

function equal(what, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) ok(what, g); else bad(what, `got ${g}, expected ${w}`);
}

/** The same page tests/imaging_reference.py builds: lit from one corner, six lines. */
function page() {
  const grey = new Float32Array(W * H);
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      let v = 120 + 110 * (1 - (x / W) * 0.7 - (y / H) * 0.55);
      if (y % 24 >= 0 && y >= 30 && y < H - 30 && (y - 30) % 24 < 6 && x >= 30 && x < W - 40) v -= 130;
      grey[y * W + x] = Math.trunc(Math.min(255, Math.max(0, v)));
    }
  }
  return grey;
}

const mean = a => { let s = 0; for (const v of a) s += v; return s / a.length; };

// --- flat-field correction --------------------------------------------------

const grey = page();
const light = im.lightField(grey, W, H);
const flat = im.flatten(grey, light);

console.log("Flat-field correction, against tools/clean_scan.py:");
near("illumination estimate, mean", mean(light), 140.9224, 0.5);
near("corrected image, mean", mean(flat), 224.1941, 0.3);
near("white point (92nd percentile)", im.percentile(flat, 92), 255.0, 0.2);
near("black point (2nd percentile)", im.percentile(flat, 2), 14.7115, 0.3);

const box = im.inkBox(flat, W, H, 170, 2);
equal("bounding box of the ink", [box.x0, box.y0, box.x1, box.y1], [30, 30, 279, 203]);

// The point of dividing rather than brightening: the paper must come out even
// across the page even though the lamp was on one corner.
const corner = (x, y) => flat[y * W + x];
const spread = Math.abs(corner(5, 5) - corner(W - 5, H - 5));
if (spread < 12) ok("paper is even corner to corner", `${spread.toFixed(1)} grey levels apart`);
else bad("paper is even corner to corner", `${spread.toFixed(1)} grey levels apart, expected < 12`);

// --- the signature alpha channel --------------------------------------------

console.log("Signature alpha, against tools/extract_signature.py:");
const alpha = im.signatureAlpha(flat, 205, 95);
near("alpha channel, mean", mean(alpha), 39.5333, 0.3);
let covered = 0;
for (const v of alpha) if (v > 30) covered++;
near("ink coverage, per cent", covered / alpha.length * 100, 15.625, 0.05);

// A ramp and not a step: there have to be partly transparent pixels at the edges of
// the strokes, or the signature comes out with staircase edges.
let partial = 0;
for (const v of alpha) if (v > 5 && v < 250) partial++;
if (partial > 0) ok("stroke edges stay semi-transparent", `${partial} pixels between`);
else bad("stroke edges stay semi-transparent", "the ramp collapsed into a threshold");

const rgba = im.greyToRgba(grey, W, H);
const cut = im.extractSignature(rgba, W, H);
equal("signature trimmed to the ink, with padding",
      [cut.box.x0, cut.box.y0, cut.box.x1, cut.box.y1], [24, 24, 286, 210]);

// --- geometry ---------------------------------------------------------------

console.log("Geometry:");
const tilted = im.rotate(page(), W, H, -1.5, 255);
near("slant of the text lines on a tilted page", im.textLineAngle(tilted, W, H), 1.5, 0.1);

// A band with no text in it scores the same at every angle. Measuring it has to
// return nothing rather than whichever end of the range happened to be tried last:
// that bug turned a straight photo of a short letter into a page tilted by six
// degrees, because the lower band of the frame was blank paper.
const blank = new Float32Array(320 * 120).fill(240);
near("a blank band measures no angle at all", im.textLineAngle(blank, 320, 120), 0, 1e-9);

// And the whole pass, on a page that is already straight: no fan-out to correct, and
// the text still there afterwards.
const upright = im.straightenPass(im.greyToRgba(page(), W, H), W, H);
near("a straight page needs no straightening", upright.fan, 0, 0.05);
if (upright.width >= 240 && upright.height >= 160) {
  ok("straightening crops to the text", `${upright.width}x${upright.height}`);
} else {
  bad("straightening crops to the text", `${upright.width}x${upright.height}`);
}

const fit = im.a4Canvas(1000, 1300);
equal("A4 canvas rebuilt around the text",
      [fit.canvasW, fit.canvasH, fit.marginX, fit.marginY], [1163, 1645, 81, 58]);
const ratio = fit.canvasW / fit.canvasH;
if (Math.abs(ratio - 0.70711) < 0.002) ok("rebuilt sheet has the A4 ratio", ratio.toFixed(5));
else bad("rebuilt sheet has the A4 ratio", ratio.toFixed(5));

// A projective transform that maps a square to itself must be the identity, and a
// point run through the trapezoid must land where the algebra says.
const identity = im.perspectiveCoeffs(
  [[0, 0], [10, 0], [10, 10], [0, 10]], [[0, 0], [10, 0], [10, 10], [0, 10]]);
const isIdentity = identity.every((v, i) => Math.abs(v - [1, 0, 0, 0, 1, 0, 0, 0][i]) < 1e-9);
if (isIdentity) ok("projective transform of a square is the identity");
else bad("projective transform of a square is the identity", JSON.stringify(identity));

// --- autocontrast -----------------------------------------------------------

console.log("Autocontrast, against tools/photo_to_pdf.py:");
const lut = im.autocontrastLut(page(), 1, 6);
const stretched = Float32Array.from(page(), v => lut[Math.round(v)]);
let lo = 255, hi = 0;
for (const v of stretched) { if (v < lo) lo = v; if (v > hi) hi = v; }
equal("autocontrast reaches both ends of the range", [lo, hi], [0, 255]);
near("autocontrast, mean of the result", mean(stretched), 173.9997, 0.5);

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
